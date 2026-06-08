"""Bedrock model wrapper with cost tracking for Strands agents.

This module provides utilities to track Bedrock costs for Strands agents.
Uses the Strands SDK's built-in metrics (result.metrics.accumulated_usage)
to extract accurate token counts from agent responses.
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

    Extracts actual token counts from the Strands AgentResult.metrics.accumulated_usage
    dict which contains inputTokens, outputTokens, and totalTokens from all
    underlying Bedrock calls (including multi-turn tool-use rounds).

    Falls back to string-length estimation only if metrics are unavailable.

    Args:
        component: Component name (e.g., "orchestrator_hub", "visualization_renderer").
        model_id: The Bedrock model ID used.
        response: The Strands AgentResult object.
        correlation_id: Optional correlation ID for request tracing.
    """
    try:
        input_tokens = 0
        output_tokens = 0
        source = "estimated"

        # Primary: extract actual token counts from Strands AgentResult.metrics
        if hasattr(response, "metrics") and response.metrics is not None:
            accumulated_usage = getattr(response.metrics, "accumulated_usage", None)
            if accumulated_usage and isinstance(accumulated_usage, dict):
                input_tokens = accumulated_usage.get("inputTokens", 0)
                output_tokens = accumulated_usage.get("outputTokens", 0)
                if input_tokens > 0 or output_tokens > 0:
                    source = "strands_metrics"

        # Fallback: estimate from response string length if metrics unavailable
        if input_tokens == 0 and output_tokens == 0:
            response_text = str(response)
            output_tokens = len(response_text) // 4
            input_tokens = 150  # Conservative minimum for agent system prompt + user prompt
            source = "estimated"
            logger.warning(
                f"Cost tracking for {component}: Strands metrics unavailable, "
                f"using string-length estimation (output_tokens={output_tokens})"
            )

        if input_tokens > 0 or output_tokens > 0:
            get_cost_tracker().log_invocation(
                model_id=model_id,
                component=component,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                correlation_id=correlation_id,
                metadata={"source": source},
            )
    except Exception as e:
        # Don't let tracking failures break the agent
        logger.warning(f"Cost tracking failed for {component}: {e}")


