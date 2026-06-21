"""Routing and response data models for the MCP Adapter Layer.

Defines intermediate data structures used within the adapter for routing
decisions (RoutingTarget) and normalized MCP tool call results (MCPToolResult).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class RoutingTarget(BaseModel):
    """Resolved routing target for a StructuredIntent.

    Produced by the IntentRouter after resolving entity_refs against the
    OntologyStore. Identifies which MCP server and dataset/table should
    handle the request.

    Attributes:
        server_id: Target MCP server identifier ("redshift" or "s3").
        dataset_name: Dataset name for S3 targets (e.g., "financial_data",
            "product_catalog"). None for Redshift targets.
        table_name: Table name for Redshift targets (resolved from
            SchemaRegistry). None for S3 targets.
        entity_refs: The entity_ref identifiers that route to this target.
    """

    server_id: Literal["redshift", "s3"]
    dataset_name: str | None = None
    table_name: str | None = None
    entity_refs: list[str] = Field(default_factory=list)


class MCPToolResult(BaseModel):
    """Normalized result from an MCP tool call.

    Wraps the raw MCP protocol response into a consistent structure used
    by translators and the ResponseTransformer.

    Attributes:
        success: Whether the tool call completed without error.
        content: Parsed JSON content from the tool response. None on failure.
        error_message: Error text if the tool call failed (isError=true or
            transport-level failure). None on success.
        tool_name: Name of the MCP tool that was invoked.
        server_id: Identifier of the MCP server ("redshift" or "s3").
        duration_ms: Wall-clock duration of the tool call in milliseconds.
    """

    success: bool
    content: dict | None = None
    error_message: str | None = None
    tool_name: str
    server_id: str
    duration_ms: float = 0.0
