"""FastAPI application for the Guardrail Layer service.

Exposes POST /internal/validate endpoint that validates orchestrator responses
against schemas and policy rules. On pass/redact, calls the Visualization
Renderer and returns RenderedOutput. On reject, returns 422 with error details.

Runs on port 8003.

Requirements: 7.1, 7.7, 11.4
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.config import BEDROCK_GUARDRAIL_ID, BEDROCK_GUARDRAIL_VERSION, GUARDRAIL_PORT
from src.models.shared import OrchestratorResponse, StructuredIntent
from src.services.guardrail_layer import GuardrailLayer
from src.services.observability import (
    extract_correlation_id,
    observability_decorator,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Guardrail Layer Service",
    description="Validates orchestrator responses against schemas and policy rules.",
    version="1.0.0",
)

# Module-level guardrail instance
_guardrail: GuardrailLayer | None = None


def get_guardrail() -> GuardrailLayer:
    """Get or create the GuardrailLayer instance."""
    global _guardrail
    if _guardrail is None:
        _guardrail = GuardrailLayer(
            bedrock_guardrail_id=BEDROCK_GUARDRAIL_ID,
            bedrock_guardrail_version=BEDROCK_GUARDRAIL_VERSION,
        )
    return _guardrail


def set_guardrail(guardrail: GuardrailLayer) -> None:
    """Override the guardrail instance (for testing)."""
    global _guardrail
    _guardrail = guardrail


class ValidateRequest(BaseModel):
    """Request body for POST /internal/validate."""

    orchestrator_response: dict
    structured_intent: dict


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    guardrail = get_guardrail()
    return {
        "status": "healthy",
        "service": "guardrail_layer",
        "port": GUARDRAIL_PORT,
        "rules_loaded": len(guardrail.rules),
    }


@app.post("/internal/validate")
@observability_decorator("guardrail_layer")
async def validate_endpoint(request: Request, body: ValidateRequest) -> JSONResponse:
    """Validate an orchestrator response against schemas and policy rules.

    On passed/redacted: returns the validated response for rendering.
    On rejected: returns 422 with error details.

    Args:
        request: The inbound FastAPI request.
        body: Request body with orchestrator_response and structured_intent.

    Returns:
        JSONResponse with validation result.
    """
    correlation_id = extract_correlation_id(request)
    guardrail = get_guardrail()

    # Parse inputs
    try:
        response = OrchestratorResponse.model_validate(body.orchestrator_response)
        intent = StructuredIntent.model_validate(body.structured_intent)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "INVALID_INPUT",
                "message": f"Failed to parse request: {e}",
            },
        )

    # Validate
    result = await guardrail.validate(response, intent)

    if result.status == "rejected":
        return JSONResponse(
            status_code=422,
            content={
                "status": "rejected",
                "error_details": result.error_details,
                "triggered_rules": result.applied_rules,
            },
        )

    if result.status == "error":
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "error_details": result.error_details,
            },
        )

    # Passed or redacted — return validated response
    validated_resp = result.validated_response
    return JSONResponse(
        status_code=200,
        content={
            "status": result.status,
            "validated_response": validated_resp.model_dump(mode="json") if validated_resp else None,
            "applied_rules": result.applied_rules,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=GUARDRAIL_PORT)
