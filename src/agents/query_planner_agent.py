"""Query Planner Agent — Strands SDK agent for multi-source data retrieval.

Replaces the NLP Translator + Orchestrator Hub two-service architecture with
a single Strands agent that interprets natural language queries, reasons about
the ontology and source registry, produces an Execution Plan, and executes
queries against data source connectors.

Returns an OrchestratorResponse that the existing Guardrail → Visualization
pipeline accepts unchanged.

Requirements: 1.1, 1.2, 1.4, 1.5, 7.1, 7.2, 7.3, 7.5, 9.4
"""

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from strands import Agent, tool

from src.config import (
    DEFAULT_MODEL_ID,
    S3_BUCKET,
    get_s3_client,
    get_strands_bedrock_model,
)
from src.models.session_context import SessionContext
from src.models.shared import AgentResult, OrchestratorResponse
from src.services.bedrock_wrapper import track_agent_invocation
from src.services.ontology_store import OntologyStore

logger = logging.getLogger(__name__)

AGENT_ID = "query-planner"
S3_FINANCIAL_KEY = "data-sources/financial_data.json"
S3_PRODUCT_KEY = "data-sources/product_catalog.csv"


# ---------------------------------------------------------------------------
# System prompt for the Query Planner Agent
# ---------------------------------------------------------------------------

QUERY_PLANNER_SYSTEM_PROMPT = """\
You are a Query Planner Agent responsible for interpreting natural language \
queries about enterprise data and executing them against the appropriate data sources.

## Your Capabilities

You have access to:
1. An enterprise ontology with concepts covering financial data (sales revenue, \
order volume, return rates, quarterly reports) and product data (catalog, inventory, \
pricing, suppliers).
2. Data source tools that can query specific backends.

## Available Ontology Concepts

**Financial Domain** (source: financial_data.json):
- ontology:sales_revenue — Revenue from product sales, tracked quarterly by region \
and category
- ontology:order_volume — Number of customer orders, tracked quarterly by region \
and category
- ontology:return_rate — Percentage of returns, tracked quarterly by region and category
- ontology:quarterly_report — Aggregated financial performance by quarter

**Product Domain** (source: product_catalog.csv):
- ontology:product_catalog — Complete product listing with prices, stock, suppliers
- ontology:inventory_stock — Current stock quantities by category and supplier
- ontology:product_pricing — Unit prices and costs for margin calculations
- ontology:supplier_info — Supplier names and regions

**Shared Dimensions**:
- ontology:product_category — Categories: Electronics, Office Furniture, Office Supplies
- ontology:region — Regions: North America, Europe

## Workflow

1. First, use `lookup_ontology` to understand which concepts relate to the user's query.
2. Then, use the appropriate query tool (`query_s3_json_source` for financial data, \
or `query_s3_json_source` for product catalog) to retrieve the data.
3. Return the data results clearly.

## Query Types

Classify the user's query as one of:
- **lookup**: User wants specific data points or records
- **aggregation**: User wants summaries, totals, averages, trends
- **comparison**: User wants to compare entities, time periods, or data sets

## Rules

- Always start by looking up ontology concepts to understand what data is available.
- Choose the correct data source based on the ontology concept's domain.
- For financial queries (revenue, sales, orders, returns): use financial_data source.
- For product queries (catalog, inventory, pricing, suppliers): use product_catalog source.
- For cross-domain queries: query both sources and present combined results.
- If the query is too vague to determine which data to retrieve, request clarification \
by explaining what types of data are available.
- Always include the data_source in your results for traceability.
"""


# ---------------------------------------------------------------------------
# Tool definitions (module-level functions decorated with @tool)
# ---------------------------------------------------------------------------

# Module-level state for tools to access
_ontology_store: OntologyStore | None = None


@tool
def lookup_ontology(keyword: str) -> str:
    """Search the enterprise ontology for concepts matching a keyword.

    Use this tool to understand which data concepts relate to the user's query.
    Returns matching concepts with their descriptions and data source information.

    Args:
        keyword: A search term to find relevant ontology concepts (e.g., "revenue",
                 "product", "inventory", "sales").

    Returns:
        JSON string with matching ontology concepts and their metadata.
    """
    if _ontology_store is None:
        return json.dumps({"error": "Ontology store not initialized"})

    try:
        concepts = _ontology_store.search_concepts(keyword)
        results = []
        for concept in concepts:
            results.append({
                "concept_id": concept.concept_id,
                "label": concept.label,
                "domain": concept.properties.get("domain", "unknown"),
                "description": concept.properties.get("description", ""),
                "data_source": concept.properties.get("data_source", ""),
                "aggregatable": concept.properties.get("aggregatable", False),
            })

        if not results:
            return json.dumps({
                "status": "no_matches",
                "message": f"No ontology concepts found for keyword '{keyword}'.",
                "suggestion": "Try broader terms like 'revenue', 'product', 'sales', 'inventory'.",
            })

        return json.dumps({"status": "success", "concepts": results, "count": len(results)})
    except Exception as e:
        logger.error(json.dumps({
            "service_name": "query_planner",
            "operation": "lookup_ontology",
            "error": str(e),
        }))
        return json.dumps({"error": f"Ontology lookup failed: {str(e)}"})


@tool
def search_sources(concept_ids: str) -> str:
    """Search the source registry for data sources that provide data for given concepts.

    Use this to find which data sources contain information about specific
    ontology concepts.

    Args:
        concept_ids: Comma-separated list of ontology concept IDs
                     (e.g., "ontology:sales_revenue,ontology:order_volume").

    Returns:
        JSON string with matching data sources and their configurations.
    """
    # Phase 1: Return hardcoded source mappings based on ontology properties
    financial_concepts = {
        "ontology:sales_revenue", "ontology:order_volume",
        "ontology:return_rate", "ontology:quarterly_report",
    }
    product_concepts = {
        "ontology:product_catalog", "ontology:inventory_stock",
        "ontology:product_pricing", "ontology:supplier_info",
    }
    shared_concepts = {"ontology:product_category", "ontology:region"}

    ids = [c.strip() for c in concept_ids.split(",")]
    id_set = set(ids)

    sources = []
    if id_set & financial_concepts or id_set & shared_concepts:
        sources.append({
            "source_id": "s3-financial-data",
            "source_name": "Financial Data (S3 JSON)",
            "connector_type": "s3_json",
            "data_source_file": "financial_data.json",
            "concepts_served": list(financial_concepts | shared_concepts),
        })
    if id_set & product_concepts or id_set & shared_concepts:
        sources.append({
            "source_id": "s3-product-catalog",
            "source_name": "Product Catalog (S3 CSV)",
            "connector_type": "s3_json",
            "data_source_file": "product_catalog.csv",
            "concepts_served": list(product_concepts | shared_concepts),
        })

    return json.dumps({"status": "success", "sources": sources, "count": len(sources)})


@tool
def query_rds_source(source_id: str, sql_query: str) -> str:
    """Execute a parameterized SQL query against a registered RDS data source.

    Args:
        source_id: The registered source identifier for the RDS instance.
        sql_query: The SQL query to execute (SELECT only).

    Returns:
        JSON string with query results or error details.
    """
    return json.dumps({
        "status": "error",
        "error_type": "SOURCE_NOT_CONFIGURED",
        "error_description": (
            f"RDS source '{source_id}' is not configured in Phase 1. "
            "RDS connectors will be available in Phase 2."
        ),
    })


@tool
def query_dynamodb_source(table_name: str, key_condition: str, filter_expression: str = "") -> str:
    """Execute a query or scan against a registered DynamoDB table.

    Args:
        table_name: The DynamoDB table name to query.
        key_condition: Key condition expression for the query.
        filter_expression: Optional filter expression for additional filtering.

    Returns:
        JSON string with query results or error details.
    """
    return json.dumps({
        "status": "error",
        "error_type": "SOURCE_NOT_CONFIGURED",
        "error_description": (
            f"DynamoDB source '{table_name}' is not configured in Phase 1. "
            "DynamoDB connectors will be available in Phase 2."
        ),
    })


@tool
def query_s3_csv_source(bucket: str, key: str, filters: str = "") -> str:
    """Read and filter a CSV file from S3.

    Args:
        bucket: The S3 bucket name.
        key: The S3 object key for the CSV file.
        filters: Optional JSON string of column filters.

    Returns:
        JSON string with parsed CSV data or error details.
    """
    return json.dumps({
        "status": "error",
        "error_type": "SOURCE_NOT_CONFIGURED",
        "error_description": (
            f"S3 CSV source '{key}' is not configured in Phase 1. "
            "S3 CSV connectors will be available in Phase 2."
        ),
    })


@tool
def query_log_source(bucket: str, key: str, time_range: str = "", level_filter: str = "") -> str:
    """Parse and filter structured log files from S3.

    Args:
        bucket: The S3 bucket name containing the log file.
        key: The S3 object key for the log file (JSON-lines format).
        time_range: Optional time range filter (ISO 8601 start,end).
        level_filter: Optional log level filter (e.g., "ERROR", "WARN").

    Returns:
        JSON string with parsed log entries or error details.
    """
    return json.dumps({
        "status": "error",
        "error_type": "SOURCE_NOT_CONFIGURED",
        "error_description": (
            f"Log source '{key}' is not configured in Phase 1. "
            "Log connectors will be available in Phase 2."
        ),
    })


@tool
def query_s3_json_source(data_source: str, query_type: str, entity_refs: str, filters: str = "") -> str:
    """Query JSON or CSV data from S3 for financial or product data.

    This is the primary data retrieval tool for Phase 1. It queries either
    the financial data (JSON) or product catalog (CSV) from S3.

    Args:
        data_source: The data source to query. Must be one of:
                     "financial_data" or "product_catalog".
        query_type: One of "lookup", "aggregation", or "comparison".
        entity_refs: Comma-separated ontology concept IDs to filter results
                     (e.g., "ontology:sales_revenue,ontology:region").
        filters: Optional JSON string of additional filters.

    Returns:
        JSON string with query results including columns, rows, and metadata.
    """
    entity_ref_list = [e.strip() for e in entity_refs.split(",") if e.strip()]

    if data_source == "financial_data":
        return _query_financial_data(query_type, entity_ref_list, filters)
    elif data_source == "product_catalog":
        return _query_product_catalog(query_type, entity_ref_list, filters)
    else:
        return json.dumps({
            "status": "error",
            "error_type": "UNKNOWN_SOURCE",
            "error_description": (
                f"Unknown data source '{data_source}'. "
                "Available sources: 'financial_data', 'product_catalog'."
            ),
        })


# ---------------------------------------------------------------------------
# S3 data query implementations (ported from spoke_agent.py)
# ---------------------------------------------------------------------------


def _query_financial_data(
    query_type: str, entity_refs: list[str], filters: str = ""
) -> str:
    """Query the financial JSON data source from S3.

    Contains quarterly sales revenue, order volume, and return rate data
    broken down by product category and region.
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

        return json.dumps({
            "status": "success",
            "data_source": "financial_data.json",
            **payload,
        })
    except Exception as e:
        logger.error(json.dumps({
            "service_name": "query_planner",
            "operation": "query_financial_data",
            "error": str(e),
        }))
        return json.dumps({
            "status": "error",
            "error_type": "DATA_SOURCE_ERROR",
            "error_description": str(e),
            "data_source": "financial_data.json",
        })


def _query_product_catalog(
    query_type: str, entity_refs: list[str], filters: str = ""
) -> str:
    """Query the product catalog CSV data source from S3.

    Contains product names, categories, prices, stock quantities,
    and supplier details.
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

        return json.dumps({
            "status": "success",
            "data_source": "product_catalog.csv",
            **payload,
        })
    except Exception as e:
        logger.error(json.dumps({
            "service_name": "query_planner",
            "operation": "query_product_catalog",
            "error": str(e),
        }))
        return json.dumps({
            "status": "error",
            "error_type": "DATA_SOURCE_ERROR",
            "error_description": str(e),
            "data_source": "product_catalog.csv",
        })


# ---------------------------------------------------------------------------
# Query execution helpers (ported from spoke_agent.py)
# ---------------------------------------------------------------------------


def _filter_rows_dict(
    rows: list[dict[str, Any]], entity_refs: list[str]
) -> list[dict[str, Any]]:
    """Filter rows relevant to the entity references."""
    if not entity_refs:
        return rows

    keywords = [
        ref.replace("ontology:", "").replace("_", " ").lower()
        for ref in entity_refs
    ]

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
        if isinstance(rows[0].get(col), (int, float))
        and not isinstance(rows[0].get(col), bool)
    ]

    aggregations: dict[str, dict[str, Any]] = {}
    for col in numeric_cols:
        values = [
            row.get(col, 0) for row in rows
            if isinstance(row.get(col), (int, float))
            and not isinstance(row.get(col), bool)
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
        if isinstance(rows[0].get(col), (int, float))
        and not isinstance(rows[0].get(col), bool)
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
                if isinstance(r.get(col), (int, float))
                and not isinstance(r.get(col), bool)
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


# ---------------------------------------------------------------------------
# Fallback deterministic routing (Requirement 9.4)
# ---------------------------------------------------------------------------

# Stop words for keyword extraction (reused from NLP Translator)
_STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above",
    "below", "between", "and", "but", "or", "not", "no", "nor",
    "so", "yet", "both", "either", "neither", "each", "every",
    "all", "any", "few", "more", "most", "other", "some", "such",
    "than", "too", "very", "just", "about", "also", "how", "what",
    "which", "who", "whom", "this", "that", "these", "those", "am",
    "it", "its", "i", "me", "my", "we", "our", "you", "your",
    "he", "him", "his", "she", "her", "they", "them", "their",
    "show", "tell", "give", "get", "find", "list", "display",
    "many", "much",
}

# Entity routing sets (same as spoke_agent.py)
_FINANCIAL_ENTITIES = {
    "ontology:sales_revenue", "ontology:quarterly_report",
    "ontology:order_volume", "ontology:return_rate", "ontology:region",
}
_PRODUCT_ENTITIES = {
    "ontology:product_catalog", "ontology:inventory_stock",
    "ontology:product_pricing", "ontology:supplier_info",
    "ontology:product_category",
}


def _extract_keywords(query_text: str) -> list[str]:
    """Extract meaningful keywords from query text for ontology search.

    Performs tokenization and stop word removal to identify candidate
    terms for ontology concept matching.
    """
    words = query_text.lower().split()
    cleaned = []
    for word in words:
        cleaned_word = word.strip(".,;:!?\"'()[]{}")
        if cleaned_word and cleaned_word not in _STOP_WORDS and len(cleaned_word) > 1:
            cleaned.append(cleaned_word)

    # Also try bigrams for compound concept matching
    bigrams = []
    for i in range(len(cleaned) - 1):
        bigrams.append(f"{cleaned[i]} {cleaned[i + 1]}")

    return cleaned + bigrams


def _resolve_entities(query_text: str, ontology_store: OntologyStore) -> list[str]:
    """Resolve entity references from query text against the ontology.

    Extracts keywords and searches the ontology for matching concepts.
    Returns canonical concept identifiers.
    """
    keywords = _extract_keywords(query_text)
    resolved_ids: list[str] = []
    seen: set[str] = set()

    for keyword in keywords:
        concepts = ontology_store.search_concepts(keyword)
        for concept in concepts:
            if concept.concept_id not in seen:
                resolved_ids.append(concept.concept_id)
                seen.add(concept.concept_id)

    return resolved_ids


def _classify_query_type(query_text: str) -> str:
    """Classify query type using keyword heuristics (no LLM).

    Used in fallback path when the agent is unavailable.
    """
    text = query_text.lower()

    comparison_signals = [
        "compare", "comparison", "versus", " vs ", " vs.", "difference",
        "between", "against", "relative to", "compared to", "contrast",
    ]
    aggregation_signals = [
        "total", "sum", "average", "avg", "count", "how many",
        "trend", "over time", "growth", "aggregate", "overall",
        "breakdown", "distribution", "percentage", "proportion",
        "minimum", "maximum", "median", "mean",
    ]

    if any(s in text for s in comparison_signals):
        return "comparison"
    if any(s in text for s in aggregation_signals):
        return "aggregation"
    return "lookup"


def _fallback_deterministic_query(
    query_text: str, ontology_store: OntologyStore
) -> OrchestratorResponse:
    """Fallback deterministic routing when agent fails (Requirement 9.4).

    Mirrors the NLP Translator + Spoke Agent logic:
    1. Extract keywords from query text
    2. Resolve entities against ontology
    3. Route to the appropriate data source based on entity_refs
    4. Return a valid OrchestratorResponse
    """
    query_id = uuid.uuid4()

    # Step 1 & 2: Extract keywords and resolve entities
    entity_refs = _resolve_entities(query_text, ontology_store)

    # Step 3: Classify query type
    query_type = _classify_query_type(query_text)

    # Step 4: Route to appropriate source(s)
    intent_entities = set(entity_refs)
    needs_financial = bool(intent_entities & _FINANCIAL_ENTITIES)
    needs_product = bool(intent_entities & _PRODUCT_ENTITIES)

    # Default to financial if no clear match
    if not needs_financial and not needs_product:
        needs_financial = True

    payloads = []
    data_source = "multi-source"

    if needs_financial:
        result_json = _query_financial_data(query_type, entity_refs)
        fin_result = json.loads(result_json)
        if fin_result.get("status") == "success":
            payloads.append(fin_result)
            data_source = fin_result.get("data_source", "financial_data.json")

    if needs_product:
        result_json = _query_product_catalog(query_type, entity_refs)
        prod_result = json.loads(result_json)
        if prod_result.get("status") == "success":
            payloads.append(prod_result)
            data_source = prod_result.get("data_source", "product_catalog.csv")

    if not payloads:
        return OrchestratorResponse(
            query_id=query_id,
            results=[AgentResult(
                status="error",
                payload=None,
                error_type="DATA_SOURCE_ERROR",
                error_description="All data source queries failed in fallback mode.",
                agent_id=AGENT_ID,
                data_source="multi-source",
            )],
            unavailable_agents=[],
        )
    elif len(payloads) == 1:
        return OrchestratorResponse(
            query_id=query_id,
            results=[AgentResult(
                status="success",
                payload=payloads[0],
                agent_id=AGENT_ID,
                data_source=data_source,
            )],
            unavailable_agents=[],
        )
    else:
        combined_payload = {
            "data_type": "comparison",
            "sources": payloads,
            "row_count": sum(p.get("row_count", 0) for p in payloads),
        }
        return OrchestratorResponse(
            query_id=query_id,
            results=[AgentResult(
                status="success",
                payload=combined_payload,
                agent_id=AGENT_ID,
                data_source="multi-source",
            )],
            unavailable_agents=[],
        )


# ---------------------------------------------------------------------------
# QueryPlannerAgent class
# ---------------------------------------------------------------------------


class QueryPlannerAgent:
    """Single Strands Agent that replaces NLP Translator + Orchestrator Hub.

    Interprets natural language queries, reasons about ontology concepts and
    data sources, and executes queries against the appropriate connectors.
    Returns OrchestratorResponse compatible with the existing Guardrail → Viz
    pipeline.

    Requirements: 1.1, 1.2, 1.4, 1.5, 7.1, 7.2, 7.3, 7.5, 9.4
    """

    def __init__(
        self,
        ontology_store: OntologyStore | None = None,
        model_id: str | None = None,
    ):
        """Initialize the Query Planner Agent.

        Args:
            ontology_store: The ontology store for entity resolution and
                concept lookups. Defaults to a new OntologyStore instance.
            model_id: Optional Bedrock model ID override.
        """
        global _ontology_store

        self._ontology_store = ontology_store or OntologyStore()
        self._model_id = model_id or DEFAULT_MODEL_ID

        # Set module-level reference for tools to access
        _ontology_store = self._ontology_store

        # Initialize the Strands Agent
        self._agent = Agent(
            system_prompt=QUERY_PLANNER_SYSTEM_PROMPT,
            tools=[
                lookup_ontology,
                search_sources,
                query_rds_source,
                query_dynamodb_source,
                query_s3_csv_source,
                query_log_source,
                query_s3_json_source,
            ],
            model=get_strands_bedrock_model(self._model_id),
            callback_handler=None,
        )

    def plan_and_execute(
        self,
        query_text: str,
        session_context: SessionContext | None = None,
    ) -> OrchestratorResponse:
        """Main entry point: natural language query → OrchestratorResponse.

        Invokes the Strands agent to interpret the query, reason about ontology
        concepts, and execute against appropriate data sources. Falls back to
        deterministic routing if the agent fails.

        Args:
            query_text: The natural language query from the user.
            session_context: Optional conversational state for follow-up queries.

        Returns:
            OrchestratorResponse compatible with the Guardrail → Viz pipeline.
        """
        query_id = uuid.uuid4()
        correlation_id = str(query_id)

        # Validate input
        if not query_text or not query_text.strip():
            return OrchestratorResponse(
                query_id=query_id,
                results=[AgentResult(
                    status="error",
                    payload=None,
                    error_type="UNPARSEABLE_QUERY",
                    error_description="Query text is empty or contains only whitespace.",
                    agent_id=AGENT_ID,
                    data_source="none",
                )],
                unavailable_agents=[],
            )

        query_text = query_text.strip()

        try:
            # Build the user prompt with session context
            prompt = self._build_agent_prompt(query_text, session_context)

            # Invoke the Strands agent
            logger.info(json.dumps({
                "service_name": "query_planner",
                "operation": "plan_and_execute",
                "event": "agent_invocation_start",
                "query_text": query_text,
                "correlation_id": correlation_id,
            }))

            result = self._agent(prompt)

            # Track cost
            track_agent_invocation(
                component="query_planner",
                model_id=self._model_id,
                response=result,
                correlation_id=correlation_id,
            )

            # Parse the agent's tool call results to build the response
            response = self._parse_agent_result(result, query_id)

            logger.info(json.dumps({
                "service_name": "query_planner",
                "operation": "plan_and_execute",
                "event": "agent_invocation_success",
                "query_id": str(query_id),
                "correlation_id": correlation_id,
                "result_count": len(response.results),
            }))

            return response

        except Exception as e:
            # Fallback to deterministic routing (Requirement 9.4)
            logger.warning(json.dumps({
                "service_name": "query_planner",
                "operation": "plan_and_execute",
                "event": "agent_fallback_triggered",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "correlation_id": correlation_id,
            }))

            return _fallback_deterministic_query(query_text, self._ontology_store)

    def _build_agent_prompt(
        self,
        query_text: str,
        session_context: SessionContext | None,
    ) -> str:
        """Build the user prompt including session history for context.

        Includes relevant conversation history so the agent can handle
        follow-up queries like "show me that by region" (Requirement 7.3).
        """
        parts = []

        # Include session history if available
        if session_context and session_context.history:
            parts.append("## Conversation History")
            # Include last 3 exchanges for context
            recent_history = session_context.history[-3:]
            for entry in recent_history:
                parts.append(f"- User asked: \"{entry.get('query', '')}\"")
                if entry.get("sources_used"):
                    parts.append(f"  Sources used: {entry.get('sources_used')}")
                if entry.get("entity_refs"):
                    parts.append(f"  Entities: {entry.get('entity_refs')}")
            parts.append("")

            # Provide last entity refs as context for follow-ups
            if session_context.last_entity_refs:
                parts.append(
                    f"Previously referenced entities: "
                    f"{', '.join(session_context.last_entity_refs)}"
                )
            if session_context.last_sources_used:
                parts.append(
                    f"Previously used data sources: "
                    f"{', '.join(session_context.last_sources_used)}"
                )
            parts.append("")

        # The actual user query
        parts.append(f"## User Query\n\n{query_text}")

        return "\n".join(parts)

    def _parse_agent_result(
        self, result: Any, query_id: uuid.UUID
    ) -> OrchestratorResponse:
        """Parse the Strands agent result into an OrchestratorResponse.

        Extracts tool call results from the agent's execution to build
        a properly structured response.
        """
        # The agent result contains the final text response.
        # We need to extract structured data from tool calls that occurred.
        # Strands agent tool results are embedded in the response.

        # Try to extract structured data from the agent's response text
        response_text = str(result)

        # Look for JSON data in the response that came from tool calls
        # The agent should have called query_s3_json_source which returns JSON
        payload = self._extract_data_payload(response_text)

        if payload and payload.get("status") == "success":
            return OrchestratorResponse(
                query_id=query_id,
                results=[AgentResult(
                    status="success",
                    payload=payload,
                    agent_id=AGENT_ID,
                    data_source=payload.get("data_source", "unknown"),
                )],
                unavailable_agents=[],
            )

        # If we can't extract structured data, check if the agent is
        # requesting clarification
        if self._is_clarification_response(response_text):
            return OrchestratorResponse(
                query_id=query_id,
                results=[AgentResult(
                    status="success",
                    payload={
                        "data_type": "clarification",
                        "message": response_text,
                        "options": self._extract_clarification_options(response_text),
                    },
                    agent_id=AGENT_ID,
                    data_source="none",
                )],
                unavailable_agents=[],
            )

        # If the agent produced a text response but no structured data,
        # fall back to deterministic routing
        logger.warning(json.dumps({
            "service_name": "query_planner",
            "operation": "_parse_agent_result",
            "event": "no_structured_data_extracted",
            "response_length": len(response_text),
        }))

        # Use fallback to ensure we always return data
        return _fallback_deterministic_query(
            result.message if hasattr(result, "message") else str(result)[:200],
            self._ontology_store,
        )

    def _extract_data_payload(self, response_text: str) -> dict[str, Any] | None:
        """Extract structured data payload from agent response.

        Searches for JSON blocks in the response that contain data
        query results (status, data_type, columns, rows, etc.).
        """
        # Try to find JSON objects in the response
        import re
        json_pattern = re.compile(r'\{[^{}]*"status"\s*:\s*"success"[^{}]*\}', re.DOTALL)

        # Try more comprehensive JSON extraction
        brace_depth = 0
        json_start = None
        candidates = []

        for i, char in enumerate(response_text):
            if char == '{':
                if brace_depth == 0:
                    json_start = i
                brace_depth += 1
            elif char == '}':
                brace_depth -= 1
                if brace_depth == 0 and json_start is not None:
                    candidate = response_text[json_start:i + 1]
                    candidates.append(candidate)
                    json_start = None

        # Find the best candidate (one with "status": "success" and data fields)
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if (
                    isinstance(parsed, dict)
                    and parsed.get("status") == "success"
                    and ("data_type" in parsed or "columns" in parsed or "rows" in parsed)
                ):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                continue

        return None

    def _is_clarification_response(self, response_text: str) -> bool:
        """Check if the agent response is requesting clarification."""
        clarification_signals = [
            "could you clarify",
            "could you specify",
            "what type of data",
            "which data source",
            "do you mean",
            "please specify",
            "i need more information",
            "can you be more specific",
            "available data types",
            "which would you like",
        ]
        text_lower = response_text.lower()
        return any(signal in text_lower for signal in clarification_signals)

    def _extract_clarification_options(self, response_text: str) -> list[str]:
        """Extract clarification options from agent response."""
        options = []
        # Look for numbered or bulleted options
        import re
        lines = response_text.split("\n")
        for line in lines:
            line = line.strip()
            if re.match(r'^[\d]+[.)]\s+', line) or re.match(r'^[-*]\s+', line):
                option_text = re.sub(r'^[\d]+[.)]\s+|^[-*]\s+', '', line).strip()
                if option_text:
                    options.append(option_text)

        if not options:
            options = [
                "Financial data (revenue, sales, orders, returns)",
                "Product data (catalog, inventory, pricing, suppliers)",
            ]
        return options
