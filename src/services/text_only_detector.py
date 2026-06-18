"""
Text-Only Output Detector

Uses a small LLM (Amazon Nova Micro) to determine if a query should receive
a text-only response vs a visualization.

Requirement #6 - Option A with LLM classification.
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Classification prompt for the LLM
CLASSIFICATION_PROMPT = """You are a query classifier
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

        Group-by queries (containing "by X", "per X", "vs") always return
        False (chart) regardless of LLM output, because they produce
        multi-row results that are best visualized.

        Args:
            query: User's query text

        Returns:
            True if text-only, False if visualization should be attempted
        """
        # Hard override: group-by queries are ALWAYS charts
        # These produce multi-row breakdowns that should be visualized
        query_lower = query.lower().strip()
        group_by_indicators = [
            " by ", " per ", " across ", " for each ", " grouped by ",
            " breakdown", " distribution", " vs ", " versus ",
        ]
        for kw in group_by_indicators:
            if kw in query_lower:
                return False

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
        Classify query using Amazon Nova Micro (optimized for cost).

        Args:
            query: User's query text
            client: Bedrock runtime client

        Returns:
            True if text-only, False if chart, None if classification failed
        """
        try:
            prompt = CLASSIFICATION_PROMPT.format(query=query)
            
            # Use Amazon Nova Micro for cost optimization
            model_id = "us.amazon.nova-micro-v1:0"

            response = client.invoke_model(
                modelId=model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "schemaVersion": "messages-v1",
                    "messages": [
                        {
                            "role": "user",
                            "content": [{"text": prompt}],
                        }
                    ],
                    "inferenceConfig": {
                        "maxTokens": 10,
                        "temperature": 0.0,
                    },
                }),
            )

            response_body = json.loads(response["body"].read())
            # Nova response format: output.message.content[0].text
            output = response_body.get("output", {})
            message = output.get("message", {})
            content = message.get("content", [])

            if content and len(content) > 0:
                answer = content[0].get("text", "").strip().lower()
                logger.info(f"LLM classification for '{query[:50]}...': {answer}")

                if answer == "text":
                    return True
                elif answer == "chart":
                    return False

            logger.warning(f"LLM returned unexpected classification: {response_body}")
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

        # GROUP BY indicators — these produce multi-row results best shown as charts
        # Must check BEFORE text-only keywords since "average X by Y" is a chart
        group_by_keywords = [
            " by ", " per ", " across ", " for each ", " grouped by ",
            " breakdown", " distribution", " vs ", " versus ",
        ]
        for kw in group_by_keywords:
            if kw in query_lower:
                return False

        # Text-only keywords (only when NOT asking for a breakdown)
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
        Applies smart filtering for numeric constraints found in the query.

        Args:
            data: Query result data
            query: Original query for context
            max_length: Max summary length

        Returns:
            Text summary string
        """
        # First, try to apply numeric filtering if the query contains constraints
        filtered_data = TextSummaryGenerator._apply_query_filters(data, query)

        # Try LLM-based summary
        try:
            from src.config import get_bedrock_client, DEFAULT_MODEL_ID
            client = get_bedrock_client()

            prompt = f"""Given this data from a business query, provide a concise text answer.

Query: "{query}"
Data: {json.dumps(filtered_data, default=str)[:2000]}

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
        return TextSummaryGenerator._simple_summary(filtered_data, max_length)

    @staticmethod
    def _apply_query_filters(data: Any, query: str) -> Any:
        """
        Apply numeric filters based on query constraints.
        E.g., "below 50", "greater than 100", "less than", etc.
        
        Args:
            data: Original data
            query: User's query string
            
        Returns:
            Filtered data
        """
        import re
        
        if not isinstance(data, (list, dict)):
            return data
        
        query_lower = query.lower()
        
        # Parse numeric constraints from query
        # Patterns: "below X", "less than X", "greater than X", "more than X", "over X", "under X"
        constraints = []
        
        # Below/Less than/Under
        below_match = re.search(r'(?:below|less than|under|less than|<)\s+(\d+)', query_lower)
        if below_match:
            threshold = int(below_match.group(1))
            constraints.append(('below', threshold))
        
        # Above/Greater than/Over/More than
        above_match = re.search(r'(?:above|greater than|over|more than|>)\s+(\d+)', query_lower)
        if above_match:
            threshold = int(above_match.group(1))
            constraints.append(('above', threshold))
        
        # If no constraints found, return data as-is
        if not constraints:
            return data
        
        # Apply constraints to data
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            # Find numeric columns to filter on
            first_row = data[0]
            numeric_cols = [k for k, v in first_row.items() if isinstance(v, (int, float))]
            
            if not numeric_cols:
                return data
            
            filtered = []
            for row in data:
                matches_all = True
                for col in numeric_cols:
                    val = row.get(col)
                    if not isinstance(val, (int, float)):
                        continue
                    
                    for op, threshold in constraints:
                        if op == 'below' and val >= threshold:
                            matches_all = False
                            break
                        elif op == 'above' and val <= threshold:
                            matches_all = False
                            break
                    
                    if not matches_all:
                        break
                
                if matches_all:
                    filtered.append(row)
            
            return filtered if filtered else data
        
        return data

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
