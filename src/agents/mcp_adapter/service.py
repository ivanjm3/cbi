"""MCP Adapter Service — FastAPI application on port 8012.

Exposes spoke-agent-compatible endpoints for mcp-redshift-adapter and
mcp-s3-adapter. Initializes MCP client connections, routes intents,
translates to MCP tool calls, and falls back to legacy agents on failure.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.models.shared import AgentResult, StructuredIntent
from src.services.cancellation_registry import CancellationRegistry
from src.services.ontology_store import OntologyStore
from src.services.schema_registry import SchemaRegistry
from src.services.sql_generator import SQLGenerator

from .client_manager import MCPClientManager, MCPUnavailableError
from .config import MCPAdapterConfig, load_config
from .fallback_handler import FallbackHandler
from .intent_router import IntentRouter
from .models import MCPToolResult, RoutingTarget
from .redshift_translator import RedshiftTranslator
from .response_transformer import ResponseTransformer
from .s3_translator import S3Translator

logger = logging.getLogger(__name__)

# Service port
MCP_ADAPTER_PORT = 8012


class InvokeRequest(BaseModel):
    """Request body for the agent invoke endpoint."""

    structured_intent: dict


# Module-level state populated during lifespan
_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize and tear down MCP connections."""
    config = load_config()

    # Initialize MCP client managers
    redshift_client = MCPClientManager(config.redshift)
    redshift_client._max_reconnect_attempts = config.max_reconnect_attempts
    redshift_client._reconnect_interval = config.reconnect_interval

    s3_client = MCPClientManager(config.s3)
    s3_client._max_reconnect_attempts = config.max_reconnect_attempts
    s3_client._reconnect_interval = config.reconnect_interval

    # Initialize supporting services
    ontology_store = OntologyStore()
    schema_registry = SchemaRegistry()
    sql_generator = SQLGenerator(schema_registry)
    cancellation_registry = CancellationRegistry()

    # Initialize translators
    redshift_translator = RedshiftTranslator(sql_generator, redshift_client)
    s3_translator = S3Translator(s3_client, max_row_limit=config.max_row_limit)

    # Initialize router and fallback
    intent_router = IntentRouter(ontology_store)
    fallback_handler = FallbackHandler()

    # Store in module state BEFORE connections (so endpoints work even if
    # MCP connections fail — they'll use fallback to legacy agents)
    _state["config"] = config
    _state["redshift_client"] = redshift_client
    _state["s3_client"] = s3_client
    _state["redshift_translator"] = redshift_translator
    _state["s3_translator"] = s3_translator
    _state["intent_router"] = intent_router
    _state["fallback_handler"] = fallback_handler
    _state["response_transformer"] = ResponseTransformer
    _state["cancellation_registry"] = cancellation_registry

    # Attempt connections (non-blocking — failures mark servers unavailable)
    try:
        await redshift_client.connect()
    except Exception as e:
        logger.warning("Redshift MCP connection failed at startup: %s", e)

    try:
        await s3_client.connect()
    except Exception as e:
        logger.warning("S3 MCP connection failed at startup: %s", e)

    logger.info(
        "MCP Adapter Service started on port %d "
        "(redshift=%s, s3=%s)",
        MCP_ADAPTER_PORT,
        "available" if redshift_client.available else "unavailable",
        "available" if s3_client.available else "unavailable",
    )

    try:
        yield
    finally:
        # Graceful shutdown
        logger.info("Shutting down MCP Adapter Service")
        await redshift_client.disconnect()
        await s3_client.disconnect()
        _state.clear()
        logger.info("MCP Adapter Service shutdown complete")


app = FastAPI(
    title="MCP Adapter Layer",
    description="Bridges the Orchestrator Hub with MCP servers for data access",
    lifespan=lifespan,
)


@app.post("/agents/mcp-redshift-adapter/invoke")
async def invoke_redshift(request: Request, body: InvokeRequest) -> JSONResponse:
    """Handle Redshift-targeted intents via MCP.

    Checks cancellation, translates intent to MCP tool call via
    RedshiftTranslator, transforms response, and falls back to
    legacy agent on failure.
    """
    correlation_id = _extract_correlation_id(request)

    try:
        intent = StructuredIntent.model_validate(body.structured_intent)
    except Exception as e:
        result = AgentResult(
            status="error",
            error_type="INVALID_INTENT",
            error_description=f"Failed to parse structured intent: {e}",
            agent_id="mcp-redshift-adapter",
            data_source="mcp-redshift",
        )
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    # Check cancellation
    cancellation_registry: CancellationRegistry = _state["cancellation_registry"]
    if cancellation_registry.is_cancelled(correlation_id):
        result = AgentResult(
            status="error",
            error_type="QUERY_CANCELLED",
            error_description="Request was cancelled before MCP invocation",
            agent_id="mcp-redshift-adapter",
            data_source="mcp-redshift",
        )
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    redshift_client: MCPClientManager = _state["redshift_client"]
    redshift_translator: RedshiftTranslator = _state["redshift_translator"]
    fallback_handler: FallbackHandler = _state["fallback_handler"]
    transformer = _state["response_transformer"]

    # If MCP server is unavailable, go directly to fallback
    if not redshift_client.available:
        result = await fallback_handler.dispatch(intent, "redshift", correlation_id)
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    try:
        # Check cancellation before MCP call
        if cancellation_registry.is_cancelled(correlation_id):
            result = _cancelled_result("mcp-redshift-adapter", "mcp-redshift")
            return JSONResponse(
                status_code=200, content=result.model_dump(mode="json")
            )

        mcp_result = await redshift_translator.execute(intent)

        # If translator returned AgentResult directly (SQL error), return it
        if isinstance(mcp_result, AgentResult):
            return JSONResponse(
                status_code=200, content=mcp_result.model_dump(mode="json")
            )

        # Transform MCPToolResult to AgentResult
        assert isinstance(mcp_result, MCPToolResult)
        if not mcp_result.success:
            logger.warning(
                "MCP Redshift tool returned error: tool=%s, error=%s",
                mcp_result.tool_name,
                mcp_result.error_message,
            )
            result = transformer.error_result(
                "redshift", mcp_result.tool_name, mcp_result.error_message or "Unknown error"
            )
        else:
            logger.info(
                "MCP Redshift tool success: tool=%s, content_keys=%s",
                mcp_result.tool_name,
                list(mcp_result.content.keys()) if mcp_result.content else None,
            )
            result = transformer.from_redshift_query(mcp_result, intent)

        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    except MCPUnavailableError:
        # MCP connection lost — fallback to legacy
        logger.warning(
            "MCP Redshift unavailable during request, falling back "
            "(correlation_id=%s)",
            correlation_id,
        )
        result = await fallback_handler.dispatch(intent, "redshift", correlation_id)
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )


@app.post("/agents/mcp-s3-adapter/invoke")
async def invoke_s3(request: Request, body: InvokeRequest) -> JSONResponse:
    """Handle S3-targeted intents via MCP.

    Checks cancellation, resolves dataset name via IntentRouter,
    translates intent to MCP tool call via S3Translator, and falls
    back to legacy agent on failure.
    """
    correlation_id = _extract_correlation_id(request)

    try:
        intent = StructuredIntent.model_validate(body.structured_intent)
    except Exception as e:
        result = AgentResult(
            status="error",
            error_type="INVALID_INTENT",
            error_description=f"Failed to parse structured intent: {e}",
            agent_id="mcp-s3-adapter",
            data_source="mcp-s3",
        )
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    # Check cancellation
    cancellation_registry: CancellationRegistry = _state["cancellation_registry"]
    if cancellation_registry.is_cancelled(correlation_id):
        result = _cancelled_result("mcp-s3-adapter", "mcp-s3")
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    s3_client: MCPClientManager = _state["s3_client"]
    s3_translator: S3Translator = _state["s3_translator"]
    intent_router: IntentRouter = _state["intent_router"]
    fallback_handler: FallbackHandler = _state["fallback_handler"]

    # If MCP server is unavailable, go directly to fallback
    if not s3_client.available:
        result = await fallback_handler.dispatch(intent, "s3", correlation_id)
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    # Resolve dataset name from entity_refs
    targets = intent_router.resolve_targets(intent)
    if isinstance(targets, AgentResult):
        # Unroutable entity
        return JSONResponse(
            status_code=200, content=targets.model_dump(mode="json")
        )

    # Find the S3 target
    s3_target = next(
        (t for t in targets if t.server_id == "s3"), None
    )
    if s3_target is None or s3_target.dataset_name is None:
        result = AgentResult(
            status="error",
            error_type="UNROUTABLE_ENTITY",
            error_description="No S3 dataset resolved from entity_refs",
            agent_id="mcp-s3-adapter",
            data_source="mcp-s3",
        )
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    try:
        # Check cancellation before MCP call
        if cancellation_registry.is_cancelled(correlation_id):
            result = _cancelled_result("mcp-s3-adapter", "mcp-s3")
            return JSONResponse(
                status_code=200, content=result.model_dump(mode="json")
            )

        result = await s3_translator.execute(intent, s3_target.dataset_name)
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )

    except MCPUnavailableError:
        # MCP connection lost — fallback to legacy
        logger.warning(
            "MCP S3 unavailable during request, falling back "
            "(correlation_id=%s)",
            correlation_id,
        )
        result = await fallback_handler.dispatch(intent, "s3", correlation_id)
        return JSONResponse(
            status_code=200, content=result.model_dump(mode="json")
        )


@app.get("/health")
async def health() -> dict:
    """Health check with MCP server availability status."""
    redshift_client: MCPClientManager | None = _state.get("redshift_client")
    s3_client: MCPClientManager | None = _state.get("s3_client")

    return {
        "status": "healthy",
        "service": "mcp-adapter",
        "port": MCP_ADAPTER_PORT,
        "mcp_servers": {
            "redshift": {
                "available": redshift_client.available if redshift_client else False,
                "transport": redshift_client.config.transport if redshift_client else None,
            },
            "s3": {
                "available": s3_client.available if s3_client else False,
                "transport": s3_client.config.transport if s3_client else None,
            },
        },
    }


def _extract_correlation_id(request: Request) -> str:
    """Extract X-Correlation-ID from request headers, or generate one."""
    import uuid

    correlation_id = request.headers.get("x-correlation-id")
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    return correlation_id


def _cancelled_result(agent_id: str, data_source: str) -> AgentResult:
    """Produce QUERY_CANCELLED AgentResult."""
    return AgentResult(
        status="error",
        error_type="QUERY_CANCELLED",
        error_description="Request was cancelled before MCP invocation",
        agent_id=agent_id,
        data_source=data_source,
    )
