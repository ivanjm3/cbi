"""FastAPI application for the Visualization Renderer service.

Exposes POST /internal/render endpoint that transforms validated responses
into chart or text visualizations using rule-based chart selection.

Runs on port 8004.

Requirements: 8.5, 8.6, 11.4
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.services.logging_config import configure_logging
configure_logging()

from src.config import VIZ_PORT
from src.models.shared import OrchestratorResponse, StructuredIntent
from src.services.observability import (
    extract_correlation_id,
    observability_decorator,
)
from src.services.visualization_renderer import VisualizationRenderer

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Visualization Renderer Service",
    description="Transforms validated responses into chart or text visualizations.",
    version="1.0.0",
)

# Module-level renderer instance
_renderer: VisualizationRenderer | None = None


def get_renderer() -> VisualizationRenderer:
    """Get or create the VisualizationRenderer instance."""
    global _renderer
    if _renderer is None:
        _renderer = VisualizationRenderer()
    return _renderer


def set_renderer(renderer: VisualizationRenderer) -> None:
    """Override the renderer instance (for testing)."""
    global _renderer
    _renderer = renderer


class RenderRequest(BaseModel):
    """Request body for POST /internal/render."""

    validated_response: dict
    structured_intent: dict


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "visualization_renderer",
        "port": VIZ_PORT,
    }


@app.post("/internal/render")
@observability_decorator("visualization_renderer")
async def render_endpoint(request: Request, body: RenderRequest) -> JSONResponse:
    """Render a validated response into a visualization.

    Args:
        request: The inbound FastAPI request.
        body: Request body with validated_response and structured_intent.

    Returns:
        JSONResponse with RenderedOutput (200) or error (500).
    """
    correlation_id = extract_correlation_id(request)
    renderer = get_renderer()

    # Parse inputs
    try:
        response = OrchestratorResponse.model_validate(body.validated_response)
        intent = StructuredIntent.model_validate(body.structured_intent)
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={
                "error": "INVALID_INPUT",
                "message": f"Failed to parse request: {e}",
            },
        )

    # Render
    try:
        intent_metadata = {
            "query_id": str(intent.query_id),
            "query_type": intent.query_type,
            "query_text": intent.routing_metadata.get("query_text", ""),
            "requested_chart_type": intent.routing_metadata.get("requested_chart_type"),
        }
        rendered = await renderer.render(response, intent_metadata)

        return JSONResponse(
            status_code=200,
            content=rendered.model_dump(mode="json"),
        )

    except Exception as e:
        logger.error(f"Render failure: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "error_type": "RENDER_FAILURE",
                "message": str(e),
            },
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=VIZ_PORT)
