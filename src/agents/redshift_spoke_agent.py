"""Redshift Spoke Agent — FastAPI service for querying Amazon Redshift.

Receives StructuredIntent payloads from the Orchestrator Hub, generates
parameterized SQL via the SQL Generator, executes queries through the
Redshift Connector (boto3 redshift-data), and returns AgentResult responses
compatible with the visualization pipeline.

Runs as a FastAPI process on port 8011 with POST /agents/redshift-spoke-agent/invoke.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.services.logging_config import configure_logging

configure_logging()

from src.config import REDSHIFT_AGENT_PORT, RedshiftConfig
from src.models.redshift_models import GeneratedQuery, RedshiftError, RedshiftResult, SQLGeneratorError
from src.models.shared import AgentResult, StructuredIntent
from src.services.observability import extract_correlation_id, observability_decorator
from src.services.redshift_connector import RedshiftConnector
from src.services.schema_registry import SchemaRegistry
from src.services.sql_generator import SQLGenerator

logger = logging.getLogger(__name__)

AGENT_ID = "redshift-spoke-agent"

# Module-level state set during startup
_connector: RedshiftConnector | None = None
_schema_registry: SchemaRegistry | None = None
_sql_generator: SQLGenerator | None = None
_healthy: bool = False
_valid_concept_ids: list[str] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: validate Redshift connectivity and schema on startup."""
    global _connector, _schema_registry, _sql_generator, _healthy, _valid_concept_ids

    config = RedshiftConfig.from_env()
    _connector = RedshiftConnector(config)
    _schema_registry = SchemaRegistry()
    _sql_generator = SQLGenerator(_schema_registry)

    # Validate connectivity
    connected = await _connector.validate_connectivity()
    if not connected:
        logger.warning(
            "Redshift connectivity check failed at startup — starting in degraded state"
        )
        _healthy = False
        yield
        return

    # Validate Schema Registry against Redshift
    _valid_concept_ids = await _schema_registry.validate_against_redshift(_connector)

    if not _valid_concept_ids:
        logger.error(
            "No valid schema mappings found in Redshift — refusing to start"
        )
        raise RuntimeError(
            "Redshift Spoke Agent cannot start: no valid schema mappings available"
        )

    _healthy = True
    logger.info(
        "Redshift Spoke Agent started successfully with %d valid concepts: %s",
        len(_valid_concept_ids),
        _valid_concept_ids,
    )

    yield


app = FastAPI(
    title="Redshift Spoke Agent",
    description="Spoke agent that queries Amazon Redshift via the Data API based on structured intents.",
    version="1.0.0",
    lifespan=lifespan,
)


class InvokeRequest(BaseModel):
    """Request body for the agent invoke endpoint."""

    structured_intent: dict


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint returning service status and connection info."""
    config = RedshiftConfig.from_env()
    return {
        "status": "healthy" if _healthy else "unhealthy",
        "service": AGENT_ID,
        "port": REDSHIFT_AGENT_PORT,
        "database": config.database,
    }


@app.post(f"/agents/{AGENT_ID}/invoke")
@observability_decorator("redshift_spoke_agent")
async def invoke_agent(request: Request, body: InvokeRequest) -> JSONResponse:
    """Process a structured intent: generate SQL, execute, format AgentResult.

    Validates the incoming StructuredIntent, generates parameterized SQL
    via the SQL Generator, executes it through the Redshift Connector,
    and returns an AgentResult with the appropriate data_type mapping.

    Checks for upstream disconnection before executing the expensive
    Redshift query and returns CANCELLED status if detected.

    Args:
        request: The inbound FastAPI request.
        body: Request body containing the structured_intent dict.

    Returns:
        JSONResponse with AgentResult (always 200 per spoke agent contract).
    """
    correlation_id = extract_correlation_id(request)

    # Validate StructuredIntent
    try:
        intent = StructuredIntent.model_validate(body.structured_intent)
    except Exception as e:
        result = AgentResult(
            status="error",
            payload=None,
            error_type="INVALID_INTENT",
            error_description=f"Failed to parse structured intent: {e}",
            agent_id=AGENT_ID,
            data_source="redshift",
        )
        return JSONResponse(status_code=200, content=result.model_dump(mode="json"))

    # Generate SQL
    gen_result = _sql_generator.generate(intent)

    if isinstance(gen_result, SQLGeneratorError):
        result = AgentResult(
            status="error",
            payload=None,
            error_type=gen_result.error_type,
            error_description=gen_result.description,
            agent_id=AGENT_ID,
            data_source="redshift",
        )
        return JSONResponse(status_code=200, content=result.model_dump(mode="json"))

    # Check for upstream disconnection before expensive operation
    if await request.is_disconnected():
        logger.info(f"Client disconnected before Redshift query, correlation_id={correlation_id}")
        result = AgentResult(
            status="CANCELLED",
            payload=None,
            agent_id=AGENT_ID,
            data_source="redshift",
        )
        return JSONResponse(status_code=200, content=result.model_dump(mode="json"))

    # Execute query via Redshift Connector
    exec_result = await _connector.execute_statement(
        gen_result.sql, parameters=gen_result.parameters
    )

    if isinstance(exec_result, RedshiftError):
        error_type_map = {
            "TIMEOUT": "TIMEOUT_ERROR",
            "AUTH_FAILURE": "CONNECTION_ERROR",
            "QUERY_FAILURE": "QUERY_EXECUTION_ERROR",
            "CONNECTION_ERROR": "CONNECTION_ERROR",
        }
        result = AgentResult(
            status="error",
            payload=None,
            error_type=error_type_map.get(exec_result.error_type, "QUERY_EXECUTION_ERROR"),
            error_description=exec_result.description,
            agent_id=AGENT_ID,
            data_source="redshift",
        )
        return JSONResponse(status_code=200, content=result.model_dump(mode="json"))

    # Format response based on query type
    payload = _format_payload(gen_result, exec_result)

    result = AgentResult(
        status="success",
        payload=payload,
        agent_id=AGENT_ID,
        data_source="redshift",
    )
    return JSONResponse(status_code=200, content=result.model_dump(mode="json"))


def _format_payload(query: GeneratedQuery, result: RedshiftResult) -> dict[str, Any]:
    """Format the query result into the appropriate payload structure.

    Maps query_type to data_type:
    - lookup → tabular (columns + rows)
    - aggregation → aggregation (aggregations dict)
    - comparison → comparison (groups dict)

    Args:
        query: The generated query with metadata.
        result: The Redshift execution result.

    Returns:
        Dict payload conforming to the AgentResult payload schema.
    """
    if query.query_type == "lookup":
        return _format_tabular(result)
    elif query.query_type == "aggregation":
        return _format_aggregation(result)
    elif query.query_type == "comparison":
        return _format_comparison(result)
    else:
        # Fallback to tabular
        return _format_tabular(result)


def _format_tabular(result: RedshiftResult) -> dict[str, Any]:
    """Format result as tabular data (columns + rows).

    Args:
        result: The Redshift execution result.

    Returns:
        Payload with data_type "tabular", columns, rows, and row_count.
    """
    columns = [col["name"] for col in result.columns]
    return {
        "data_type": "tabular",
        "columns": columns,
        "rows": result.rows,
        "row_count": result.row_count,
    }


def _format_aggregation(result: RedshiftResult) -> dict[str, Any]:
    """Format result as aggregation data.

    For grouped aggregations (GROUP BY queries that produce multiple rows
    with a categorical dimension), returns tabular format to preserve the
    per-group breakdown. This allows the visualization renderer to chart
    each group correctly.

    For scalar aggregations (single-row results like SELECT SUM(...)),
    returns the summary aggregation dict.

    Args:
        result: The Redshift execution result.

    Returns:
        Payload with appropriate data_type based on result shape.
    """
    if not result.rows:
        return {
            "data_type": "aggregation",
            "aggregations": {},
            "row_count": 0,
        }

    columns = [col["name"] for col in result.columns]

    # Detect if this is a grouped aggregation (multiple rows with a
    # categorical first column) vs a scalar aggregation (single row).
    # Grouped aggregations should preserve row-level data for charting.
    has_multiple_rows = len(result.rows) > 1
    has_categorical_dimension = False

    if has_multiple_rows and result.rows:
        # Check if the first column contains non-numeric values (GROUP BY dim)
        first_col_values = [row[0] for row in result.rows if row]
        has_categorical_dimension = any(
            isinstance(v, str) or isinstance(v, bool)
            for v in first_col_values
        )

    if has_multiple_rows and has_categorical_dimension:
        # Grouped aggregation → return as tabular to preserve per-group rows
        return {
            "data_type": "tabular",
            "columns": columns,
            "rows": result.rows,
            "row_count": result.row_count,
        }

    # Scalar aggregation (single row or all-numeric columns) → summary dict
    aggregations: dict[str, Any] = {}
    for col_idx, col_name in enumerate(columns):
        values = [row[col_idx] for row in result.rows if col_idx < len(row)]
        numeric_values = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]

        if numeric_values:
            aggregations[col_name] = {
                "sum": sum(numeric_values),
                "avg": sum(numeric_values) / len(numeric_values),
                "min": min(numeric_values),
                "max": max(numeric_values),
                "count": len(numeric_values),
            }

    return {
        "data_type": "aggregation",
        "aggregations": aggregations,
        "row_count": result.row_count,
    }


def _format_comparison(result: RedshiftResult) -> dict[str, Any]:
    """Format result as comparison data grouped by first column.

    The first column is the GROUP BY dimension; remaining columns are
    numeric aggregates for each group.

    Args:
        result: The Redshift execution result.

    Returns:
        Payload with data_type "comparison", group_by, and groups dict.
    """
    if not result.rows:
        return {
            "data_type": "comparison",
            "group_by": None,
            "groups": {},
            "row_count": 0,
        }

    columns = [col["name"] for col in result.columns]

    # First column is the group-by dimension
    group_by_col = columns[0] if columns else None
    numeric_cols = columns[1:] if len(columns) > 1 else []

    groups: dict[str, dict[str, Any]] = {}
    for row in result.rows:
        if not row:
            continue
        group_key = str(row[0])
        group_data: dict[str, Any] = {}
        for col_idx, col_name in enumerate(numeric_cols, start=1):
            if col_idx < len(row):
                group_data[col_name] = row[col_idx]
        groups[group_key] = group_data

    return {
        "data_type": "comparison",
        "group_by": group_by_col,
        "groups": groups,
        "row_count": result.row_count,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=REDSHIFT_AGENT_PORT)
