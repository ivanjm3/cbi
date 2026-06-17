"""FastAPI application for the NLP Translator service.

Exposes the POST /query endpoint that accepts natural language queries,
translates them into structured intents, and orchestrates the full
query flow: NLP → Orchestrator → Guardrail → Renderer.

Also exposes POST /cancel for explicit query cancellation, and detects
client disconnects during query processing for cooperative cancellation.

Runs on port 8001 (configured in src.config).

Requirements: 2.1, 2.5, 11.2, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4
"""

import asyncio
import json
import logging
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, FastAPI, Request
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
from src.services.meta_query_detector import MetaQueryDetector
from src.services.cancellation_registry import CancellationRegistry
from src.services.observability import (
    extract_correlation_id,
    observability_decorator,
    propagation_headers,
)

logger = logging.getLogger(__name__)

# Module-level cancellation registry for tracking cancelled queries
_cancellation_registry = CancellationRegistry(ttl_seconds=300.0, max_entries=1000)

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
        from src.services.orchestrator_hub import set_agent_registry_callback
        
        _translator = NLPTranslator()
        
        # Set up callback to sync agent registry updates from orchestrator
        set_agent_registry_callback(_translator.update_registered_agents)
        
        # Update with any agents already registered by orchestrator
        try:
            from src.services.orchestrator_hub import _hub_instance
            if _hub_instance:
                _translator.update_registered_agents(
                    list(_hub_instance._agents.keys())
                )
        except Exception as e:
            # Log warning but don't fail - agents will be synced later
            import logging
            logging.warning(
                f"Could not sync agent registry at initialization: {e}"
            )
    
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


class CancelRequest(BaseModel):
    """Request body for the POST /cancel endpoint."""
    correlation_id: str


class CancelResponse(BaseModel):
    """Response body for the POST /cancel endpoint."""
    cancelled: bool
    correlation_id: str
    message: str


def get_cancellation_registry() -> CancellationRegistry:
    """Get the module-level CancellationRegistry instance.

    Useful for testing or external access.

    Returns:
        The shared CancellationRegistry instance.
    """
    return _cancellation_registry


async def _propagate_cancellation_to_orchestrator(correlation_id: str) -> None:
    """Propagate a cancellation to the Orchestrator Hub (background task).

    Fire-and-forget: logs errors but does not raise.

    Args:
        correlation_id: The query identifier to cancel downstream.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{ORCHESTRATOR_URL}/internal/cancel",
                json={"correlation_id": correlation_id},
            )
    except Exception as e:
        logger.warning(
            f"Failed to propagate cancellation to orchestrator for "
            f"{correlation_id}: {e}"
        )


@app.post("/cancel")
async def cancel_query_endpoint(
    body: CancelRequest, background_tasks: BackgroundTasks
) -> JSONResponse:
    """Cancel an in-flight query by correlation ID.

    Marks the correlation ID in the local registry and propagates
    cancellation to the Orchestrator Hub as a background task to
    ensure response time stays under 50ms.

    Returns 200 with confirmation regardless of whether the query
    was active (idempotent / no-op safe).

    Args:
        body: The request body containing the correlation_id to cancel.
        background_tasks: FastAPI background tasks for async propagation.

    Returns:
        JSONResponse with cancellation status.
    """
    correlation_id = body.correlation_id

    # Register cancellation locally
    _cancellation_registry.register(correlation_id, source="explicit")

    # Propagate to Orchestrator Hub in background (non-blocking)
    background_tasks.add_task(
        _propagate_cancellation_to_orchestrator, correlation_id
    )

    logger.info(f"Cancellation registered for correlation_id={correlation_id}")

    return JSONResponse(
        status_code=200,
        content=CancelResponse(
            cancelled=True,
            correlation_id=correlation_id,
            message="Cancellation registered",
        ).model_dump(),
    )


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint.
    Returns:
        Service status information.
    """
    return {"status": "healthy", "service": "nlp_translator", "port": NLP_PORT}


class FollowUpRequest(BaseModel):
    """Request body for the POST /query/follow-up endpoint."""
    follow_up_text: str
    original_query: str
    conversation_history: list[dict[str, str]] | None = None
    chart_data: dict | None = None
    raw_data: dict | None = None
    metadata: dict | None = None


@app.post("/query/follow-up")
async def follow_up_query_endpoint(request: Request, body: FollowUpRequest) -> JSONResponse:
    """Handle follow-up conversational queries about an existing visualization.

    This endpoint uses an LLM to answer questions about previously generated
    charts/data without re-running the data pipeline. It receives the chart
    context and produces a natural language explanation.

    Use cases:
    - "Explain this graph in simple terms"
    - "What does this data tell us?"
    - "Why is Q3 higher than Q2?"
    - "Summarize the key takeaways"

    Args:
        request: The inbound FastAPI request.
        body: The request body with follow-up text and chart context.

    Returns:
        JSONResponse with a text RenderedOutput containing the explanation.
    """
    import time
    import uuid as uuid_mod

    start_time = time.monotonic()
    correlation_id = extract_correlation_id(request)

    # Input guardrail check
    input_rejection = await asyncio.to_thread(
        _check_input_guardrails_bedrock, body.follow_up_text
    )
    if input_rejection:
        return JSONResponse(status_code=422, content=input_rejection)

    # Build context for the LLM
    context_parts = []
    if body.original_query:
        context_parts.append(f"Original data query: \"{body.original_query}\"")

    if body.metadata:
        query_type = body.metadata.get("query_type", "")
        entity_refs = body.metadata.get("entity_refs", [])
        if query_type:
            context_parts.append(f"Query type: {query_type}")
        if entity_refs:
            context_parts.append(f"Data entities: {', '.join(entity_refs)}")

    # Include chart data summary for the LLM to explain
    data_context = ""
    if body.chart_data:
        # Truncate large data for LLM context window
        chart_data_str = json.dumps(body.chart_data, default=str)
        if len(chart_data_str) > 8000:
            chart_data_str = chart_data_str[:8000] + "... (truncated)"
        data_context = f"\nChart/Visualization data:\n{chart_data_str}"
    elif body.raw_data:
        raw_data_str = json.dumps(body.raw_data, default=str)
        if len(raw_data_str) > 8000:
            raw_data_str = raw_data_str[:8000] + "... (truncated)"
        data_context = f"\nRaw data:\n{raw_data_str}"

    if body.conversation_history:
        history_str = "\n".join(
            f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}"
            for msg in body.conversation_history[-10:]  # Last 10 messages
        )
        context_parts.append(f"\nConversation so far:\n{history_str}")

    context_str = "\n".join(context_parts)

    # Call LLM to generate explanation
    prompt = f"""You are a helpful data analyst assistant. The user has a visualization/chart and is asking a follow-up question about it.

Context:
{context_str}
{data_context}

User's question: {body.follow_up_text}

Provide a clear, helpful answer in plain language. If explaining a chart, describe:
- What the chart shows (the key metrics and dimensions)
- Key patterns or trends visible in the data
- Any notable outliers or interesting data points
- A simple summary a non-technical person would understand

Keep your response concise but informative. Use bullet points for clarity where appropriate."""

    try:
        from src.config import DEFAULT_MODEL_ID, get_bedrock_client

        client = get_bedrock_client()
        llm_body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1500,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}],
        })

        response = await asyncio.to_thread(
            client.invoke_model,
            modelId=DEFAULT_MODEL_ID,
            body=llm_body,
            contentType="application/json",
            accept="application/json",
        )

        response_body = json.loads(response["body"].read())

        # Track cost
        try:
            from src.services.cost_tracker import get_cost_tracker
            usage = response_body.get("usage", {})
            get_cost_tracker().log_invocation(
                model_id=DEFAULT_MODEL_ID,
                component="follow_up_query",
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
        except Exception:
            pass

        content = response_body.get("content", [])
        explanation_text = ""
        if content and len(content) > 0:
            explanation_text = content[0].get("text", "").strip()

        if not explanation_text:
            explanation_text = "I wasn't able to generate an explanation. Please try rephrasing your question."

        latency_ms = int((time.monotonic() - start_time) * 1000)

        from src.models.shared import RenderedOutput
        rendered_output = RenderedOutput(
            output_type="text",
            chart_type=None,
            chart_data=None,
            text_content=explanation_text,
            description=explanation_text,
            is_meta_query=False,
            metadata={
                "query_id": str(uuid_mod.uuid4()),
                "query_type": "follow_up",
                "entity_refs": body.metadata.get("entity_refs", []) if body.metadata else [],
                "latency_ms": latency_ms,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        )

        return JSONResponse(
            status_code=200,
            content={
                "rendered_output": rendered_output.model_dump(mode="json"),
                "correlation_id": correlation_id,
            },
        )

    except Exception as e:
        logger.error(f"Follow-up query LLM error: {e}")
        latency_ms = int((time.monotonic() - start_time) * 1000)

        from src.models.shared import RenderedOutput
        rendered_output = RenderedOutput(
            output_type="text",
            chart_type=None,
            chart_data=None,
            text_content=f"Unable to process follow-up question: {str(e)}",
            description="Error processing follow-up",
            metadata={
                "query_id": str(uuid_mod.uuid4()),
                "query_type": "follow_up_error",
                "latency_ms": latency_ms,
            },
        )

        return JSONResponse(
            status_code=200,
            content={
                "rendered_output": rendered_output.model_dump(mode="json"),
                "correlation_id": correlation_id,
            },
        )


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


async def _monitor_client_disconnect(
    request: Request, correlation_id: str
) -> bool:
    """Monitor the client connection and register cancellation on disconnect.

    Polls `request.is_disconnected()` every 0.25 seconds. When a disconnect
    is detected, registers the correlation ID in the cancellation registry
    and propagates cancellation to the Orchestrator Hub.

    Args:
        request: The inbound FastAPI request to monitor.
        correlation_id: The query identifier for cancellation tracking.

    Returns:
        True if client disconnected, False otherwise (never returns False
        in practice — only returns True or gets cancelled).
    """
    while True:
        await asyncio.sleep(0.25)
        if await request.is_disconnected():
            _cancellation_registry.register(correlation_id, source="disconnect")
            # Propagate to orchestrator (fire-and-forget within this task)
            await _propagate_cancellation_to_orchestrator(correlation_id)
            return True


@app.post("/query")
@observability_decorator("nlp_translator")
async def query_endpoint(request: Request, body: QueryRequest) -> JSONResponse:
    """Accept a natural language query and return rendered output.
    Orchestrates the full query flow:
    1. Check if this is a meta-query (capability question) — if so, return text response
    2. Translate query → StructuredIntent
    3. Call Orchestrator Hub /internal/process with intent
    4. Call Guardrail Layer /internal/validate with response + intent
    5. Call Visualization Renderer /internal/render with validated response
    6. Return RenderedOutput to client with latency breakdown
    If translation fails, returns 422 with NLPError details.
    Monitors client disconnect and cancels downstream processing if detected.

    Args:
        request: The inbound FastAPI request (for correlation ID extraction).
        body: The request body containing query_text.

    Returns:
        JSONResponse with rendered output (200) or error details (422/500).
    """
    import time
    import uuid

    correlation_id = extract_correlation_id(request)
    translator = get_translator()
    latency: dict[str, int] = {}
    total_start = time.monotonic()

    # Step 0: Meta-query detection (early exit for capability questions)
    if MetaQueryDetector.is_meta_query(body.query_text):
        meta_response = MetaQueryDetector.generate_meta_response(body.query_text)
        # Wrap in RenderedOutput format for frontend consistency
        from src.models.shared import RenderedOutput
        rendered_output = RenderedOutput(
            output_type="text",
            chart_type=None,
            chart_data=None,
            text_content=meta_response.get("text_content", ""),
            description=meta_response.get("description", ""),
            is_meta_query=True,
            metadata=meta_response.get("metadata", {
                "query_id": str(uuid.uuid4()),
                "query_type": "meta",
            }),
        )
        return JSONResponse(status_code=200, content=rendered_output.model_dump(mode="json"))

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
    
    # Step 0.75: Ontology Validation (Requirement #4)
    # Validate that all extracted entities exist in ontology before routing
    try:
        from src.services.ontology_store import OntologyStore
        
        ontology = OntologyStore()
        entity_refs = intent.entity_refs or []
        
        invalid_entities = []
        for entity_ref in entity_refs:
            # Use lookup_concept which returns None if not found
            if ontology.lookup_concept(entity_ref) is None:
                # Try search as fallback
                results = ontology.search_concepts(entity_ref)
                if not results:
                    invalid_entities.append(entity_ref)
        
        if invalid_entities:
            error_msg = f"Entities not found in ontology: {', '.join(invalid_entities)}"
            logger.warning(f"Ontology validation failed: {error_msg}")
            return JSONResponse(
                status_code=422,
                content={
                    "error_code": "ONTOLOGY_VALIDATION_ERROR",
                    "error_message": error_msg,
                    "query_id": str(intent.query_id),
                },
            )
    except Exception as e:
        logger.warning(f"Ontology validation error: {e}")
        # Continue anyway - validation is optional
    
    headers = propagation_headers(correlation_id)

    # Step 2: Call Orchestrator Hub (with disconnect detection)
    step_start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            # Start the orchestrator request
            orchestrator_task = asyncio.create_task(
                client.post(
                    f"{ORCHESTRATOR_URL}/internal/process",
                    json={"structured_intent": intent.model_dump(mode="json")},
                    headers=headers,
                )
            )

            # Monitor client disconnect while waiting for the orchestrator
            disconnect_task = asyncio.create_task(
                _monitor_client_disconnect(request, correlation_id)
            )

            # Wait for either the orchestrator response or client disconnect
            done, pending = await asyncio.wait(
                [orchestrator_task, disconnect_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel whichever task is still pending
            for task in pending:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

            # If disconnect was detected (disconnect_task completed first)
            if disconnect_task in done and disconnect_task.result() is True:
                # Client disconnected — cancel the orchestrator task
                logger.info(
                    f"Client disconnected during orchestrator call, "
                    f"correlation_id={correlation_id}"
                )
                return JSONResponse(
                    status_code=499,
                    content={
                        "error": "CLIENT_CLOSED_REQUEST",
                        "message": "Client disconnected",
                        "query_id": str(intent.query_id),
                    },
                )

            # Get the orchestrator response
            orchestrator_response = orchestrator_task.result()

            if orchestrator_response.status_code != 200:
                error_data = orchestrator_response.json()
                return JSONResponse(
                    status_code=orchestrator_response.status_code,
                    content=error_data,
                )

            orchestrator_data = orchestrator_response.json()

    except asyncio.CancelledError:
        # Task was cancelled (likely due to disconnect detection)
        _cancellation_registry.register(correlation_id, source="disconnect")
        await _propagate_cancellation_to_orchestrator(correlation_id)
        return JSONResponse(
            status_code=499,
            content={
                "error": "CLIENT_CLOSED_REQUEST",
                "message": "Request cancelled",
                "query_id": str(intent.query_id),
            },
        )
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

    # Step 3.5: Text-Only Detection (Requirement #6 - Option A)
    # Check if query should return text-only response instead of visualization
    try:
        from src.services.text_only_detector import TextOnlyDetector
        
        detector = TextOnlyDetector()
        if detector.should_use_text_only(body.query_text):
            # Generate text-only response instead of visualization
            logger.info(f"Text-only response for query: {body.query_text[:50]}...")
            
            # Extract data from orchestrator response
            # OrchestratorResponse has results[] with payload in each AgentResult
            orch_resp = orchestrator_data.get("orchestrator_response", orchestrator_data)
            results = orch_resp.get("results", [])
            
            # Merge all agent payloads into one data dict
            merged_data = {}
            for result in results:
                if isinstance(result, dict) and result.get("status") == "success":
                    payload = result.get("payload", {})
                    if payload:
                        merged_data.update(payload)
            
            from src.services.text_only_detector import TextSummaryGenerator
            summary_text = TextSummaryGenerator.generate_summary(merged_data, body.query_text)
            
            from src.models.shared import RenderedOutput
            rendered_output = RenderedOutput(
                output_type="text",
                chart_type=None,
                chart_data=None,
                text_content=summary_text,
                description=summary_text,
                metadata={
                    "query_id": str(intent.query_id),
                    "query_type": "text_only",
                    "entity_refs": intent.entity_refs or [],
                    "latency_ms": int((time.monotonic() - total_start) * 1000),
                },
            )
            
            latency["total_ms"] = int((time.monotonic() - total_start) * 1000)
            return JSONResponse(
                status_code=200,
                content={
                    "rendered_output": rendered_output.model_dump(mode="json"),
                    "latency_breakdown": latency,
                },
            )
    except Exception as e:
        logger.warning(f"Text-only detection error: {e}")
        # Continue to visualization - text detection is optional

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

    # Clean up cancellation entry on normal completion
    _cancellation_registry.remove(correlation_id)

    # Step 5: Ensure raw_data is included for chart type switching
    if isinstance(rendered_output, dict) and "raw_data" not in rendered_output:
        # Extract useful payload data from orchestrator response
        orch_data = orchestrator_data.get("orchestrator_response", orchestrator_data)
        if isinstance(orch_data, dict):
            # OrchestratorResponse has results: [{ status, payload, ... }]
            results = orch_data.get("results", [])
            if results:
                # Merge successful payloads
                merged_payload = {}
                for r in results:
                    if isinstance(r, dict) and r.get("status") == "success" and r.get("payload"):
                        merged_payload.update(r["payload"])
                if merged_payload:
                    rendered_output["raw_data"] = merged_payload
                else:
                    rendered_output["raw_data"] = orch_data
            else:
                rendered_output["raw_data"] = orch_data.get("data", orch_data)

    # Step 6: Return rendered output with latency breakdown
    return JSONResponse(
        status_code=200,
        content={
            "rendered_output": rendered_output,
            "latency": latency,
            "query_id": str(intent.query_id),
            "correlation_id": correlation_id,
        },
    )


@app.post("/api/re-render")
async def re_render_visualization(request: Request) -> JSONResponse:
    """Re-render a visualization with a different chart type.
    
    Called when user switches chart types on a card.
    Takes the original data + new chart type request and generates
    a new Chart.js configuration via the Visualization Renderer.
    
    Request body:
    {
        "original_data": {...},
        "requested_type": "line",
        "prompt": "...",
        "query": "...",
        "metadata": {...}
    }
    
    Returns: New RenderedOutput with the selected chart type.
    """
    import time
    import uuid as uuid_mod
    
    try:
        body = await request.json()
        correlation_id = extract_correlation_id(request)
        headers = propagation_headers(correlation_id)
        
        # Extract data - handle both raw data and Chart.js config formats
        original_data = body.get("original_data", {})
        requested_type = body.get("requested_type", "bar")
        original_query = body.get("query", "")
        
        # If original_data is a Chart.js config, extract the data portion
        if isinstance(original_data, dict) and "data" in original_data and "type" in original_data:
            # Check if it's an OrchestratorResponse (has "results" with "payload")
            if "results" in original_data and isinstance(original_data.get("results"), list):
                # It's an OrchestratorResponse — extract payload
                results = original_data["results"]
                merged = {}
                for r in results:
                    if isinstance(r, dict) and r.get("status") == "success" and r.get("payload"):
                        merged.update(r["payload"])
                original_data = merged if merged else original_data
            else:
                # It's a Chart.js config like { type: "scatter", data: { datasets: [...] } }
                chart_js_data = original_data.get("data", {})
                original_data = chart_js_data
        elif isinstance(original_data, dict) and "results" in original_data:
            # Full OrchestratorResponse without "type" key
            results = original_data["results"]
            merged = {}
            for r in results:
                if isinstance(r, dict) and r.get("status") == "success" and r.get("payload"):
                    merged.update(r["payload"])
            if merged:
                original_data = merged

        # Handle "text" type directly — no need for viz renderer
        if requested_type == "text":
            from src.services.text_only_detector import TextSummaryGenerator
            from src.models.shared import RenderedOutput
            
            # Use LLM to generate text summary from the data
            summary_text = TextSummaryGenerator.generate_summary(
                original_data, original_query
            )
            
            rendered = RenderedOutput(
                output_type="text",
                chart_type=None,
                chart_data=None,
                text_content=summary_text,
                description=summary_text,
                metadata={
                    "query_id": str(uuid_mod.uuid4()),
                    "query_type": "text_conversion",
                    "latency_ms": 0,
                },
            )
            return JSONResponse(status_code=200, content=rendered.model_dump(mode="json"))

        # Handle "table" type directly — format data as table
        if requested_type == "table":
            from src.models.shared import RenderedOutput
            
            # Try to extract columns and rows from the data
            columns = []
            rows = []
            
            if isinstance(original_data, dict):
                # Check if it has datasets (Chart.js format)
                if "datasets" in original_data and "labels" in original_data:
                    labels = original_data.get("labels", [])
                    datasets = original_data.get("datasets", [])
                    columns = ["Label"] + [ds.get("label", f"Series {i}") for i, ds in enumerate(datasets)]
                    rows = [[labels[i] if i < len(labels) else ""] + [str(ds.get("data", [])[i]) if i < len(ds.get("data", [])) else "" for ds in datasets] for i in range(len(labels))]
                elif "datasets" in original_data:
                    # Scatter/bubble format: datasets with {x, y} points
                    datasets = original_data.get("datasets", [])
                    columns = ["Dataset", "X", "Y"]
                    for ds in datasets:
                        ds_label = ds.get("label", "Data")
                        for point in ds.get("data", []):
                            if isinstance(point, dict):
                                rows.append([ds_label, str(point.get("x", "")), str(point.get("y", ""))])
                else:
                    # Generic dict — use keys as columns
                    columns = list(original_data.keys())
                    if columns:
                        # Single row of values
                        rows = [[str(original_data.get(c, "")) for c in columns]]
            
            table_data = {"type": "table", "columns": columns, "rows": rows}
            
            rendered = RenderedOutput(
                output_type="chart",
                chart_type="table",
                chart_data=table_data,
                text_content=None,
                description=f"Data displayed as table ({len(rows)} rows)",
                metadata={
                    "query_id": str(uuid_mod.uuid4()),
                    "query_type": "table_conversion",
                    "row_count": len(rows),
                    "latency_ms": 0,
                },
            )
            return JSONResponse(status_code=200, content=rendered.model_dump(mode="json"))
        
        # Build a valid OrchestratorResponse-compatible payload
        # The viz renderer expects: { query_id: UUID, results: [AgentResult] }
        query_id = str(uuid_mod.uuid4())
        renderer_payload = {
            "validated_response": {
                "query_id": query_id,
                "results": [
                    {
                        "status": "success",
                        "payload": original_data,
                        "agent_id": "re-render",
                        "data_source": "chart_conversion",
                    }
                ],
                "unavailable_agents": [],
            },
            "structured_intent": {
                "query_id": query_id,
                "query_type": "lookup",
                "entity_refs": ["chart_conversion"],
                "routing_metadata": {
                    "requested_chart_type": requested_type,
                    "query_text": original_query or f"Show data as {requested_type}",
                },
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        }
        
        step_start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                render_response = await client.post(
                    f"{VIZ_URL}/internal/render",
                    json=renderer_payload,
                    headers=headers,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            logger.warning(f"Visualization renderer unavailable: {e}")
            from src.models.shared import RenderedOutput
            return JSONResponse(
                status_code=200,
                content=RenderedOutput(
                    output_type="text",
                    text_content=f"Chart type conversion requested: {requested_type}",
                    description="Unable to render, showing data summary",
                    metadata={
                        "query_id": query_id,
                        "query_type": "re_render",
                        "latency_ms": int((time.monotonic() - step_start) * 1000),
                    }
                ).model_dump(mode="json")
            )
        
        if render_response.status_code == 200:
            rendered_data = render_response.json()
            # Ensure chart_type matches requested type
            if rendered_data.get("chart_data") and isinstance(rendered_data["chart_data"], dict):
                rendered_data["chart_data"]["type"] = requested_type
                rendered_data["chart_type"] = requested_type
            if rendered_data.get("metadata"):
                rendered_data["metadata"]["latency_ms"] = int((time.monotonic() - step_start) * 1000)
            return JSONResponse(status_code=200, content=rendered_data)
        else:
            error_body = render_response.json() if render_response.headers.get("content-type", "").startswith("application/json") else {}
            logger.error(f"Renderer failed with status {render_response.status_code}: {error_body}")
            return JSONResponse(
                status_code=500,
                content={"error": f"Failed to re-render visualization: {error_body.get('message', 'Unknown error')}"}
            )
            
    except Exception as e:
        logger.error(f"Re-render endpoint error: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error during re-render"}
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
