"""Response Transformer for the MCP Adapter Layer.

Converts raw MCP tool responses (MCPToolResult) into AgentResult format
compatible with the downstream Guardrail Layer and Visualization Renderer.
"""

from __future__ import annotations

from typing import Any

from src.models.shared import AgentResult, StructuredIntent

from .models import MCPToolResult


# Agent ID and data_source mappings by server_id
_AGENT_IDS = {
    "redshift": "mcp-redshift-adapter",
    "s3": "mcp-s3-adapter",
}

_DATA_SOURCES = {
    "redshift": "mcp-redshift",
    "s3": "mcp-s3",
}

# Query type to data_type mapping
_DATA_TYPE_MAP = {
    "lookup": "tabular",
    "aggregation": "aggregation",
    "comparison": "comparison",
}


class ResponseTransformer:
    """Transforms MCP tool responses to AgentResult format.

    Provides static methods for converting Redshift query results,
    S3 read results, and error responses into the standard AgentResult
    schema consumed by downstream services.
    """

    @staticmethod
    def from_redshift_query(
        mcp_result: MCPToolResult, intent: StructuredIntent
    ) -> AgentResult:
        """Transform execute_query/execute_parameterized_query result to AgentResult.

        Extracts columns, rows, and pagination info from the MCP response
        content. Handles empty results gracefully.

        Args:
            mcp_result: The MCPToolResult from a Redshift query tool call.
            intent: The original StructuredIntent for query_type mapping.

        Returns:
            AgentResult with status "success" and tabular payload, or
            error AgentResult if the MCP result indicates failure.
        """
        if not mcp_result.success:
            return ResponseTransformer.error_result(
                server_id="redshift",
                tool_name=mcp_result.tool_name,
                error_description=mcp_result.error_message or "Unknown error",
            )

        content = mcp_result.content or {}

        # Check if the MCP tool returned an error response (the MCP SDK
        # doesn't always set isError for application-level errors)
        if "error" in content and "columns" not in content:
            error_info = content["error"]
            error_msg = error_info.get("message", "Unknown MCP tool error") if isinstance(error_info, dict) else str(error_info)
            return ResponseTransformer.error_result(
                server_id="redshift",
                tool_name=mcp_result.tool_name,
                error_description=error_msg,
            )

        # Extract columns and rows from the MCP response
        raw_columns = content.get("columns", [])
        rows = content.get("rows", [])

        # Normalize columns — MCP server may return dicts like [{"name": "col", "type": "varchar"}]
        # or plain strings like ["col1", "col2"]. Ensure we always produce a list of strings.
        if raw_columns and isinstance(raw_columns[0], dict):
            columns = [col.get("name", str(col)) for col in raw_columns]
        else:
            columns = raw_columns

        # Row count from pagination metadata or actual row length
        pagination = content.get("pagination", {})
        row_count = pagination.get("total_count", len(rows))

        data_type = _DATA_TYPE_MAP.get(intent.query_type, "tabular")

        return AgentResult(
            status="success",
            payload={
                "data_type": data_type,
                "columns": columns,
                "rows": rows,
                "row_count": row_count,
            },
            agent_id=_AGENT_IDS["redshift"],
            data_source=_DATA_SOURCES["redshift"],
        )

    @staticmethod
    def from_s3_read(
        rows: list[list[Any]],
        columns: list[str],
        intent: StructuredIntent,
    ) -> AgentResult:
        """Transform accumulated S3 read_dataset rows into AgentResult.

        Sets data_type based on the original query_type. Row count is the
        number of rows in the accumulated array.

        Args:
            rows: Accumulated row data from paginated read_dataset calls.
            columns: Column names from the dataset.
            intent: The original StructuredIntent for query_type mapping.

        Returns:
            AgentResult with status "success" and appropriate data_type.
        """
        data_type = _DATA_TYPE_MAP.get(intent.query_type, "tabular")

        return AgentResult(
            status="success",
            payload={
                "data_type": data_type,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            },
            agent_id=_AGENT_IDS["s3"],
            data_source=_DATA_SOURCES["s3"],
        )

    @staticmethod
    def error_result(
        server_id: str, tool_name: str, error_description: str
    ) -> AgentResult:
        """Produce error AgentResult from MCP failure.

        Args:
            server_id: Identifier of the MCP server ("redshift" or "s3").
            tool_name: Name of the MCP tool that failed.
            error_description: Error text from the MCP response.

        Returns:
            AgentResult with status "error" and error_type "MCP_TOOL_ERROR".
        """
        agent_id = _AGENT_IDS.get(server_id, f"mcp-{server_id}-adapter")
        data_source = _DATA_SOURCES.get(server_id, f"mcp-{server_id}")

        return AgentResult(
            status="error",
            error_type="MCP_TOOL_ERROR",
            error_description=(
                f"{data_source} {tool_name}: {error_description}"
            ),
            agent_id=agent_id,
            data_source=data_source,
        )
