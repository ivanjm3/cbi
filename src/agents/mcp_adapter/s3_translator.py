"""S3 Translator for the MCP Adapter Layer.

Translates StructuredIntent payloads into mcp-s3 tool calls, handles
pagination, and performs local aggregation/comparison computations on
the retrieved data.
"""

from __future__ import annotations

import logging
from typing import Any

from src.models.shared import AgentResult, StructuredIntent

from .client_manager import MCPClientManager, MCPTimeoutError, MCPUnavailableError
from .models import MCPToolResult

logger = logging.getLogger(__name__)

# Default page size for read_dataset calls
_DEFAULT_PAGE_SIZE = 1000

# Maximum rows to accumulate across pages
_MAX_ROW_LIMIT = 10000

# Columns to exclude when selecting the grouping column for comparison
_IDENTIFIER_COLUMNS = {"product_id", "name", "id", "ticket_id", "employee_id", "campaign_id"}


class S3Translator:
    """Translates StructuredIntent to mcp-s3 tool calls.

    Handles pagination of read_dataset, schema inference via get_schema or
    sample_dataset, and local aggregation/comparison computations.
    """

    def __init__(self, client: MCPClientManager, max_row_limit: int = _MAX_ROW_LIMIT) -> None:
        """Initialize the S3 translator.

        Args:
            client: MCPClientManager connected to the mcp-s3 server.
            max_row_limit: Maximum rows to paginate (default 10000).
        """
        self.client = client
        self.max_row_limit = max_row_limit
        self._schema_cache: dict[str, list[dict]] = {}

    async def execute(
        self, intent: StructuredIntent, dataset_name: str
    ) -> AgentResult:
        """Read dataset from MCP S3 server and apply query-type logic.

        Args:
            intent: The StructuredIntent with query_type information.
            dataset_name: Resolved dataset name (e.g., "financial_data").

        Returns:
            AgentResult with the appropriate data_type based on query_type.
        """
        try:
            # Ensure schema is cached for column type inference
            columns_meta = await self._ensure_schema_cached(dataset_name)

            # Read all rows with pagination
            rows, columns = await self._read_all_rows(dataset_name)

            # Apply filters from query text (e.g., "for Europe", "in Q2 2024")
            query_text = intent.routing_metadata.get("query_text", "")
            if query_text:
                rows = self._apply_query_filters(rows, columns, query_text)

            if not rows:
                return AgentResult(
                    status="success",
                    payload={
                        "data_type": _data_type_for(intent.query_type),
                        "columns": columns,
                        "rows": [],
                        "row_count": 0,
                    },
                    agent_id="mcp-s3-adapter",
                    data_source="mcp-s3",
                )

            # Optionally fetch semantic metadata for better column selection
            semantic = await self._get_semantic_metadata(dataset_name)

            # Apply query-type specific logic
            if intent.query_type == "aggregation":
                payload = self._compute_aggregation(
                    rows, columns, columns_meta, semantic
                )
            elif intent.query_type == "comparison":
                payload = self._compute_comparison(
                    rows, columns, columns_meta, semantic
                )
            else:
                # lookup — return raw rows
                payload = {
                    "data_type": "tabular",
                    "columns": columns,
                    "rows": rows,
                    "row_count": len(rows),
                }

            return AgentResult(
                status="success",
                payload=payload,
                agent_id="mcp-s3-adapter",
                data_source="mcp-s3",
            )

        except MCPTimeoutError as e:
            logger.error(
                "MCP S3 read_dataset timed out for query %s: %s",
                intent.query_id,
                str(e),
            )
            return AgentResult(
                status="error",
                error_type="MCP_TOOL_ERROR",
                error_description=f"mcp-s3 read_dataset timed out: {e}",
                agent_id="mcp-s3-adapter",
                data_source="mcp-s3",
            )

        except MCPUnavailableError:
            # Re-raise so the service layer can trigger fallback
            raise

    async def _read_all_rows(
        self, dataset_name: str
    ) -> tuple[list[list[Any]], list[str]]:
        """Read all rows from a dataset with pagination.

        Continues issuing read_dataset calls with incremented offset
        until has_more is false or max_row_limit is reached.

        Returns:
            Tuple of (accumulated_rows, column_names).
        """
        all_rows: list[list[Any]] = []
        columns: list[str] = []
        offset = 0

        while len(all_rows) < self.max_row_limit:
            result = await self.client.call_tool(
                "read_dataset",
                {
                    "dataset": dataset_name,
                    "offset": offset,
                    "limit": _DEFAULT_PAGE_SIZE,
                },
            )

            if not result.success:
                logger.error(
                    "read_dataset failed for %s at offset %d: %s",
                    dataset_name,
                    offset,
                    result.error_message,
                )
                break

            content = result.content or {}
            page_rows = content.get("rows", [])
            page_columns = content.get("columns", columns)
            has_more = content.get("has_more", False)

            if not columns and page_columns:
                columns = page_columns

            all_rows.extend(page_rows)

            if not has_more or not page_rows:
                break

            offset += len(page_rows)

        # Trim to max_row_limit
        if len(all_rows) > self.max_row_limit:
            all_rows = all_rows[: self.max_row_limit]

        return all_rows, columns

    def _apply_query_filters(
        self, rows: list[list], columns: list[str], query_text: str
    ) -> list[list]:
        """Filter rows based on dimension values mentioned in the query text.

        Scans the query text for exact matches of categorical column values
        and filters rows accordingly. Handles conditions like "for Europe"
        or "in Q2 2024" by matching column values that appear in the query.

        Args:
            rows: All data rows from the dataset.
            columns: Column name list corresponding to row positions.
            query_text: The user's original query text.

        Returns:
            Filtered rows, or original rows if no filters matched or
            filtering would remove all data.
        """
        if not query_text or not rows or not columns:
            return rows

        query_lower = query_text.lower()
        filtered = rows

        for col_idx, col_name in enumerate(columns):
            # Skip identifier columns — they have too many unique values
            if col_name.lower() in _IDENTIFIER_COLUMNS:
                continue

            # Get unique values in this column
            unique_values: set[str] = set()
            for row in rows:
                if col_idx < len(row) and row[col_idx] is not None:
                    unique_values.add(str(row[col_idx]))

            # Skip columns with too many unique values (likely not categorical)
            if len(unique_values) > 50:
                continue

            # Check if any value appears in the query text
            for val in unique_values:
                if len(val) < 2:
                    continue  # Skip very short values to avoid false matches
                if val.lower() in query_lower:
                    # Filter to rows matching this value
                    candidate = [
                        r for r in filtered
                        if col_idx < len(r) and str(r[col_idx]).lower() == val.lower()
                    ]
                    if candidate:
                        filtered = candidate
                    break  # Only apply one filter per column

        # Fallback to all rows if filtering removes everything
        return filtered if filtered else rows

    async def _ensure_schema_cached(self, dataset_name: str) -> list[dict]:
        """Fetch and cache schema for column type inference.

        Tries get_schema first. Falls back to sample_dataset for type
        inference if get_schema fails.

        Returns:
            List of column metadata dicts with at least 'name' and 'type' keys.
        """
        if dataset_name in self._schema_cache:
            return self._schema_cache[dataset_name]

        # Try get_schema first
        try:
            result = await self.client.call_tool(
                "get_schema",
                {"dataset": dataset_name},
            )
            if result.success and result.content:
                columns = result.content.get("columns", [])
                if columns:
                    self._schema_cache[dataset_name] = columns
                    return columns
        except (MCPTimeoutError, MCPUnavailableError):
            pass

        # Fallback: sample_dataset to infer types
        try:
            result = await self.client.call_tool(
                "sample_dataset",
                {"dataset": dataset_name},
            )
            if result.success and result.content:
                columns = self._infer_schema_from_sample(result.content)
                if columns:
                    self._schema_cache[dataset_name] = columns
                    return columns
        except (MCPTimeoutError, MCPUnavailableError):
            pass

        logger.warning(
            "Could not retrieve schema for dataset %s", dataset_name
        )
        return []

    async def _get_semantic_metadata(
        self, dataset_name: str
    ) -> dict[str, Any] | None:
        """Optionally fetch semantic metadata for dimension/measure selection.

        Returns None if the tool call fails or returns no useful metadata.
        """
        try:
            result = await self.client.call_tool(
                "get_semantic_metadata",
                {"dataset": dataset_name},
            )
            if result.success and result.content:
                dimensions = result.content.get("dimensions", [])
                measures = result.content.get("measures", [])
                if dimensions or measures:
                    return result.content
        except (MCPTimeoutError, MCPUnavailableError):
            pass

        return None

    def _compute_aggregation(
        self,
        rows: list[list[Any]],
        columns: list[str],
        columns_meta: list[dict],
        semantic: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Compute sum, avg, min, max, count for each numeric column.

        Uses semantic metadata measures if available, otherwise infers
        numeric columns from schema.
        """
        numeric_cols = self._get_numeric_columns(columns, columns_meta, semantic)

        aggregations: dict[str, dict[str, Any]] = {}
        for col_name in numeric_cols:
            col_idx = columns.index(col_name) if col_name in columns else -1
            if col_idx < 0:
                continue

            values = self._extract_numeric_values(rows, col_idx)
            if not values:
                aggregations[col_name] = {
                    "sum": 0, "avg": 0, "min": 0, "max": 0, "count": 0
                }
                continue

            aggregations[col_name] = {
                "sum": sum(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
                "count": len(values),
            }

        return {
            "data_type": "aggregation",
            "aggregations": aggregations,
            "row_count": len(rows),
        }

    def _compute_comparison(
        self,
        rows: list[list[Any]],
        columns: list[str],
        columns_meta: list[dict],
        semantic: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Group by category column and compute per-group sum/avg for numeric columns.

        Grouping column selection:
        1. If semantic metadata provides dimensions, use the first dimension.
        2. Otherwise, use "category" if present.
        3. Otherwise, use the first string-typed column excluding identifiers.
        """
        group_col = self._select_grouping_column(columns, columns_meta, semantic)
        numeric_cols = self._get_numeric_columns(columns, columns_meta, semantic)

        if group_col is None or group_col not in columns:
            # Can't perform comparison without a grouping column — return flat
            return {
                "data_type": "comparison",
                "groups": {},
                "group_column": None,
                "row_count": len(rows),
            }

        group_idx = columns.index(group_col)

        # Group rows
        groups: dict[str, list[list[Any]]] = {}
        for row in rows:
            key = str(row[group_idx]) if group_idx < len(row) else "unknown"
            if key not in groups:
                groups[key] = []
            groups[key].append(row)

        # Compute per-group aggregates
        group_results: dict[str, dict[str, dict[str, Any]]] = {}
        for group_name, group_rows in groups.items():
            group_aggs: dict[str, dict[str, Any]] = {}
            for col_name in numeric_cols:
                col_idx = columns.index(col_name) if col_name in columns else -1
                if col_idx < 0:
                    continue
                values = self._extract_numeric_values(group_rows, col_idx)
                if not values:
                    group_aggs[col_name] = {"sum": 0, "avg": 0}
                else:
                    group_aggs[col_name] = {
                        "sum": sum(values),
                        "avg": sum(values) / len(values),
                    }
            group_results[group_name] = group_aggs

        return {
            "data_type": "comparison",
            "groups": group_results,
            "group_column": group_col,
            "row_count": len(rows),
        }

    def _get_numeric_columns(
        self,
        columns: list[str],
        columns_meta: list[dict],
        semantic: dict[str, Any] | None,
    ) -> list[str]:
        """Determine which columns are numeric.

        Prefers semantic metadata measures, falls back to schema type info.
        """
        # Prefer semantic measures
        if semantic:
            measures = semantic.get("measures", [])
            if measures:
                # Measures might be strings or dicts with 'name' key
                result = []
                for m in measures:
                    name = m if isinstance(m, str) else m.get("name", "")
                    if name and name in columns:
                        result.append(name)
                if result:
                    return result

        # Fall back to schema column type
        numeric_types = {"numeric", "integer", "float", "decimal", "number", "int"}
        result = []
        meta_by_name = {c.get("name", ""): c for c in columns_meta}

        for col_name in columns:
            meta = meta_by_name.get(col_name, {})
            col_type = meta.get("type", "").lower()
            if col_type in numeric_types:
                result.append(col_name)

        # If schema provides no type info, infer from data (heuristic)
        if not result and columns_meta:
            # No numeric columns found from schema — skip
            pass

        return result

    def _select_grouping_column(
        self,
        columns: list[str],
        columns_meta: list[dict],
        semantic: dict[str, Any] | None,
    ) -> str | None:
        """Select the grouping column for comparison queries.

        Priority:
        1. First semantic dimension
        2. "category" if present
        3. First string-typed column excluding identifiers
        """
        # Prefer semantic dimensions
        if semantic:
            dimensions = semantic.get("dimensions", [])
            if dimensions:
                name = dimensions[0] if isinstance(dimensions[0], str) else dimensions[0].get("name", "")
                if name and name in columns:
                    return name

        # Check for "category" column
        if "category" in columns:
            return "category"

        # Find first string/categorical column excluding identifiers
        string_types = {"categorical", "string", "varchar", "text", "char"}
        meta_by_name = {c.get("name", ""): c for c in columns_meta}

        for col_name in columns:
            if col_name.lower() in _IDENTIFIER_COLUMNS:
                continue
            meta = meta_by_name.get(col_name, {})
            col_type = meta.get("type", "").lower()
            if col_type in string_types:
                return col_name

        return None

    @staticmethod
    def _extract_numeric_values(rows: list[list[Any]], col_idx: int) -> list[float]:
        """Extract numeric values from a specific column, skipping non-numeric entries."""
        values: list[float] = []
        for row in rows:
            if col_idx >= len(row):
                continue
            val = row[col_idx]
            if val is None:
                continue
            try:
                values.append(float(val))
            except (ValueError, TypeError):
                continue
        return values

    @staticmethod
    def _infer_schema_from_sample(content: dict) -> list[dict]:
        """Infer column schema from sample_dataset response.

        Examines sample rows to classify columns as numeric or categorical.
        """
        columns = content.get("columns", [])
        rows = content.get("rows", [])

        if not columns or not rows:
            return []

        result: list[dict] = []
        for i, col_name in enumerate(columns):
            # Check first few non-null values
            is_numeric = False
            for row in rows[:10]:
                if i >= len(row) or row[i] is None:
                    continue
                try:
                    float(row[i])
                    is_numeric = True
                except (ValueError, TypeError):
                    is_numeric = False
                break

            result.append({
                "name": col_name,
                "type": "numeric" if is_numeric else "categorical",
            })

        return result

    def clear_schema_cache(self) -> None:
        """Clear the cached dataset schemas."""
        self._schema_cache.clear()


def _data_type_for(query_type: str) -> str:
    """Map query_type to data_type for AgentResult payload."""
    mapping = {
        "lookup": "tabular",
        "aggregation": "aggregation",
        "comparison": "comparison",
    }
    return mapping.get(query_type, "tabular")
