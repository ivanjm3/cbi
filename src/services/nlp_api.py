"""FastAPI application for the NLP Translator service.

Exposes the POST /query endpoint that accepts natural language queries,
translates them into structured intents, and orchestrates the full
query flow: NLP → Orchestrator → Guardrail → Renderer.

Runs on port 8001 (configured in src.config).

Requirements: 2.1, 2.5, 11.2
"""

import logging
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from src.config import (
    GUARDRAIL_URL,
    NLP_PORT,
    ORCHESTRATOR_URL,
    VIZ_URL,
)
from src.models.shared import NLPError, StructuredIntent
from src.services.nlp_translator import NLPTranslator
from src.services.observability import (
    extract_correlation_id,
    observability_decorator,
    propagation_headers,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="NLP Translator Service",
    description="Translates natural language queries into structured intents and orchestrates the query flow.",
    version="1.0.0",
)

# CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Path to the frontend HTML file
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

# Module-level translator instance, initialized on startup
_translator: NLPTranslator | None = None


def get_translator() -> NLPTranslator:
    """Get or create the NLP Translator instance.

    Returns:
        The shared NLPTranslator instance.
    """
    global _translator
    if _translator is None:
        _translator = NLPTranslator()
    return _translator


def set_translator(translator: NLPTranslator) -> None:
    """Override the translator instance (for testing).

    Args:
        translator: A configured NLPTranslator instance.
    """
    global _translator
    _translator = translator


class QueryRequest(BaseModel):
    """Request body for the POST /query endpoint."""
    query_text: str


class ErrorResponse(BaseModel):
    """Error response body returned on translation failures."""
    error_code: str
    error_message: str
    query_id: str


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint.
    Returns:
        Service status information.
    """
    return {"status": "healthy", "service": "nlp_translator", "port": NLP_PORT}


@app.get("/")
async def serve_frontend() -> FileResponse:
    """Serve the testing frontend UI.
    Returns:
        The index.html file for the query testing interface.
    """
    return FileResponse(_FRONTEND_DIR / "index.html", media_type="text/html")


import asyncio
import uuid


def _check_input_guardrails_bedrock(query_text: str) -> dict | None:
    """Check input via Bedrock Guardrails only. No local regex.

    On Bedrock unavailability: fail open (allow content, log warning).

    Args:
        query_text: The raw user query.

    Returns:
        Error dict with error_code and error_message if blocked, or None.
    """
    from src.config import BEDROCK_GUARDRAIL_ID, BEDROCK_GUARDRAIL_VERSION
    if not BEDROCK_GUARDRAIL_ID:
        return None  # No guardrail configured

    try:
        from src.config import get_bedrock_client
        client = get_bedrock_client()
        result = client.apply_guardrail(
            guardrailIdentifier=BEDROCK_GUARDRAIL_ID,
            guardrailVersion=BEDROCK_GUARDRAIL_VERSION,
            source="INPUT",
            content=[{"text": {"text": query_text}}],
        )
        if result.get("action") == "GUARDRAIL_INTERVENED":
            outputs = result.get("outputs", [])
            message = outputs[0].get("text", "Content blocked") if outputs else "Content policy violation"
            return {
                "error_code": "CONTENT_POLICY_VIOLATION",
                "error_message": message,
                "query_id": str(uuid.uuid4()),
            }
    except Exception as e:
        logger.warning(f"Input Bedrock Guardrails check failed: {e}")

    return None  # Fail open


@app.post("/query")
@observability_decorator("nlp_translator")
async def query_endpoint(request: Request, body: QueryRequest) -> JSONResponse:
    """Accept a natural language query and return rendered output.
    Orchestrates the full query flow:
    1. Translate query → StructuredIntent
    2. Call Orchestrator Hub /internal/process with intent
    3. Call Guardrail Layer /internal/validate with response + intent
    4. Call Visualization Renderer /internal/render with validated response
    5. Return RenderedOutput to client
    If translation fails, returns 422 with NLPError details.

    Args:
        request: The inbound FastAPI request (for correlation ID extraction).
        body: The request body containing query_text.

    Returns:
        JSONResponse with rendered output (200) or error details (422/500).
    """
    correlation_id = extract_correlation_id(request)
    translator = get_translator()

    # Run input guardrail check and NLP translation in parallel
    input_rejection, result = await asyncio.gather(
        asyncio.to_thread(_check_input_guardrails_bedrock, body.query_text),
        translator.translate(body.query_text),
    )

    # If input guardrail rejects, return 422 immediately
    if input_rejection:
        return JSONResponse(
            status_code=422,
            content=input_rejection,
        )

    # Step 1: Use translation result
    if isinstance(result, NLPError):
        return JSONResponse(
            status_code=422,
            content={
                "error_code": result.error_code,
                "error_message": result.error_message,
                "query_id": str(result.query_id),
            },
        )

    intent: StructuredIntent = result
    headers = propagation_headers(correlation_id)

    # Step 2: Call Orchestrator Hub
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            orchestrator_response = await client.post(
                f"{ORCHESTRATOR_URL}/internal/process",
                json={"structured_intent": intent.model_dump(mode="json")},
                headers=headers,
            )

            if orchestrator_response.status_code != 200:
                error_data = orchestrator_response.json()
                return JSONResponse(
                    status_code=orchestrator_response.status_code,
                    content=error_data,
                )

            orchestrator_data = orchestrator_response.json()

    except httpx.ConnectError:
        logger.error(f"Failed to connect to Orchestrator Hub at {ORCHESTRATOR_URL}")
        return JSONResponse(
            status_code=503,
            content={
                "error": "SERVICE_UNAVAILABLE",
                "message": "Orchestrator Hub is not available.",
                "query_id": str(intent.query_id),
            },
        )
    except httpx.TimeoutException:
        logger.error("Orchestrator Hub request timed out")
        return JSONResponse(
            status_code=504,
            content={
                "error": "GATEWAY_TIMEOUT",
                "message": "Orchestrator Hub request timed out.",
                "query_id": str(intent.query_id),
            },
        )

    # Step 3: Call Guardrail Layer
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            guardrail_response = await client.post(
                f"{GUARDRAIL_URL}/internal/validate",
                json={
                    "orchestrator_response": orchestrator_data.get(
                        "orchestrator_response", orchestrator_data
                    ),
                    "structured_intent": intent.model_dump(mode="json"),
                },
                headers=headers,
            )

            if guardrail_response.status_code != 200:
                error_data = guardrail_response.json()
                return JSONResponse(
                    status_code=guardrail_response.status_code,
                    content=error_data,
                )

            guardrail_data = guardrail_response.json()

    except httpx.ConnectError:
        logger.error(f"Failed to connect to Guardrail Layer at {GUARDRAIL_URL}")
        return JSONResponse(
            status_code=503,
            content={
                "error": "SERVICE_UNAVAILABLE",
                "message": "Guardrail Layer is not available.",
                "query_id": str(intent.query_id),
            },
        )
    except httpx.TimeoutException:
        logger.error("Guardrail Layer request timed out")
        return JSONResponse(
            status_code=504,
            content={
                "error": "GATEWAY_TIMEOUT",
                "message": "Guardrail Layer request timed out.",
                "query_id": str(intent.query_id),
            },
        )

    # Step 4: Call Visualization Renderer
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            viz_response = await client.post(
                f"{VIZ_URL}/internal/render",
                json={
                    "validated_response": guardrail_data.get(
                        "validated_response", guardrail_data
                    ),
                    "structured_intent": intent.model_dump(mode="json"),
                },
                headers=headers,
            )

            if viz_response.status_code != 200:
                error_data = viz_response.json()
                return JSONResponse(
                    status_code=viz_response.status_code,
                    content=error_data,
                )

            rendered_output = viz_response.json()

    except httpx.ConnectError:
        logger.error(f"Failed to connect to Visualization Renderer at {VIZ_URL}")
        return JSONResponse(
            status_code=503,
            content={
                "error": "SERVICE_UNAVAILABLE",
                "message": "Visualization Renderer is not available.",
                "query_id": str(intent.query_id),
            },
        )
    except httpx.TimeoutException:
        logger.error("Visualization Renderer request timed out")
        return JSONResponse(
            status_code=504,
            content={
                "error": "GATEWAY_TIMEOUT",
                "message": "Visualization Renderer request timed out.",
                "query_id": str(intent.query_id),
            },
        )

    # Step 5: Return rendered output to client
    return JSONResponse(
        status_code=200,
        content={"rendered_output": rendered_output},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=NLP_PORT)
