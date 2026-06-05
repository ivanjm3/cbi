"""Unified Spoke Agent — Deterministic multi-source data agent.

Queries both JSON and CSV data sources from S3 based on entity_refs
from the structured intent. Uses deterministic routing (no LLM) for
fast, predictable data retrieval.

Runs as a FastAPI process on port 8010 with POST /agents/spoke-agent/invoke.
No retry on data source errors (single-attempt semantics).

Requirements: 6.1, 6.2, 6.3, 6.4
"""

import csv
import io
import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.services.logging_config import configure_logging
configure_logging()

from src.config import AGENT_A_PORT, S3_BUCKET, get_s3_client
from src.models.shared import AgentResult, StructuredIntent
from src.services.observability import (
    extract_correlation_id,
    observability_decorator,
)

logger = logging.getLogger(__name__)

AGENT_ID = "spoke-agent"
S3_FINANCIAL_KEY = "data-sources/financial_data.json"
S3_PRODUCT_KEY = "data-sources/product_catalog.csv"


# --- Data source query functions ---


def query_financial_data(
    query_type: str, entity_refs: list[str], filters: str = ""
) -> str:
    """Query the financial JSON data source for sales and revenue information.

    Contains quarterly sales revenue and order volume data broken down by
    product category and region. Use this tool when the query involves
    financial metrics, revenue, sales, or quarterly reports.

    Args:
        query_type: One of "lookup", "aggregation", or "comparison".
        entity_refs: List of ontology concept identifiers to filter by.
        filters: Optional JSON string of additional filters.

    Returns:
        JSON string with query results.
    """
    try:
        s3 = get_s3_client()
        response = s3.get_object(Bucket=S3_BUCKET, Key=S3_FINANCIAL_KEY)
        content = response["Body"].read().decode("utf-8")
        data = json.loads(content)

        rows = data.get("rows", [])
        columns = data.get("columns", [])
        filtered_rows = _filter_rows_dict(rows, entity_refs)
        payload = _execute_query(query_type, filtered_rows, columns)

        return json.dumps({"status": "success", "data_source": "financial_data.json", **payload})

    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "data_source": "financial_data.json"})


def query_product_catalog(
    query_type: str, entity_refs: list[str], filters: str = ""
) -> str:
    """Query the product catalog CSV data source for product information.

    Contains product names, categories, prices, stock quantities, and supplier
    details. Use this tool when the query involves products, catalog items,
    inventory, or pricing.

    Args:
        query_type: One of "lookup", "aggregation", or "comparison".
        entity_refs: List of ontology concept identifiers to filter by.
        filters: Optional JSON string of additional filters.

    Returns:
        JSON string with query results.
    """
    try:
        s3 = get_s3_client()
        response = s3.get_object(Bucket=S3_BUCKET, Key=S3_PRODUCT_KEY)
        content = response["Body"].read().decode("utf-8")

        rows: list[dict[str, Any]] = []
        columns: list[str] = []
        reader = csv.DictReader(io.StringIO(content))
        columns = list(reader.fieldnames or [])
        for row in reader:
            rows.append(_coerce_row(row))

        filtered_rows = _filter_rows_dict(rows, entity_refs)
        payload = _execute_query(query_type, filtered_rows, columns)

        return json.dumps({"status": "success", "data_source": "product_catalog.csv", **payload})

    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "data_source": "product_catalog.csv"})


# --- Shared query execution helpers ---


def _filter_rows_dict(
    rows: list[dict[str, Any]], entity_refs: list[str]
) -> list[dict[str, Any]]:
    """Filter rows relevant to the entity references."""
    if not entity_refs:
        return rows

    keywords = [ref.replace("ontology:", "").replace("_", " ").lower() for ref in entity_refs]

    matched = []
    for row in rows:
        row_text = " ".join(str(v).lower() for v in row.values())
        if any(kw in row_text for kw in keywords):
            matched.append(row)

    return matched if matched else rows


def _execute_query(
    query_type: str, rows: list[dict[str, Any]], columns: list[str]
) -> dict[str, Any]:
    """Execute a query based on type."""
    if query_type == "aggregation":
        return _execute_aggregation(rows, columns)
    elif query_type == "comparison":
        return _execute_comparison(rows, columns)
    else:
        return _execute_lookup(rows, columns)


def _execute_lookup(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, Any]:
    """Return filtered rows directly."""
    return {
        "data_type": "tabular",
        "columns": columns,
        "rows": [[row.get(col) for col in columns] for row in rows],
        "row_count": len(rows),
    }


def _execute_aggregation(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, Any]:
    """Compute sums and averages for numeric columns."""
    if not rows:
        return {"data_type": "aggregation", "aggregations": {}, "row_count": 0}

    numeric_cols = [
        col for col in columns
        if isinstance(rows[0].get(col), (int, float)) and not isinstance(rows[0].get(col), bool)
    ]

    aggregations: dict[str, dict[str, Any]] = {}
    for col in numeric_cols:
        values = [
            row.get(col, 0) for row in rows
            if isinstance(row.get(col), (int, float)) and not isinstance(row.get(col), bool)
        ]
        if values:
            aggregations[col] = {
                "sum": round(sum(values), 2),
                "avg": round(sum(values) / len(values), 2),
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }

    return {
        "data_type": "aggregation",
        "columns": numeric_cols,
        "aggregations": aggregations,
        "row_count": len(rows),
    }


def _execute_comparison(rows: list[dict[str, Any]], columns: list[str]) -> dict[str, Any]:
    """Group by a categorical column and aggregate."""
    if not rows:
        return {"data_type": "comparison", "groups": {}, "row_count": 0}

    # Find group column
    group_col = None
    if "category" in columns:
        group_col = "category"
    else:
        for col in columns:
            val = rows[0].get(col)
            if isinstance(val, str) and col not in ("product_id", "name", "id"):
                group_col = col
                break

    if not group_col:
        return _execute_lookup(rows, columns)

    numeric_cols = [
        col for col in columns
        if isinstance(rows[0].get(col), (int, float)) and not isinstance(rows[0].get(col), bool)
    ]

    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get(group_col, "unknown"))
        groups.setdefault(key, []).append(row)

    comparison_data: dict[str, dict[str, Any]] = {}
    for group_key, group_rows in groups.items():
        group_agg: dict[str, Any] = {"count": len(group_rows)}
        for col in numeric_cols:
            values = [
                r.get(col, 0) for r in group_rows
                if isinstance(r.get(col), (int, float)) and not isinstance(r.get(col), bool)
            ]
            if values:
                group_agg[col] = {
                    "sum": round(sum(values), 2),
                    "avg": round(sum(values) / len(values), 2),
                }
        comparison_data[group_key] = group_agg

    return {
        "data_type": "comparison",
        "group_by": group_col,
        "columns": numeric_cols,
        "groups": comparison_data,
        "row_count": len(rows),
    }


def _coerce_row(row: dict[str, str]) -> dict[str, Any]:
    """Coerce CSV string values to appropriate Python types."""
    result: dict[str, Any] = {}
    for key, value in row.items():
        if value.lower() in ("true", "false"):
            result[key] = value.lower() == "true"
        else:
            try:
                result[key] = int(value)
            except ValueError:
                try:
                    result[key] = float(value)
                except ValueError:
                    result[key] = value
    return result


# --- FastAPI Application ---

app = FastAPI(
    title="Unified Spoke Agent",
    description="Deterministic data agent that queries financial data and product catalog based on entity_refs.",
    version="1.0.0",
)


class InvokeRequest(BaseModel):
    """Request body for the agent invoke endpoint."""
    structured_intent: dict


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": AGENT_ID,
        "port": AGENT_A_PORT,
        "data_sources": ["financial_data.json", "product_catalog.csv"],
    }


@app.post(f"/agents/{AGENT_ID}/invoke")
@observability_decorator("spoke_agent")
async def invoke_agent(request: Request, body: InvokeRequest) -> JSONResponse:
    """Invoke the unified spoke agent with a structured intent.

    Uses deterministic entity_ref-based routing to query the correct
    data source(s). No LLM call — the entity_refs from the NLP translator
    already tell us which data to fetch.

    Args:
        request: The inbound FastAPI request.
        body: Request body with the structured intent.

    Returns:
        JSONResponse with AgentResult (200).
    """
    correlation_id = extract_correlation_id(request)

    try:
        intent = StructuredIntent.model_validate(body.structured_intent)
    except Exception as e:
        result = AgentResult(
            status="error",
            payload=None,
            error_type="INVALID_INTENT",
            error_description=f"Failed to parse structured intent: {e}",
            agent_id=AGENT_ID,
            data_source="multi-source",
        )
        return JSONResponse(status_code=200, content=result.model_dump(mode="json"))

    # Direct deterministic query — entity_refs already identify the data source
    result = _fallback_direct_query(intent)

    return JSONResponse(status_code=200, content=result.model_dump(mode="json"))


# --- Helper functions ---


def _fallback_direct_query(intent: StructuredIntent) -> AgentResult:
    """Fallback: deterministically query based on entity_refs without LLM.

    Args:
        intent: The structured intent.

    Returns:
        AgentResult with structured data.
    """
    financial_entities = {"ontology:sales_revenue", "ontology:quarterly_report",
                          "ontology:order_volume", "ontology:return_rate", "ontology:region"}
    product_entities = {"ontology:product_catalog", "ontology:inventory_stock",
                        "ontology:product_pricing", "ontology:supplier_info", "ontology:product_category"}

    intent_entities = set(intent.entity_refs)
    needs_financial = bool(intent_entities & financial_entities)
    needs_product = bool(intent_entities & product_entities)

    if not needs_financial and not needs_product:
        needs_financial = True

    payloads = []
    data_source = "multi-source"

    if needs_financial:
        result_json = query_financial_data(
            query_type=intent.query_type,
            entity_refs=intent.entity_refs,
        )
        fin_result = json.loads(result_json)
        if fin_result.get("status") == "success":
            payloads.append(fin_result)
            data_source = fin_result.get("data_source", "financial_data.json")

    if needs_product:
        result_json = query_product_catalog(
            query_type=intent.query_type,
            entity_refs=intent.entity_refs,
        )
        prod_result = json.loads(result_json)
        if prod_result.get("status") == "success":
            payloads.append(prod_result)
            data_source = prod_result.get("data_source", "product_catalog.csv")

    if not payloads:
        return AgentResult(
            status="error", payload=None,
            error_type="DATA_SOURCE_ERROR",
            error_description="All data source queries failed.",
            agent_id=AGENT_ID, data_source="multi-source",
        )
    elif len(payloads) == 1:
        return AgentResult(
            status="success", payload=payloads[0],
            agent_id=AGENT_ID, data_source=data_source,
        )
    else:
        return AgentResult(
            status="success",
            payload={"data_type": "comparison", "sources": payloads,
                     "row_count": sum(p.get("row_count", 0) for p in payloads)},
            agent_id=AGENT_ID, data_source="multi-source",
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=AGENT_A_PORT)
