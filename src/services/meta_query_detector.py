"""Meta-query detection service.

Distinguishes between meta-queries (capability questions, system queries)
and data queries. Meta-queries get text responses without visualization attempts.

Meta-query patterns:
- "what can you do?"
- "what are your capabilities?"
- "who are you?"
- "help", "how does this work?"
- "explain..."

Data queries get full visualization pipeline.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class MetaQueryDetector:
    """Detects if a query is a meta-query or a data query."""

    # Meta-query keywords and patterns
    META_PATTERNS = [
        # Capability/System questions
        r"\b(what\s+(can\s+)?you|your\s+capabilities?|what.*do\s+you)\b",
        r"\b(help|how.*works?)\b",
        r"\b(who\s+are\s+you|what\s+are\s+you)\b",
        r"\b(commands?|functions?|features?)\s+(available|do\s+you\s+have)\b",
        r"\b(supported|available)\s+(features?|queries?|operations?)\b",
        r"\b(how\s+do\s+i|how\s+to|tutorial|guide)\b",
        r"\b(documentation|docs|readme)\b",
        r"\b(what.*language|what\s+database|what\s+data\s+sources?)\b",
        r"\b(limitations?|constraints?|restrictions?)\b",
        r"\b(examples?|sample|demo)\s+(query|queries|request)\b",
    ]

    @classmethod
    def is_meta_query(cls, query_text: str) -> bool:
        """Detect if a query is a meta-query (capability/system question).

        Args:
            query_text: The user's query text.

        Returns:
            True if this is a meta-query, False if it's a data query.
        """
        text = query_text.strip().lower()

        # Check each meta-pattern
        for pattern in cls.META_PATTERNS:
            if re.search(pattern, text):
                logger.debug(
                    json.dumps({
                        "service_name": "meta_query_detector",
                        "operation": "is_meta_query",
                        "event": "meta_query_detected",
                        "pattern": pattern,
                        "query_text": query_text[:100],
                    })
                )
                return True

        return False

    @classmethod
    def generate_meta_response(cls, query_text: str) -> dict[str, Any]:
        """Generate a text response for a meta-query.

        Args:
            query_text: The user's meta-query text.

        Returns:
            A response dict formatted as RenderedOutput (text-only).
        """
        import uuid
        from datetime import datetime, timezone
        
        query_lower = query_text.lower()

        if any(kw in query_lower for kw in ["what can you do", "capabilities", "features"]):
            content = (
                "I'm a conversational BI assistant. I can help you:\n\n"
                "• Query your data using natural language (e.g., 'show me sales by region')\n"
                "• Generate interactive visualizations (bar charts, line charts, scatter plots, pie charts, etc.)\n"
                "• Compare datasets and time periods\n"
                "• Explore trends and aggregations\n"
                "• Save and restore your analysis sessions\n"
                "• Switch between different chart types\n"
                "• Ask follow-up questions with full context\n\n"
                "Try asking me a business question like 'What was the total revenue last quarter?' "
                "or 'Show me product sales trends over the past year.'"
            )
        elif any(kw in query_lower for kw in ["who are you", "what are you"]):
            content = (
                "I'm a conversational BI system powered by Claude 3.5 Haiku. "
                "I help you explore and understand your data through natural language queries and interactive visualizations. "
                "Just ask me questions about your data and I'll provide insights with charts and tables."
            )
        elif any(kw in query_lower for kw in ["help", "how does this work"]):
            content = (
                "Here's how to get started:\n\n"
                "1. Type a natural language question about your data\n"
                "2. I'll understand your question and query the relevant data sources\n"
                "3. Results appear as an interactive visualization card\n"
                "4. You can follow up with more questions about the same data\n"
                "5. Click the visualization type dropdown to switch between chart types\n"
                "6. Use the conversation panel to ask follow-up questions\n\n"
                "Example queries:\n"
                "• 'Show me quarterly sales revenue'\n"
                "• 'What products had the highest growth?'\n"
                "• 'Compare Q1 vs Q2 performance by region'"
            )
        else:
            content = (
                "I'm a conversational BI assistant. I can help you explore and visualize your data. "
                "Ask me questions like 'What's the revenue trend?' or 'Show me sales by product category.' "
                "Type 'help' for more information."
            )

        return {
            "output_type": "text",
            "chart_type": None,
            "chart_data": None,
            "text_content": content,
            "description": "Meta-query response",
            "is_meta_query": True,
            "metadata": {
                "query_id": str(uuid.uuid4()),
                "query_type": "meta",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "latency_ms": 0,
                "data_sources": [],
                "entity_refs": [],
            },
        }
