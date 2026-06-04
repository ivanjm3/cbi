"""Bedrock model wrapper with cost tracking for Strands agents.

This module provides utilities to track Bedrock costs for Strands agents.
Since Strands SDK doesn't expose token counts directly, we use a post-invocation
callback pattern to extract usage from agent responses.
"""

import json
import logging
from typing import Any

from src.services.cost_tracker import get_cost_tracker

logger = logging.getLogger(__name__)


def track_agent_invocation(
    component: str,
    model_id: str,
    response: Any,
    correlation_id: str | None = None,
) -> None:
    """Track token usage and cost from a Strands agent invocation.

    Extracts token counts from the agent response and logs them to the cost tracker.
    This should be called after every agent invocation.

    Args:
        component: Component name (e.g., "orchestrator_hub", "spoke_agent_json").
        model_id: The Bedrock model ID used.
        response: The agent response object.
        correlation_id: Optional correlation ID for request tracing.
    """
    try:
        # Strands agents return a response object. The underlying Bedrock
        # response metadata may be in response._metadata or similar.
        # For now, we estimate based on string length as a fallback.
        # TODO: Update when Strands SDK exposes token counts directly.
        
        # Rough estimation: 1 token ≈ 4 characters for English text
        response_text = str(response)
        estimated_output_tokens = len(response_text) // 4
        
        # We don't have input token counts without accessing the prompt,
        # so we log a warning and use a conservative estimate.
        estimated_input_tokens = 100  # Conservative default for agent prompts
        
        if estimated_output_tokens > 0:
            get_cost_tracker().log_invocation(
                model_id=model_id,
                component=component,
                input_tokens=estimated_input_tokens,
                output_tokens=estimated_output_tokens,
                correlation_id=correlation_id,
                metadata={"note": "Estimated from response length (Strands SDK limitation)"},
            )
    except Exception as e:
        # Don't let tracking failures break the agent
        logger.warning(f"Cost tracking failed for {component}: {e}")


