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

from src.services.logging_config import configure_logging
configure_logging()

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

# Path to the frontend built assets (dist/ from Vite build)
_FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

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
    """Serve the frontend SPA index.html.
    Returns:
        The index.html file for the React frontend.
    """
    index_path = _FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return FileResponse(
        Path(__file__).resolve().parent.parent.parent / "frontend" / "index.html",
        media_type="text/html",
    )


@app.get("/cost-report")
async def cost_report_endpoint():
    """Return today's cost report as JSON."""
    from src.services.cost_tracker import get_cost_tracker
    try:
        tracker = get_cost_tracker()
        summary = tracker.get_daily_summary()
        return JSONResponse(status_code=200, content=summary)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


import asyncio
import uuid

# Cache for input guardrail results to avoid repeated Bedrock calls
_input_guardrail_cache: dict[str, dict | None] = {}


def _check_input_guardrails_bedrock(query_text: str) -> dict | None:
    """Check input via Bedrock Guardrails only. No local regex.

    Results are cached per-query to avoid repeated Bedrock API calls
    for the same input text.

    On Bedrock unavailability: fail open (allow content, log warning).

    Args:
        query_text: The raw user query.

    Returns:
        Error dict with error_code and error_message if blocked, or None.
    """
    # Check cache first
    if query_text in _input_guardrail_cache:
        return _input_guardrail_cache[query_text]

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

        # Track input guardrail cost
        try:
            from src.services.cost_tracker import get_cost_tracker
            get_cost_tracker().log_guardrail_invocation(
                component="nlp_api_input_guardrail",
                text_length_chars=len(query_text),
                action=result.get("action", "NONE"),
            )
        except Exception:
            pass  # Don't let cost tracking break guardrails

        if result.get("action") == "GUARDRAIL_INTERVENED":
            outputs = result.get("outputs", [])
            message = outputs[0].get("text", "Content blocked") if outputs else "Content policy violation"
            rejection = {
                "error_code": "CONTENT_POLICY_VIOLATION",
                "error_message": message,
                "query_id": str(uuid.uuid4()),
            }
            _input_guardrail_cache[query_text] = rejection
            return rejection
    except Exception as e:
        logger.warning(f"Input Bedrock Guardrails check failed: {e}")

    _input_guardrail_cache[query_text] = None
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
    5. Return RenderedOutput to client with latency breakdown
    If translation fails, returns 422 with NLPError details.

    Args:
        request: The inbound FastAPI request (for correlation ID extraction).
        body: The request body containing query_text.

    Returns:
        JSONResponse with rendered output (200) or error details (422/500).
    """
    import time

    correlation_id = extract_correlation_id(request)
    translator = get_translator()
    latency: dict[str, int] = {}
    total_start = time.monotonic()

    # Step 1: NLP Translation + Input Guardrail (parallel)
    step_start = time.monotonic()
    input_rejection, result = await asyncio.gather(
        asyncio.to_thread(_check_input_guardrails_bedrock, body.query_text),
        translator.translate(body.query_text),
    )
    latency["nlp_translation_ms"] = int((time.monotonic() - step_start) * 1000)

    # If input guardrail rejects, return 422 immediately
    if input_rejection:
        return JSONResponse(
            status_code=422,
            content=input_rejection,
        )

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
    step_start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
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
    latency["orchestrator_ms"] = int((time.monotonic() - step_start) * 1000)

    # Step 3: Call Guardrail Layer
    step_start = time.monotonic()
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
    latency["guardrail_ms"] = int((time.monotonic() - step_start) * 1000)

    # Step 4: Call Visualization Renderer (longer timeout for LLM agent)
    step_start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
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
    latency["visualization_ms"] = int((time.monotonic() - step_start) * 1000)
    latency["total_ms"] = int((time.monotonic() - total_start) * 1000)

    # Step 5: Return rendered output with latency breakdown
    return JSONResponse(
        status_code=200,
        content={
            "rendered_output": rendered_output,
            "latency": latency,
            "query_id": str(intent.query_id),
            "correlation_id": correlation_id,
        },
    )


# Mount static files for the frontend SPA (Vite build output)
# This must be AFTER all API routes so they take priority
from fastapi.staticfiles import StaticFiles

if _FRONTEND_DIR.exists() and _FRONTEND_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIR / "assets"), name="static-assets")
    # Catch-all for SPA routing — serve index.html for any unmatched GET
    @app.get("/{path:path}")
    async def spa_fallback(path: str):
        """Serve index.html for SPA client-side routing."""
        index_path = _FRONTEND_DIR / "index.html"
        if (file_path := _FRONTEND_DIR / path).exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(index_path, media_type="text/html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=NLP_PORT)
