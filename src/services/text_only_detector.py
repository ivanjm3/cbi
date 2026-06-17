"""
Text-Only Output Detector

Uses a small LLM (Claude Haiku) to determine if a query should receive
a text-only response vs a visualization.

Requirement #6 - Option A with LLM classification.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Classification prompt for the LLM
CLASSIFICATION_PROMPT = """You are a query classifier for a business intelligence system.
Given a user's query, determine if the response should be:
- "text": The user expects a textual answer (a number, summary, explanation, or list)
- "chart": The user expects a visual chart or graph

Rules:
- If the query asks for a single value (total, count, average, sum), respond "text"
- If the query asks "what is", "how many", "how much", respond "text"
- If the query asks to "explain", "describe", "summarize", "list", respond "text"
- If the query asks to "compare X vs Y" without asking for a chart, respond "text"
- If the query mentions "chart", "graph", "plot", "visualize", "show me a", respond "chart"
- If the query asks for trends over time, distribution, or breakdown, respond "chart"
- If the query says "compare...against" with multiple dimensions, respond "chart"

Respond with ONLY the word "text" or "chart". Nothing else.

Query: "{query}"
"""


class TextOnlyDetector:
    """
    Uses LLM to classify queries as text-only or visualization.
    Falls back to keyword heuristics if LLM is unavailable.
    """

    def __init__(self):
        self._client = None
        self._model_id = None

    def _get_client(self):
        """Lazy-load Bedrock client."""
        if self._client is None:
            try:
                from src.config import get_bedrock_client, DEFAULT_MODEL_ID
                self._client = get_bedrock_client()
                self._model_id = DEFAULT_MODEL_ID
            except Exception as e:
                logger.warning(f"Failed to initialize Bedrock client: {e}")
                self._client = False  # Mark as unavailable
        return self._client if self._client is not False else None

    def should_use_text_only(self, query: str) -> bool:
        """
        Determine if query should return text-only response.
        Uses LLM classification with keyword fallback.

        Args:
            query: User's query text

        Returns:
            True if text-only, False if visualization should be attempted
        """
        # Try LLM classification first
        try:
            client = self._get_client()
            if client:
                result = self._classify_with_llm(query, client)
                if result is not None:
                    return result
        except Exception as e:
            logger.warning(f"LLM classification failed, falling back to heuristics: {e}")

        # Fallback to keyword heuristics
        return self._classify_with_keywords(query)

    def _classify_with_llm(self, query: str, client) -> bool | None:
        """
        Classify query using Bedrock Claude Haiku.

        Args:
            query: User's query text
            client: Bedrock runtime client

        Returns:
            True if text-only, False if chart, None if classification failed
        """
        try:
            prompt = CLASSIFICATION_PROMPT.format(query=query)

            response = client.invoke_model(
                modelId=self._model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 10,
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                }),
            )

            response_body = json.loads(response["body"].read())
            content = response_body.get("content", [])

            if content and len(content) > 0:
                answer = content[0].get("text", "").strip().lower()
                logger.info(f"LLM classification for '{query[:50]}...': {answer}")

                if answer == "text":
                    return True
                elif answer == "chart":
                    return False

            logger.warning(f"LLM returned unexpected classification: {content}")
            return None

        except Exception as e:
            logger.warning(f"LLM classification error: {e}")
            return None

    def _classify_with_keywords(self, query: str) -> bool:
        """
        Fallback keyword-based classification.

        Args:
            query: User's query text

        Returns:
            True if text-only, False if visualization
        """
        query_lower = query.lower().strip()

        # Chart-forcing keywords (override everything)
        chart_keywords = [
            "visualize", "chart", "graph", "plot", "diagram",
            "bar chart", "line chart", "scatter", "pie chart",
            "heatmap", "show me a",
        ]
        for kw in chart_keywords:
            if kw in query_lower:
                return False

        # Text-only keywords
        text_keywords = [
            "what is the total",
            "what is the average",
            "how many",
            "how much",
            "what is",
            "what are",
            "explain",
            "describe",
            "summarize",
            "summary",
            "list all",
            "list the",
            "count of",
            "total revenue",
            "total sales",
            "total cost",
        ]
        for kw in text_keywords:
            if kw in query_lower:
                return True

        # Default to chart
        return False

    @staticmethod
    def get_text_only_query_type(query: str) -> str:
        """
        Classify the type of text-only query.

        Args:
            query: User's query text

        Returns:
            Query type classification
        """
        query_lower = query.lower()

        if any(kw in query_lower for kw in ["explain", "describe", "what is"]):
            return "explanation"
        elif any(kw in query_lower for kw in ["summarize", "summary"]):
            return "summary"
        elif any(kw in query_lower for kw in ["how many", "count", "total"]):
            return "count"
        elif any(kw in query_lower for kw in ["list", "show all", "get all"]):
            return "list"
        elif any(kw in query_lower for kw in ["compare", "difference"]):
            return "comparison"
        else:
            return "other"


class TextSummaryGenerator:
    """
    Generates text summaries for data results.
    Uses LLM when available, falls back to simple formatting.
    """

    @staticmethod
    def generate_summary(data: Any, query: str, max_length: int = 500) -> str:
        """
        Generate a text summary of data results.

        Args:
            data: Query result data
            query: Original query for context
            max_length: Max summary length

        Returns:
            Text summary string
        """
        # Try LLM-based summary
        try:
            from src.config import get_bedrock_client, DEFAULT_MODEL_ID
            client = get_bedrock_client()

            prompt = f"""Given this data from a business query, provide a concise text answer.

Query: "{query}"
Data: {json.dumps(data, default=str)[:2000]}

Provide a direct, concise answer to the query. If it asks for a total or count, give the number. If it asks for a list, provide the list. Keep it under 3 sentences unless a longer explanation is needed."""

            response = client.invoke_model(
                modelId=DEFAULT_MODEL_ID,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 300,
                    "temperature": 0,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                }),
            )

            response_body = json.loads(response["body"].read())
            content = response_body.get("content", [])
            if content and len(content) > 0:
                return content[0].get("text", "").strip()

        except Exception as e:
            logger.warning(f"LLM summary generation failed: {e}")

        # Fallback to simple formatting
        return TextSummaryGenerator._simple_summary(data, max_length)

    @staticmethod
    def _simple_summary(data: Any, max_length: int) -> str:
        """Simple fallback summary without LLM."""
        if isinstance(data, dict):
            items = []
            for key, value in list(data.items())[:5]:
                if isinstance(value, (int, float)):
                    items.append(f"{key}: {value:,.2f}" if isinstance(value, float) else f"{key}: {value:,}")
                else:
                    items.append(f"{key}: {str(value)[:50]}")
            summary = "Results: " + ", ".join(items)
            if len(data) > 5:
                summary += f" (and {len(data) - 5} more)"
            return summary[:max_length]

        elif isinstance(data, list):
            if len(data) == 0:
                return "No results found."
            summary = f"Retrieved {len(data)} results"
            if len(data) <= 5:
                summary += ": " + ", ".join(str(item) for item in data)
            else:
                preview = ", ".join(str(item) for item in data[:3])
                summary += f": {preview}, and {len(data) - 3} more"
            return summary[:max_length]

        return str(data)[:max_length]
