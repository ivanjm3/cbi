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
        filtered_rows = _filter_rows_dict(rows, entity_refs, json.loads(filters) if filters else None)
        payload = _execute_query(query_type, filtered_rows, columns, json.loads(filters) if filters else None)

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

        filtered_rows = _filter_rows_dict(rows, entity_refs, json.loads(filters) if filters else None)
        payload = _execute_query(query_type, filtered_rows, columns, json.loads(filters) if filters else None)

        return json.dumps({"status": "success", "data_source": "product_catalog.csv", **payload})

    except Exception as e:
        return json.dumps({"status": "error", "error": str(e), "data_source": "product_catalog.csv"})


# --- Shared query execution helpers ---


def _filter_rows_dict(
    rows: list[dict[str, Any]],
    entity_refs: list[str],
    routing_metadata: dict | None = None,
) -> list[dict[str, Any]]:
    """Filter rows by column-value conditions extracted from routing_metadata.

    Applies WHERE-style filtering using query_text values parsed against
    known column patterns (quarter, region, category, supplier, dates,
    numeric thresholds, booleans) before falling back to entity-ref keyword
    matching.

    Args:
        rows: Raw data rows from the data source.
        entity_refs: Ontology concept IDs (used as fallback filter).
        routing_metadata: StructuredIntent routing_metadata containing
            query_text, target_columns, and other hints from the NLP layer.

    Returns:
        Filtered list of rows matching the conditions.
    """
    import re

    if not rows:
        return rows

    # --- Step 1: Extract column-value filters from query_text ---
    conditions: list[tuple[str, str, str]] = []  # (column, operator, value)
    # operator: "eq" (contains/equals), "lt" (less than), "gt" (greater than)

    if routing_metadata:
        query_text = routing_metadata.get("query_text", "").lower()

        # Detect columns available in the data
        sample_row = rows[0] if rows else {}
        available_cols = set(sample_row.keys())

        # --- Quarter filter: Q1-Q4 + optional year ---
        quarter_matches = re.findall(r'\b(q[1-4])\s*(20\d{2})?\b', query_text)
        for qm in quarter_matches:
            quarter_val = qm[0].upper()
            if qm[1]:
                quarter_val = f"{quarter_val} {qm[1]}"
            conditions.append(("quarter", "eq", quarter_val))

        # --- Year-only filter: "in 2024" without quarter ---
        if "quarter" in available_cols and not quarter_matches:
            year_matches = re.findall(r'\b(20\d{2})\b', query_text)
            for year in year_matches:
                conditions.append(("quarter", "eq", year))

        # --- Region filter ---
        known_regions = ["north america", "europe"]
        if "region" in available_cols or "supplier_region" in available_cols:
            for region in known_regions:
                if region in query_text:
                    col = "region" if "region" in available_cols else "supplier_region"
                    conditions.append((col, "eq", region.title()))

        # --- Category filter ---
        known_categories = ["electronics", "office furniture", "office supplies",
                            "software", "networking"]
        if "category" in available_cols:
            for cat in known_categories:
                if cat in query_text:
                    conditions.append(("category", "eq", cat.title()))

        # --- Supplier filter ---
        if "supplier" in available_cols:
            # Check if any supplier name from the data appears in query
            supplier_names = set(str(r.get("supplier", "")).lower() for r in rows)
            for sup in supplier_names:
                if sup and len(sup) > 3 and sup in query_text:
                    conditions.append(("supplier", "eq", sup))
                    break

        # --- Boolean / is_active filter ---
        if "is_active" in available_cols:
            if "active" in query_text and "inactive" not in query_text:
                conditions.append(("is_active", "eq", "true"))
            elif "inactive" in query_text:
                conditions.append(("is_active", "eq", "false"))

        # --- Numeric threshold filters: "below X", "above X", "less than X" ---
        lt_match = re.search(r'(?:below|under|less than|fewer than|<)\s*(\d+(?:\.\d+)?)', query_text)
        gt_match = re.search(r'(?:above|over|more than|greater than|exceeds?|>)\s*(\d+(?:\.\d+)?)', query_text)

        if lt_match:
            threshold = float(lt_match.group(1))
            # Guess which column: "stock below 50" → stock_quantity
            if "stock" in query_text and "stock_quantity" in available_cols:
                conditions.append(("stock_quantity", "lt", str(threshold)))
            elif "price" in query_text and "unit_price" in available_cols:
                conditions.append(("unit_price", "lt", str(threshold)))

        if gt_match:
            threshold = float(gt_match.group(1))
            if "stock" in query_text and "stock_quantity" in available_cols:
                conditions.append(("stock_quantity", "gt", str(threshold)))
            elif "price" in query_text and "unit_price" in available_cols:
                conditions.append(("unit_price", "gt", str(threshold)))

        # --- Date/month filter: "January 2025", "restocked in March" ---
        if "last_restocked" in available_cols:
            months = {
                "january": "01", "february": "02", "march": "03", "april": "04",
                "may": "05", "june": "06", "july": "07", "august": "08",
                "september": "09", "october": "10", "november": "11", "december": "12",
            }
            for month_name, month_num in months.items():
                if month_name in query_text:
                    year_match = re.search(r'\b(20\d{2})\b', query_text)
                    year_str = year_match.group(1) if year_match else ""
                    date_prefix = f"{year_str}-{month_num}" if year_str else f"-{month_num}-"
                    conditions.append(("last_restocked", "eq", date_prefix))
                    break

    # --- Step 2: Apply conditions ---
    if conditions:
        filtered = []
        for row in rows:
            match = True
            for col, op, val in conditions:
                if col not in row:
                    # Skip conditions for columns not in this dataset
                    continue
                row_val = row.get(col, "")
                row_val_str = str(row_val).lower()
                val_lower = val.lower()

                if op == "eq":
                    if val_lower not in row_val_str:
                        match = False
                        break
                elif op == "lt":
                    try:
                        if float(row_val) >= float(val):
                            match = False
                            break
                    except (ValueError, TypeError):
                        match = False
                        break
                elif op == "gt":
                    try:
                        if float(row_val) <= float(val):
                            match = False
                            break
                    except (ValueError, TypeError):
                        match = False
                        break
            if match:
                filtered.append(row)
        if filtered:
            return filtered

    # --- Step 3: Fallback — entity-ref keyword matching ---
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
    query_type: str,
    rows: list[dict[str, Any]],
    columns: list[str],
    routing_metadata: dict | None = None,
) -> dict[str, Any]:
    """Execute a query based on type."""
    if query_type == "aggregation":
        return _execute_aggregation(rows, columns, routing_metadata)
    elif query_type == "comparison":
        return _execute_comparison(rows, columns, routing_metadata)
    else:
        return _execute_lookup(rows, columns, routing_metadata)


def _execute_lookup(rows: list[dict[str, Any]], columns: list[str], routing_metadata: dict | None = None) -> dict[str, Any]:
    """Return filtered rows, optionally sorted by a numeric column.

    Detects sort intent from query_text (e.g. "most expensive", "sorted by stock").
    """
    import re

    sorted_rows = rows

    if routing_metadata:
        query_text = routing_metadata.get("query_text", "").lower()

        # Detect sort/rank intent
        sort_col = None
        descending = True  # default: "most", "highest", "top" → DESC

        # "sorted by X" or "order by X"
        sort_match = re.search(r'(?:sorted?|order(?:ed)?)\s+by\s+(\w+)', query_text)
        if sort_match:
            hint = sort_match.group(1)
            # Map hint to actual column
            for col in columns:
                if hint in col.lower():
                    sort_col = col
                    break

        # "most expensive" → unit_price DESC
        if "expensive" in query_text or "highest price" in query_text:
            for col in ["unit_price", "price"]:
                if col in columns:
                    sort_col = col
                    descending = True
                    break
        elif "cheapest" in query_text or "lowest price" in query_text:
            for col in ["unit_price", "price"]:
                if col in columns:
                    sort_col = col
                    descending = False
                    break

        if sort_col and sort_col in columns:
            sorted_rows = sorted(
                rows,
                key=lambda r: (
                    float(r.get(sort_col, 0))
                    if isinstance(r.get(sort_col), (int, float))
                    else 0
                ),
                reverse=descending,
            )

    return {
        "data_type": "tabular",
        "columns": columns,
        "rows": [[row.get(col) for col in columns] for row in sorted_rows],
        "row_count": len(sorted_rows),
    }


def _execute_aggregation(
    rows: list[dict[str, Any]],
    columns: list[str],
    routing_metadata: dict | None = None,
) -> dict[str, Any]:
    """Compute aggregations, optionally grouped by a column from routing hints.

    When routing_metadata contains a group_by_hint (e.g. ["quarter"]),
    groups the rows by that column and returns per-group aggregations as
    tabular data so the UI can chart them properly.

    Also infers grouping from query_text patterns like "by department",
    "by category", "by region".
    """
    import re

    if not rows:
        return {"data_type": "aggregation", "aggregations": {}, "row_count": 0}

    # Check for a group-by hint from the NLP layer
    group_col = None
    if routing_metadata:
        hints = routing_metadata.get("group_by_hint", [])
        # Pick the first hint that is actually a column in this dataset
        for hint in (hints if isinstance(hints, list) else [hints]):
            if hint in columns:
                group_col = hint
                break

        # If no explicit hint, infer from "by X" in query text
        if not group_col:
            query_text = routing_metadata.get("query_text", "").lower()
            by_match = re.search(r'\bby\s+(\w+(?:\s+\w+)?)', query_text)
            if by_match:
                by_term = by_match.group(1).strip()
                # Map common phrases to column names
                term_map = {
                    "region": "region",
                    "category": "category",
                    "quarter": "quarter",
                    "supplier": "supplier",
                    "supplier region": "supplier_region",
                }
                if by_term in term_map and term_map[by_term] in columns:
                    group_col = term_map[by_term]
                else:
                    # Try direct match or underscore variant
                    for col in columns:
                        if by_term == col or by_term.replace(" ", "_") == col:
                            group_col = col
                            break

    numeric_cols = [
        col for col in columns
        if isinstance(rows[0].get(col), (int, float)) and not isinstance(rows[0].get(col), bool)
    ]

    # Determine aggregate function from query text
    agg_fn = "sum"
    if routing_metadata:
        query_text = routing_metadata.get("query_text", "").lower()
        if any(kw in query_text for kw in ["average", "avg", "mean"]):
            agg_fn = "avg"
        elif any(kw in query_text for kw in ["maximum", "max", "highest", "most", "top"]):
            agg_fn = "max"
        elif any(kw in query_text for kw in ["minimum", "min", "lowest", "least"]):
            agg_fn = "min"

    # Grouped aggregation — return tabular breakdown
    if group_col:
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = str(row.get(group_col, "unknown"))
            groups.setdefault(key, []).append(row)

        result_rows = []
        result_columns = [group_col] + numeric_cols
        for group_key, group_rows in sorted(groups.items()):
            agg_row: list[Any] = [group_key]
            for col in numeric_cols:
                values = [
                    r[col] for r in group_rows
                    if isinstance(r.get(col), (int, float)) and not isinstance(r.get(col), bool)
                ]
                if values:
                    if agg_fn == "avg":
                        agg_row.append(round(sum(values) / len(values), 2))
                    elif agg_fn == "max":
                        agg_row.append(max(values))
                    elif agg_fn == "min":
                        agg_row.append(min(values))
                    else:
                        agg_row.append(round(sum(values), 2))
                else:
                    agg_row.append(0)
            result_rows.append(agg_row)

        return {
            "data_type": "tabular",
            "columns": result_columns,
            "rows": result_rows,
            "row_count": len(result_rows),
            "group_by": group_col,
        }

    # Scalar aggregation over all rows
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


def _execute_comparison(
    rows: list[dict[str, Any]],
    columns: list[str],
    routing_metadata: dict | None = None,
) -> dict[str, Any]:
    """Group by a categorical column and aggregate.

    Uses group_by_hint from routing_metadata when available (e.g. "quarter")
    to compare the right dimension. Also inspects query_text for contextual
    clues ("between North America and Europe" → group by region).
    Falls back to "quarter" → "category" → first string col.
    """
    if not rows:
        return {"data_type": "comparison", "groups": {}, "row_count": 0}

    # Determine group column: routing hint → query context → defaults
    group_col = None
    if routing_metadata:
        hints = routing_metadata.get("group_by_hint", [])
        for hint in (hints if isinstance(hints, list) else [hints]):
            if hint in columns:
                group_col = hint
                break

        # If no explicit hint, infer from query context
        if not group_col:
            query_text = routing_metadata.get("query_text", "").lower()
            # "between North America and Europe" → region comparison
            if "region" in columns and any(
                r in query_text for r in ["north america", "europe", "by region", "between"]
            ):
                # Check if two regions are mentioned
                regions_mentioned = sum(
                    1 for r in ["north america", "europe"] if r in query_text
                )
                if regions_mentioned >= 2 or "by region" in query_text:
                    group_col = "region"
            # "Q1 vs Q4" → quarter comparison
            if not group_col and "quarter" in columns:
                import re
                if re.search(r'q[1-4]\s*(?:vs|versus|and|compared)', query_text):
                    group_col = "quarter"

    if not group_col:
        if "quarter" in columns:
            group_col = "quarter"
        elif "category" in columns:
            group_col = "category"
        else:
            for col in columns:
                val = rows[0].get(col)
                if isinstance(val, str) and col not in ("product_id", "name", "id"):
                    group_col = col
                    break

    if not group_col:
        return _execute_lookup(rows, columns, routing_metadata)

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

    Checks for upstream disconnection before executing S3/file I/O and
    returns CANCELLED status if detected.

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

    # Check for upstream disconnection before expensive I/O operations
    if await request.is_disconnected():
        logger.info(f"Client disconnected before data source query, correlation_id={correlation_id}")
        result = AgentResult(
            status="CANCELLED",
            payload=None,
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
            filters=json.dumps(intent.routing_metadata),
        )
        fin_result = json.loads(result_json)
        if fin_result.get("status") == "success":
            payloads.append(fin_result)
            data_source = fin_result.get("data_source", "financial_data.json")

    if needs_product:
        result_json = query_product_catalog(
            query_type=intent.query_type,
            entity_refs=intent.entity_refs,
            filters=json.dumps(intent.routing_metadata),
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
