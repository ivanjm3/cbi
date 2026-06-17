"""FastAPI application for the Orchestrator Hub service.

Exposes endpoints for processing structured intents and managing
spoke agent registrations. Also provides POST /internal/cancel for
cooperative query cancellation propagation from the NLP API.

Runs on port 8002.

Requirements: 4.1, 5.1, 5.2, 6.5, 11.4
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.services.logging_config import configure_logging
configure_logging()

from src.config import ORCHESTRATOR_PORT
from src.models.shared import AgentRegistration, OrchestratorError, StructuredIntent
from src.services.observability import (
    extract_correlation_id,
    observability_decorator,
)
from src.services.orchestrator_hub import OrchestratorHub

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Orchestrator Hub Service",
    description="Central routing engine that dispatches structured intents to spoke agents.",
    version="1.0.0",
)

# Module-level hub instance, initialized on startup
_hub: OrchestratorHub | None = None


def get_hub() -> OrchestratorHub:
    """Get or create the OrchestratorHub instance.
    Returns:
        The shared OrchestratorHub instance.
    """
    global _hub
    if _hub is None:
        _hub = OrchestratorHub()
    return _hub

def set_hub(hub: OrchestratorHub) -> None:
    """Override the hub instance (for testing).
    Args:
        hub: A configured OrchestratorHub instance.
    """
    global _hub
    _hub = hub


class ProcessRequest(BaseModel):
    """Request body for POST /internal/process."""
    structured_intent: dict


class InternalCancelRequest(BaseModel):
    """Request body for POST /internal/cancel."""
    correlation_id: str


class InternalCancelResponse(BaseModel):
    """Response body for POST /internal/cancel."""
    cancelled: bool
    correlation_id: str


class AgentRegistrationRequest(BaseModel):
    """Request body for POST /admin/agents."""

    agent_id: str
    agent_name: str
    data_source: str
    endpoint_url: str
    entity_refs: list[str]


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint.

    Returns:
        Service status information.
    """
    hub = get_hub()
    return {
        "status": "healthy",
        "service": "orchestrator_hub",
        "port": ORCHESTRATOR_PORT,
        "registered_agents": len(hub.get_registered_agents()),
    }


@app.post("/internal/cancel")
async def cancel_internal_endpoint(body: InternalCancelRequest) -> JSONResponse:
    """Internal cancel endpoint called by NLP API.

    Marks the correlation ID as cancelled in the orchestrator hub's
    cancellation registry so the dispatch loop can skip remaining agents.

    Returns 200 with confirmation regardless of whether the query
    was active (idempotent / no-op safe).

    Args:
        body: The request body containing the correlation_id to cancel.

    Returns:
        JSONResponse with cancellation status.
    """
    hub = get_hub()
    hub.register_cancellation(body.correlation_id)

    logger.info(f"Internal cancellation registered for correlation_id={body.correlation_id}")

    return JSONResponse(
        status_code=200,
        content=InternalCancelResponse(
            cancelled=True,
            correlation_id=body.correlation_id,
        ).model_dump(),
    )


@app.post("/internal/process")
@observability_decorator("orchestrator_hub")
async def process_intent_endpoint(request: Request, body: ProcessRequest) -> JSONResponse:
    """Process a structured intent through the orchestration pipeline.
    Checks cache, resolves agents, dispatches concurrently, merges results.
    Args:
        request: The inbound FastAPI request (for correlation ID extraction).
        body: The request body containing the structured intent.
    Returns:
        JSONResponse with OrchestratorResponse (200) or OrchestratorError (422).
    """
    correlation_id = extract_correlation_id(request)
    hub = get_hub()

    # Parse the structured intent
    try:
        intent = StructuredIntent.model_validate(body.structured_intent)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "INVALID_INTENT",
                "message": f"Failed to parse structured intent: {e}",
            },
        )

    # Process through the hub
    result = await hub.process_intent(intent, correlation_id=correlation_id)

    if isinstance(result, OrchestratorError):
        return JSONResponse(
            status_code=422,
            content={
                "error_type": result.error_type,
                "message": result.message,
                "query_id": str(result.query_id),
            },
        )

    # Success: return OrchestratorResponse
    return JSONResponse(
        status_code=200,
        content={
            "orchestrator_response": result.model_dump(mode="json"),
        },
    )


@app.post("/admin/agents")
@observability_decorator("orchestrator_hub")
async def register_agent_endpoint(
    request: Request, body: AgentRegistrationRequest
) -> JSONResponse:
    """Register a spoke agent with the orchestrator.

    Args:
        request: The inbound FastAPI request.
        body: The agent registration details.

    Returns:
        JSONResponse confirming registration (201).
    """
    hub = get_hub()

    registration = AgentRegistration(
        agent_id=body.agent_id,
        agent_name=body.agent_name,
        data_source=body.data_source,
        endpoint_url=body.endpoint_url,
        entity_refs=body.entity_refs,
    )

    hub.register_agent(registration)

    return JSONResponse(
        status_code=201,
        content={"registered": True, "agent_id": body.agent_id},
    )


@app.delete("/admin/agents/{agent_id}")
@observability_decorator("orchestrator_hub")
async def deregister_agent_endpoint(request: Request, agent_id: str) -> JSONResponse:
    """Deregister a spoke agent from the orchestrator.

    Args:
        request: The inbound FastAPI request.
        agent_id: The identifier of the agent to remove.

    Returns:
        JSONResponse confirming deregistration (200) or not found (404).
    """
    hub = get_hub()

    if hub.deregister_agent(agent_id):
        return JSONResponse(
            status_code=200,
            content={"deregistered": True, "agent_id": agent_id},
        )
    else:
        return JSONResponse(
            status_code=404,
            content={"error": "NOT_FOUND", "message": f"Agent '{agent_id}' not found."},
        )


@app.get("/admin/agents")
async def list_agents_endpoint() -> JSONResponse:
    """List all registered spoke agents.

    Returns:
        JSONResponse with list of registered agents.
    """
    hub = get_hub()
    agents = hub.get_registered_agents()
    return JSONResponse(
        status_code=200,
        content={
            "agents": [agent.model_dump() for agent in agents],
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=ORCHESTRATOR_PORT)
