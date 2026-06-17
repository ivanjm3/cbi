"""Follow-up query handler for strand-based conversations.

Processes follow-up queries in the context of previous visualization results.
Integrates with the strand conversation framework to enable multi-turn
interactions on visualization cards.

Requirements: 10.6 (multi-turn context management)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FollowUpRequest(BaseModel):
    """Request body for /api/follow-up endpoint."""
    query: str
    raw_data: dict[str, Any] | None = None
    metadata: dict[str, Any]
    follow_up_query: str


class FollowUpResponse(BaseModel):
    """Response body from /api/follow-up endpoint."""
    description: str
    text_content: str | None = None
    output_type: str = "text"
    metadata: dict[str, Any]


def process_follow_up_query(
    follow_up: FollowUpRequest,
    translator: Any,
    orchestrator: Any,
) -> FollowUpResponse | dict[str, Any]:
    """Process a follow-up query within strand context.

    Reuses the previous query's resolved entities and routing metadata
    to provide context-aware responses without re-parsing the entire query.

    This is an optimized path that:
    1. Reuses entity references from the original query
    2. Applies follow-up-specific intent (e.g., "show trends" → aggregation)
    3. Routes to the same agent that handled the original query
    4. Returns focused results that relate to previous context

    Args:
        follow_up: The follow-up query request with strand context.
        translator: NLP translator instance.
        orchestrator: Orchestrator hub instance.

    Returns:
        FollowUpResponse with text and metadata, or error dict.
    """
    try:
        # Build follow-up context payload
        follow_up_text = follow_up.follow_up_query

        if not follow_up_text or not follow_up_text.strip():
            return {
                "error_code": "EMPTY_FOLLOW_UP",
                "error_message": "Follow-up query cannot be empty.",
            }

        # Log follow-up for analytics
        logger.info(
            json.dumps({
                "service_name": "follow_up_handler",
                "event": "follow_up_query_received",
                "original_query": follow_up.query,
                "follow_up_text": follow_up_text[:100],
                "strand_context": bool(follow_up.metadata),
            })
        )

        # For now, return a placeholder response
        # In production, this would:
        # 1. Reuse metadata.entity_refs from original query
        # 2. Detect follow-up type (refinement, drill-down, comparison)
        # 3. Call orchestrator with context
        # 4. Format response as text or new visualization

        response_text = (
            f"You asked: {follow_up_text}\n\n"
            f"Based on your previous query about: {follow_up.query}\n\n"
            f"I'm ready to provide follow-up insights. "
            f"(This is a placeholder. Full follow-up processing will be implemented in the next phase.)"
        )

        return FollowUpResponse(
            description=response_text,
            text_content=response_text,
            output_type="text",
            metadata={
                "query_id": str(uuid.uuid4()),
                "query_type": "follow_up",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "related_to_original": True,
            },
        )

    except Exception as e:
        logger.error(
            json.dumps({
                "service_name": "follow_up_handler",
                "event": "follow_up_processing_error",
                "error_type": type(e).__name__,
                "error_message": str(e),
            })
        )
        return {
            "error_code": "FOLLOW_UP_FAILED",
            "error_message": "Failed to process follow-up query.",
        }
