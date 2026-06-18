"""MCP Client — Connects the Orchestrator Hub to MCP servers over Streamable HTTP.

Provides an async interface for calling MCP tools on the S3, Redshift, and
Ontology servers. Used by the orchestrator as a replacement for direct HTTP
POST calls to spoke agent endpoints.

The client manages connections to all three MCP servers and exposes a unified
`call_tool(server, tool_name, arguments)` interface.
"""

import asyncio
import json
import logging
from typing import Any

from fastmcp import Client

from src.config import MCP_ONTOLOGY_URL, MCP_REDSHIFT_URL, MCP_S3_URL

logger = logging.getLogger(__name__)

# Server name → URL mapping
MCP_SERVER_URLS: dict[str, str] = {
    "s3": MCP_S3_URL,
    "redshift": MCP_REDSHIFT_URL,
    "ontology": MCP_ONTOLOGY_URL,
}

# Entity ref → MCP server + tool mapping
# Maps ontology concepts to which MCP server handles them and what tool to call
ENTITY_TO_MCP_ROUTING: dict[str, dict[str, str]] = {
    # S3 JSON data (financial)
    "ontology:sales_revenue": {"server": "s3", "tool": "read_dataset", "filename": "financial_data.json"},
    "ontology:order_volume": {"server": "s3", "tool": "read_dataset", "filename": "financial_data.json"},
    "ontology:return_rate": {"server": "s3", "tool": "read_dataset", "filename": "financial_data.json"},
    "ontology:quarterly_report": {"server": "s3", "tool": "read_dataset", "filename": "financial_data.json"},
    # S3 CSV data (products)
    "ontology:product_catalog": {"server": "s3", "tool": "read_dataset", "filename": "product_catalog.csv"},
    "ontology:inventory_stock": {"server": "s3", "tool": "read_dataset", "filename": "product_catalog.csv"},
    "ontology:product_pricing": {"server": "s3", "tool": "read_dataset", "filename": "product_catalog.csv"},
    "ontology:supplier_info": {"server": "s3", "tool": "read_dataset", "filename": "product_catalog.csv"},
    # Redshift data
    "ontology:workforce_metrics": {"server": "redshift", "tool": "run_query", "table": "workforce_metrics"},
    "ontology:support_tickets": {"server": "redshift", "tool": "run_query", "table": "support_tickets"},
    "ontology:marketing_campaigns": {"server": "redshift", "tool": "run_query", "table": "marketing_campaigns"},
}


class MCPClientManager:
    """Manages connections to MCP servers and provides tool calling interface.

    Creates FastMCP Client instances for each server and exposes methods
    to call tools, read resources, and resolve entity refs to MCP operations.
    """

    def __init__(self) -> None:
        """Initialize the MCP client manager."""
        self._server_urls = MCP_SERVER_URLS.copy()

    async def call_tool(self, server: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool on a specific MCP server.

        Creates a short-lived client connection, calls the tool, and returns
        the result. Uses Streamable HTTP transport automatically.

        Args:
            server: MCP server name ('s3', 'redshift', or 'ontology').
            tool_name: The tool to invoke on the server.
            arguments: Tool arguments as a dictionary.

        Returns:
            Tool result as a dictionary.
        """
        url = self._server_urls.get(server)
        if not url:
            return {"error": f"Unknown MCP server: {server}", "available": list(self._server_urls.keys())}

        try:
            client = Client(url)
            async with client:
                result = await client.call_tool(tool_name, arguments)
                # FastMCP 3.x returns a CallToolResult with .content list
                # Each content item is a TextContent with .text attribute
                if hasattr(result, "content") and result.content:
                    text_content = result.content[0].text
                    return json.loads(text_content)
                elif hasattr(result, "structuredContent") and result.structuredContent:
                    return result.structuredContent
                else:
                    return {"error": "Empty result from MCP server"}
        except json.JSONDecodeError:
            # Result wasn't JSON, return as text
            if hasattr(result, "content") and result.content:
                return {"text_result": result.content[0].text}
            return {"error": "Non-JSON result from MCP server"}
        except Exception as e:
            logger.error(f"MCP call failed: server={server}, tool={tool_name}, error={e}")
            return {
                "error": f"MCP call failed: {type(e).__name__}: {e}",
                "server": server,
                "tool": tool_name,
            }

    async def read_resource(self, server: str, uri: str) -> dict[str, Any]:
        """Read a resource from an MCP server.

        Args:
            server: MCP server name.
            uri: The resource URI to read.

        Returns:
            Resource content as a dictionary.
        """
        url = self._server_urls.get(server)
        if not url:
            return {"error": f"Unknown MCP server: {server}"}

        try:
            client = Client(url)
            async with client:
                result = await client.read_resource(uri)
                # Result is a ReadResourceResult with .content list
                if hasattr(result, "content") and result.content:
                    return json.loads(result.content[0].text)
                return {"error": "Empty resource result"}
        except Exception as e:
            logger.error(f"MCP resource read failed: server={server}, uri={uri}, error={e}")
            return {"error": f"Resource read failed: {e}"}

    async def dispatch_for_entity_refs(
        self,
        entity_refs: list[str],
        query_type: str,
        query_text: str = "",
        routing_metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Dispatch data retrieval via MCP based on entity refs.

        Resolves which MCP servers and tools to call based on the entity
        references, then executes the appropriate tool calls.

        For S3 data: calls read_dataset with the appropriate filename.
        For Redshift data: first gets schema context via the ontology server,
        then generates and executes SQL.

        Args:
            entity_refs: List of ontology concept IDs from the StructuredIntent.
            query_type: Query type (lookup, aggregation, comparison).
            query_text: Original query text for SQL generation context.
            routing_metadata: Optional routing metadata with hints like group_by_hint.

        Returns:
            List of result dictionaries from each MCP call.
        """
        results: list[dict[str, Any]] = []
        
        if routing_metadata is None:
            routing_metadata = {}

        # Group entity refs by their target server and data file/table
        s3_files: dict[str, list[str]] = {}  # filename → entity_refs
        redshift_tables: dict[str, list[str]] = {}  # table → entity_refs

        for ref in entity_refs:
            routing = ENTITY_TO_MCP_ROUTING.get(ref)
            if not routing:
                continue
            if routing["server"] == "s3":
                filename = routing["filename"]
                s3_files.setdefault(filename, []).append(ref)
            elif routing["server"] == "redshift":
                table = routing["table"]
                redshift_tables.setdefault(table, []).append(ref)

        # Dispatch S3 reads
        for filename, refs in s3_files.items():
            result = await self.call_tool("s3", "read_dataset", {
                "filename": filename,
                "limit": 0,  # Get all rows for processing
            })
            if "error" not in result:
                result["_entity_refs"] = refs
                result["_source"] = f"s3:{filename}"
            results.append(result)

        # Dispatch Redshift queries
        for table, refs in redshift_tables.items():
            # First get the schema to understand columns
            schema_result = await self.call_tool("redshift", "get_schema", {
                "table_name": table,
            })

            # Build a SQL query based on query_type and original query text
            sql = self._build_sql(table, query_type, schema_result, query_text, routing_metadata)
            query_result = await self.call_tool("redshift", "run_query", {"sql": sql})

            if "error" not in query_result:
                query_result["_entity_refs"] = refs
                query_result["_source"] = f"redshift:{table}"
                query_result["_sql"] = sql
            results.append(query_result)

        return results

    def _build_sql(self, table: str, query_type: str, schema: dict[str, Any], query_text: str = "", routing_metadata: dict[str, Any] | None = None) -> str:
        """Build a SQL query based on query type and table schema.

        Flexible approach: analyzes the actual schema to determine numeric and
        categorical columns, then builds appropriate SQL without hardcoding.

        For count queries: generates COUNT(*) optionally with GROUP BY.
        For aggregation queries: generates SUM/AVG/etc GROUP BY categorical columns.
        For comparison queries: generates grouped comparisons.
        For lookup queries: generates simple SELECT *.

        Args:
            table: Target table name.
            query_type: One of 'count', 'lookup', 'aggregation', 'comparison'.
            schema: Schema result from get_schema tool.
            query_text: Original query text for semantic analysis.
            routing_metadata: Optional routing metadata with hints (group_by_hint, etc).

        Returns:
            SQL string to execute.
        """
        if routing_metadata is None:
            routing_metadata = {}

        columns = schema.get("columns", [])
        if not columns:
            # Fallback for schemas without column info
            if query_type == "count":
                return f'SELECT COUNT(*) AS total_count FROM "public"."{table}";'
            return f'SELECT * FROM "public"."{table}" LIMIT 100;'

        # Dynamically identify column types from schema data_type field
        numeric_cols = []
        categorical_cols = []
        date_cols = []
        
        for col in columns:
            col_name = col.get("column_name", "")
            data_type = col.get("data_type", "").lower()
            
            # Classify column by data type
            if any(t in data_type for t in ("int", "numeric", "decimal", "float", "double", "real", "bigint", "smallint")):
                numeric_cols.append(col_name)
            elif any(t in data_type for t in ("date", "timestamp", "time")):
                date_cols.append(col_name)
            elif any(t in data_type for t in ("char", "varchar", "text", "string", "boolean", "bool")):
                categorical_cols.append(col_name)

        # Extract routing hints
        group_by_hint = routing_metadata.get("group_by_hint")
        target_columns = routing_metadata.get("target_columns", [])
        aggregate_fn = routing_metadata.get("aggregate_function", "SUM").upper()
        
        # Validate aggregate function
        valid_aggs = {"SUM", "AVG", "COUNT", "MIN", "MAX"}
        if aggregate_fn not in valid_aggs:
            aggregate_fn = "SUM"

        # Check if this is a COUNT query based on query text
        is_count_query = any(
            kw in query_text.lower() 
            for kw in ["how many", "count", "number of", "total number", "how much"]
        )

        # ============ HANDLE COUNT QUERIES ============
        if query_type == "count" or is_count_query:
            # Determine GROUP BY column
            group_by_col = None
            if group_by_hint and isinstance(group_by_hint, str):
                # If hint is a column name and exists in schema
                if group_by_hint in categorical_cols or group_by_hint in date_cols:
                    group_by_col = group_by_hint
            elif isinstance(group_by_hint, list) and group_by_hint:
                # If hint is a list, use first matching column
                for hint in group_by_hint:
                    if hint in categorical_cols or hint in date_cols:
                        group_by_col = hint
                        break
            
            # Try to detect dimension from query text
            if not group_by_col:
                group_by_col = self._detect_group_by_column(query_text, categorical_cols + date_cols, table)
            
            # Build COUNT query
            if group_by_col:
                # GROUP BY with COUNT breakdown
                return f'SELECT "{group_by_col}", COUNT(*) AS count FROM "public"."{table}" GROUP BY "{group_by_col}" ORDER BY count DESC;'
            else:
                # Simple total COUNT
                return f'SELECT COUNT(*) AS total_count FROM "public"."{table}";'

        # ============ HANDLE AGGREGATION QUERIES ============
        if query_type == "aggregation":
            if not numeric_cols:
                # No numeric columns — fall back to counting
                return f'SELECT COUNT(*) AS record_count FROM "public"."{table}";'
            
            # Determine GROUP BY columns
            group_cols = []
            if group_by_hint:
                # Use hint if provided
                if isinstance(group_by_hint, str):
                    if group_by_hint in categorical_cols or group_by_hint in date_cols:
                        group_cols = [group_by_hint]
                elif isinstance(group_by_hint, list):
                    for hint in group_by_hint:
                        if hint in categorical_cols or hint in date_cols:
                            group_cols.append(hint)
            
            # If no hint, try to detect from query text
            if not group_cols:
                detected = self._detect_group_by_column(query_text, categorical_cols + date_cols, table)
                if detected:
                    group_cols = [detected]
            
            # Fallback: use all categorical columns if nothing detected
            if not group_cols:
                group_cols = categorical_cols[:1] if categorical_cols else []
            
            # Determine which numeric columns to aggregate
            agg_cols = numeric_cols
            if target_columns:
                # Filter to only mentioned columns
                agg_cols = [c for c in numeric_cols if c in target_columns]
                if not agg_cols:
                    agg_cols = numeric_cols  # Fallback to all if none matched
            
            # Build SELECT clause with aggregates
            select_parts = []
            for col in group_cols:
                select_parts.append(f'"{col}"')
            
            for col in agg_cols[:5]:  # Limit to first 5 numeric columns
                select_parts.append(f'{aggregate_fn}("{col}") AS {aggregate_fn.lower()}_{col}')
            
            select_clause = ", ".join(select_parts)
            
            if group_cols:
                group_by_clause = ", ".join(f'"{col}"' for col in group_cols)
                return f'SELECT {select_clause} FROM "public"."{table}" GROUP BY {group_by_clause};'
            else:
                # No grouping, just aggregates
                return f'SELECT {select_clause} FROM "public"."{table}";'

        # ============ HANDLE COMPARISON QUERIES ============
        if query_type == "comparison":
            if not categorical_cols and not date_cols:
                # No dimension to compare by
                return f'SELECT * FROM "public"."{table}" LIMIT 100;'
            
            # Determine comparison dimension
            comp_col = None
            if group_by_hint:
                if isinstance(group_by_hint, str) and (group_by_hint in categorical_cols or group_by_hint in date_cols):
                    comp_col = group_by_hint
                elif isinstance(group_by_hint, list) and group_by_hint:
                    for hint in group_by_hint:
                        if hint in categorical_cols or hint in date_cols:
                            comp_col = hint
                            break
            
            if not comp_col:
                comp_col = self._detect_group_by_column(query_text, categorical_cols + date_cols, table)
            
            if not comp_col:
                comp_col = categorical_cols[0] if categorical_cols else date_cols[0]
            
            # Build comparison SELECT
            select_parts = [f'"{comp_col}"']
            
            if numeric_cols:
                for col in numeric_cols[:3]:  # Limit to first 3 numeric columns
                    select_parts.append(f'SUM("{col}") AS sum_{col}')
            else:
                select_parts.append('COUNT(*) AS count')
            
            select_clause = ", ".join(select_parts)
            return f'SELECT {select_clause} FROM "public"."{table}" GROUP BY "{comp_col}" ORDER BY {select_parts[1]} DESC;'

        # ============ HANDLE LOOKUP QUERIES (DEFAULT) ============
        return f'SELECT * FROM "public"."{table}" LIMIT 100;'

    def _detect_group_by_column(self, query_text: str, categorical_cols: list[str], table: str) -> str | None:
        """Detect which column to GROUP BY based on query text and available columns.

        Flexible approach: matches words in the query against actual column names
        and semantic similarity, rather than hardcoded keyword mappings.

        Uses the following strategies in order:
        1. Direct substring match: Is a column name mentioned in the query?
        2. Semantic similarity: Does the query mention a word similar to a column?
        3. Common patterns: Is there a query pattern that suggests grouping?

        Args:
            query_text: Original query text.
            categorical_cols: List of available categorical columns in the table.
            table: Table name being queried (for context - not used for hardcoding).

        Returns:
            Column name to group by, or None if no match found.
        """
        if not query_text or not categorical_cols:
            return None

        query_lower = query_text.lower()
        
        # Strategy 1: Direct substring match with column names
        # Extract column name without prefixes like 'is_', 'has_', 'num_', etc.
        for col in categorical_cols:
            col_lower = col.lower()
            # Try exact substring match
            if col_lower in query_lower:
                return col
            # Try without common prefixes
            col_without_prefix = col_lower
            for prefix in ["is_", "has_", "num_", "count_", "total_", "avg_"]:
                if col_without_prefix.startswith(prefix):
                    col_without_prefix = col_without_prefix[len(prefix):]
                    if col_without_prefix in query_lower:
                        return col
            # Try with underscores replaced by spaces
            col_as_phrase = col_lower.replace("_", " ")
            if col_as_phrase in query_lower:
                return col
            # Try each word in the column name
            for word in col_lower.split("_"):
                if len(word) > 3 and word in query_lower:
                    return col

        # Strategy 2: Extract key nouns/dimensions from query and match to columns
        # This is semantic: "by department" should match "department" column
        # Look for common dimension indicators in query
        dimension_indicators = [
            "by ", "grouped by ", "for each ", "for every ", "across ", 
            "broken down by ", "broken down across ", "segmented by ", "per ",
        ]
        
        query_words_set = set(query_lower.split())
        
        for indicator in dimension_indicators:
            idx = query_lower.find(indicator)
            if idx >= 0:
                # Extract words after the indicator
                after_indicator = query_lower[idx + len(indicator):].split()
                for word in after_indicator[:3]:  # Check first few words after indicator
                    # Clean word of punctuation
                    word = word.strip(".,;:?!")
                    if len(word) > 2:
                        # Match against column names
                        for col in categorical_cols:
                            col_lower = col.lower()
                            if word in col_lower or col_lower.find(word) >= 0:
                                return col

        # Strategy 3: If query mentions comparative/aggregation keywords but no specific dimension,
        # return the first categorical column as a sensible default
        # This handles cases like "show totals" (should group by first categorical)
        comparison_keywords = ["compare", "versus", "vs", "between", "difference"]
        if any(kw in query_lower for kw in comparison_keywords) and categorical_cols:
            return categorical_cols[0]

        return None


# Module-level singleton
_mcp_client: MCPClientManager | None = None


def get_mcp_client() -> MCPClientManager:
    """Get or create the singleton MCP client manager.

    Returns:
        The MCPClientManager instance.
    """
    global _mcp_client
    if _mcp_client is None:
        _mcp_client = MCPClientManager()
    return _mcp_client
