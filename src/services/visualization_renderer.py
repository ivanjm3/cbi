"""Visualization Renderer — Strands Agent with dynamic chart generation.

Transforms validated agent responses into dynamic, context-aware visualizations
using LLM reasoning to select chart types, configure interactivity, and add
statistical annotations.

The Renderer is a Strands Agent instance that reasons about data shape, query
intent, and context to produce the most effective visualization. Includes a
deterministic fallback path if the LLM is unavailable.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from strands import Agent, tool

from src.models.shared import OrchestratorResponse, RenderedOutput

logger = logging.getLogger(__name__)

# Date/time patterns for fallback rule-based detection
DATE_PATTERNS = (
    "date", "time", "timestamp", "created", "updated",
    "quarter", "month", "year", "week", "day", "period",
)


@tool
def analyze_data_structure(columns: str, sample_rows: str, row_count: int, query_type: str) -> str:
    """Analyze the data structure to identify column types, patterns, and relationships.
    Examines the columns and sample rows to determine:
    - Which columns are numeric vs categorical vs temporal
    - Data cardinality and distribution characteristics
    - Whether the data represents a time series, comparison, or aggregation
    - Statistical properties (ranges, potential outliers)

    Args:
        columns: JSON array of column names.
        sample_rows: JSON array of sample data rows (first 10 rows).
        row_count: Total number of rows in the dataset.
        query_type: The query type from the structured intent (lookup, aggregation, comparison).

    Returns:
        JSON analysis with column_types, patterns, and recommendations.
    """
    try:
        cols = json.loads(columns)
        rows = json.loads(sample_rows)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON input"})

    analysis: dict[str, Any] = {
        "columns": {},
        "row_count": row_count,
        "query_type": query_type,
        "patterns": [],
    }

    # Analyze each column
    for i, col in enumerate(cols):
        col_values = [row[i] for row in rows if i < len(row)]
        col_type = _infer_column_type(col, col_values)
        analysis["columns"][col] = {
            "type": col_type,
            "sample_values": col_values[:5],
            "unique_count": len(set(str(v) for v in col_values)),
        }

        if col_type == "numeric" and col_values:
            numeric_vals = [v for v in col_values if isinstance(v, (int, float))]
            if numeric_vals:
                analysis["columns"][col]["min"] = min(numeric_vals)
                analysis["columns"][col]["max"] = max(numeric_vals)
                analysis["columns"][col]["mean"] = sum(numeric_vals) / len(numeric_vals)

    # Detect patterns
    numeric_cols = [c for c, info in analysis["columns"].items() if info["type"] == "numeric"]
    temporal_cols = [c for c, info in analysis["columns"].items() if info["type"] == "temporal"]
    categorical_cols = [c for c, info in analysis["columns"].items() if info["type"] == "categorical"]

    if temporal_cols and numeric_cols:
        analysis["patterns"].append("time_series")
    if len(numeric_cols) >= 2 and not categorical_cols:
        analysis["patterns"].append("multi_numeric")
    if categorical_cols and numeric_cols:
        analysis["patterns"].append("categorical_numeric")
    if query_type == "comparison":
        analysis["patterns"].append("comparison")
    if query_type == "aggregation":
        analysis["patterns"].append("aggregation")

    return json.dumps(analysis, default=str)


@tool
def generate_chart_spec(
    chart_type: str,
    columns: str,
    rows: str,
    title: str,
    options: str,
) -> str:
    """Generate a Chart.js/Vega-Lite compatible chart specification.

    Creates a complete chart spec with:
    - Data mapping (labels, datasets)
    - Interactive features (tooltips, hover effects)
    - Visual styling (colors, fonts, spacing)
    - Annotations (trend lines, averages, highlights)

    Args:
        chart_type: One of "bar", "line", "scatter", "pie", "table".
        columns: JSON array of column names.
        rows: JSON array of data rows.
        title: Chart title.
        options: JSON object with additional chart options (annotations, colors, etc).

    Returns:
        JSON chart specification compatible with Chart.js.
    """
    try:
        cols = json.loads(columns)
        data_rows = json.loads(rows)
        opts = json.loads(options) if options else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON input"})

    if chart_type == "table":
        return json.dumps({
            "type": "table",
            "title": title,
            "columns": cols,
            "rows": data_rows[:100],
            "total_rows": len(data_rows),
        })

    # Build chart spec based on type
    spec: dict[str, Any] = {
        "type": chart_type,
        "title": title,
        "options": {
            "responsive": True,
            "interaction": {"mode": "index", "intersect": False},
            "plugins": {
                "tooltip": {"enabled": True},
                "legend": {"display": True, "position": "top"},
            },
        },
    }

    if chart_type == "line":
        spec.update(_build_line_spec(cols, data_rows, opts))
    elif chart_type == "bar":
        spec.update(_build_bar_spec(cols, data_rows, opts))
    elif chart_type == "scatter":
        spec.update(_build_scatter_spec(cols, data_rows, opts))
    elif chart_type == "pie":
        spec.update(_build_pie_spec(cols, data_rows, opts))

    # Add annotations if specified
    if opts.get("show_trend_line"):
        spec["options"]["plugins"]["annotation"] = {"annotations": {"trend": {"type": "line"}}}
    if opts.get("show_average"):
        spec["options"]["plugins"]["annotation"] = spec["options"].get("plugins", {}).get("annotation", {})

    return json.dumps(spec, default=str)


@tool
def generate_visualization_description(
    chart_type: str,
    data_summary: str,
    query_context: str,
    key_insights: str,
) -> str:
    """Generate a human-readable description of the visualization with statistical insights.

    Creates a narrative description that explains:
    - What the chart shows
    - Key data patterns or trends
    - Notable statistics (highs, lows, averages)
    - How to interpret the visualization

    Args:
        chart_type: The chart type being rendered.
        data_summary: Summary of the data being visualized (column types, row count, ranges).
        query_context: The original query context (query_type, entity_refs).
        key_insights: Notable patterns or statistics identified during analysis.

    Returns:
        A human-readable description string.
    """
    return json.dumps({
        "chart_type": chart_type,
        "data_summary": data_summary,
        "query_context": query_context,
        "key_insights": key_insights,
    })


# --- Helper functions for chart spec generation ---

def _build_line_spec(cols: list[str], rows: list[list], opts: dict) -> dict:
    """Build line chart data specification."""
    # Find temporal and numeric columns
    time_col_idx = 0
    for i, col in enumerate(cols):
        if any(p in col.lower() for p in DATE_PATTERNS):
            time_col_idx = i
            break

    numeric_indices = [
        i for i, col in enumerate(cols)
        if i != time_col_idx and rows and isinstance(rows[0][i] if i < len(rows[0]) else None, (int, float))
    ]

    labels = [str(row[time_col_idx]) for row in rows if time_col_idx < len(row)]
    datasets = []
    colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f"]

    for idx, col_idx in enumerate(numeric_indices[:5]):
        data = [row[col_idx] for row in rows if col_idx < len(row)]
        datasets.append({
            "label": cols[col_idx],
            "data": data,
            "borderColor": colors[idx % len(colors)],
            "fill": False,
            "tension": 0.1,
        })

    return {"labels": labels, "datasets": datasets}


def _build_bar_spec(cols: list[str], rows: list[list], opts: dict) -> dict:
    """Build bar chart data specification."""
    if not rows or not cols:
        return {"labels": [], "datasets": []}

    # Find categorical and numeric columns
    cat_idx = None
    num_indices = []
    for i, col in enumerate(cols):
        if rows and isinstance(rows[0][i] if i < len(rows[0]) else None, (int, float)):
            num_indices.append(i)
        elif cat_idx is None:
            # Skip "source" column in favor of more meaningful categories
            if col.lower() != "source":
                cat_idx = i

    # Fallback to first categorical if all were "source"
    if cat_idx is None:
        for i, col in enumerate(cols):
            if not (rows and isinstance(rows[0][i] if i < len(rows[0]) else None, (int, float))):
                cat_idx = i
                break
    if cat_idx is None:
        cat_idx = 0

    labels = [str(row[cat_idx]) for row in rows if cat_idx < len(row)]
    datasets = []
    colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f"]

    for idx, num_idx in enumerate(num_indices[:5]):
        data = [row[num_idx] for row in rows if num_idx < len(row)]
        datasets.append({
            "label": cols[num_idx],
            "data": data,
            "backgroundColor": colors[idx % len(colors)],
        })

    return {"labels": labels, "datasets": datasets}


def _build_scatter_spec(cols: list[str], rows: list[list], opts: dict) -> dict:
    """Build scatter plot data specification."""
    numeric_indices = [
        i for i, col in enumerate(cols)
        if rows and isinstance(rows[0][i] if i < len(rows[0]) else None, (int, float))
    ]

    if len(numeric_indices) < 2:
        return {"datasets": []}

    x_idx, y_idx = numeric_indices[0], numeric_indices[1]
    points = [
        {"x": row[x_idx], "y": row[y_idx]}
        for row in rows
        if x_idx < len(row) and y_idx < len(row)
    ]

    return {
        "datasets": [{
            "label": f"{cols[x_idx]} vs {cols[y_idx]}",
            "data": points,
            "backgroundColor": "#4e79a7",
        }],
        "options": {
            "scales": {
                "x": {"title": {"display": True, "text": cols[x_idx]}},
                "y": {"title": {"display": True, "text": cols[y_idx]}},
            }
        },
    }


def _build_pie_spec(cols: list[str], rows: list[list], opts: dict) -> dict:
    """Build pie chart data specification."""
    if not rows or not cols:
        return {"labels": [], "datasets": []}

    cat_idx = None
    num_idx = None
    for i, col in enumerate(cols):
        if rows and isinstance(rows[0][i] if i < len(rows[0]) else None, (int, float)):
            if num_idx is None:
                num_idx = i
        elif cat_idx is None:
            cat_idx = i

    if cat_idx is None:
        cat_idx = 0
    if num_idx is None:
        num_idx = 1 if len(cols) > 1 else 0

    labels = [str(row[cat_idx]) for row in rows if cat_idx < len(row)]
    data = [row[num_idx] for row in rows if num_idx < len(row)]
    colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1", "#ff9da7"]

    return {
        "labels": labels,
        "datasets": [{
            "data": data,
            "backgroundColor": colors[:len(labels)],
        }],
    }


def _infer_column_type(col_name: str, values: list) -> str:
    """Infer column type from name and values."""
    if any(p in col_name.lower() for p in DATE_PATTERNS):
        return "temporal"
    if values and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values if v is not None):
        return "numeric"
    return "categorical"


# --- Visualization Renderer System Prompt ---

VISUALIZER_SYSTEM_PROMPT = """\
You are an expert data visualization and BI analyst agent. Your job is to analyze data \
and produce the single most insightful, appropriate visualization.

Your analysis process:
1. Examine the data columns, types, and values to understand what the data represents.
2. Consider the user's original query to understand what insight they're looking for.
3. If the user explicitly requested a chart type (scatter, line, bar, pie), use that type.
4. Otherwise, choose the chart type that best reveals patterns and insights:
   - Time series or trends over periods → line chart
   - Correlation between two numeric variables → scatter plot
   - Category comparisons with ≤6 items → pie chart (proportional)
   - Category comparisons with many items → bar chart
   - Distribution or ranking → bar chart
   - Dense multi-column data → table
5. Generate the chart specification and provide BI insights.

Output EXACTLY one JSON object (no other text):
{
  "chart_type": "bar|line|scatter|pie|table",
  "title": "Descriptive title",
  "description": "Key insights: what patterns, outliers, or trends are visible. \
What business decisions could this data inform?",
  "chart_data": {<Chart.js compatible spec with labels, datasets, colors>}
}
"""


class VisualizationRenderer:
    """Strands Agent-based visualization renderer.

    Uses LLM reasoning to analyze data and produce context-aware,
    dynamic chart specifications. Falls back to rule-based selection
    if the agent is unavailable.

    Includes an in-memory render cache that avoids repeated LLM calls
    for identical data payloads.
    """

    def __init__(self, model_id: str | None = None):
        """Initialize the Visualization Renderer agent.

        Args:
            model_id: Optional Bedrock model ID override for the Strands Agent.
        """
        from src.config import get_strands_bedrock_model
        from src.services.lru_cache import LRUCache

        agent_kwargs: dict[str, Any] = {
            "system_prompt": VISUALIZER_SYSTEM_PROMPT,
            "tools": [analyze_data_structure, generate_chart_spec, generate_visualization_description],
            "callback_handler": None,
            "model": get_strands_bedrock_model(model_id, max_tokens=500),
        }

        self._agent = Agent(**agent_kwargs)
        # Cache rendered outputs keyed by hash of (payload + query_type)
        self._render_cache: LRUCache[str, RenderedOutput] = LRUCache(max_size=200)

    def _compute_render_cache_key(self, payload: dict[str, Any], query_type: str) -> str:
        """Generate a deterministic cache key from payload data and query type.

        Args:
            payload: The data payload to render.
            query_type: The query type (lookup, aggregation, comparison).

        Returns:
            SHA-256 hex digest as cache key.
        """
        import hashlib
        # Deterministic serialization: sort keys, normalize
        key_data = json.dumps(payload, sort_keys=True, default=str) + "|" + query_type
        return hashlib.sha256(key_data.encode()).hexdigest()

    async def render(
        self, response: OrchestratorResponse, intent_metadata: dict | None = None
    ) -> RenderedOutput:
        """Render an orchestrator response into a visualization.

        Uses the Strands Agent to analyze data and select the best
        visualization. Falls back to rule-based rendering on failure.
        Results are cached so identical payloads return instantly on repeat.

        Args:
            response: The validated orchestrator response.
            intent_metadata: Optional metadata from the intent (query_id, query_type, etc).

        Returns:
            RenderedOutput with chart data or text content.
        """
        payload = self._extract_payload(response)
        metadata = self._build_metadata(response, intent_metadata)

        if not payload:
            return RenderedOutput(
                output_type="text",
                chart_type=None,
                chart_data=None,
                text_content="No data available to visualize.",
                description="Query returned no results.",
                metadata=metadata,
            )

        # Check if data is structured
        if not self._is_structured_data(payload):
            text_content = self._format_as_text(payload)
            return RenderedOutput(
                output_type="text",
                chart_type=None,
                chart_data=None,
                text_content=text_content,
                description="Query results displayed as text.",
                metadata=metadata,
            )

        # Check render cache before making expensive LLM call
        query_type = intent_metadata.get("query_type", "lookup") if intent_metadata else "lookup"
        query_text = intent_metadata.get("query_text", "") if intent_metadata else ""
        cache_key = self._compute_render_cache_key(payload, query_type + "|" + query_text)
        cached = self._render_cache.get(cache_key)
        if cached is not None:
            logger.info(json.dumps({
                "service_name": "visualization_renderer",
                "operation": "render",
                "event": "cache_hit",
                "cache_key": cache_key[:16],
            }))
            # Return cached result with updated metadata (new query_id, timestamp)
            return RenderedOutput(
                output_type=cached.output_type,
                chart_type=cached.chart_type,
                chart_data=cached.chart_data,
                text_content=cached.text_content,
                description=cached.description,
                metadata=metadata,
            )

        # Progressive response: compute stats immediately before LLM call
        stats_text = self._generate_stats_description(payload)

        # Use Strands Agent for dynamic visualization with rule-based fallback
        try:
            result = await self._agent_render(payload, intent_metadata, metadata, stats_text)
        except Exception as e:
            logger.warning(
                json.dumps({
                    "service_name": "visualization_renderer",
                    "operation": "render",
                    "event": "agent_fallback",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                })
            )
            requested_chart = intent_metadata.get("requested_chart_type") if intent_metadata else None
            result = self._fallback_render(payload, metadata, stats_text, requested_chart)

        # Cache the rendered output for future identical requests
        self._render_cache.put(cache_key, result)
        return result

    async def _agent_render(
        self,
        payload: dict[str, Any],
        intent_metadata: dict | None,
        metadata: dict,
        stats_text: str = "",
    ) -> RenderedOutput:
        """Use the Strands Agent to produce a visualization.

        Passes the user's original query, data summary, and any explicit
        chart type request to the agent for intelligent visualization.

        Args:
            payload: The data payload to visualize.
            intent_metadata: Query context including query_text and requested_chart_type.
            metadata: Output metadata.
            stats_text: Pre-computed statistical summary text.

        Returns:
            RenderedOutput from agent reasoning.
        """
        # Normalize payload to columns + rows for the agent
        columns, rows = self._normalize_payload(payload)
        query_type = intent_metadata.get("query_type", "lookup") if intent_metadata else "lookup"
        query_text = intent_metadata.get("query_text", "") if intent_metadata else ""
        requested_chart = intent_metadata.get("requested_chart_type") if intent_metadata else None
        row_count = payload.get("row_count", len(rows))

        if not columns or not rows:
            return self._fallback_render(payload, metadata)

        # Build a rich prompt with the actual user query and data context
        sample_rows = rows[:15]  # Give agent enough data to reason about
        data_type = payload.get("data_type", "unknown")

        prompt_parts = [
            f"User's original query: \"{query_text}\"" if query_text else "",
            f"Query classification: {query_type}",
            f"Data type: {data_type}",
            f"Total rows: {row_count}",
            f"Columns: {json.dumps(columns)}",
            f"Data (first {len(sample_rows)} rows): {json.dumps(sample_rows, default=str)}",
        ]

        if requested_chart:
            prompt_parts.append(
                f"\nIMPORTANT: The user explicitly requested a '{requested_chart}' chart. Use that type."
            )
        else:
            prompt_parts.append(
                "\nAnalyze this data and choose the visualization that best reveals "
                "patterns, correlations, or insights. Consider what story the data tells."
            )

        if stats_text:
            prompt_parts.append(f"\nPre-computed statistics:\n{stats_text}")

        prompt = "\n".join(p for p in prompt_parts if p)

        # Invoke agent
        result = self._agent(prompt)

        # Track cost
        from src.services.bedrock_wrapper import track_agent_invocation
        from src.config import DEFAULT_MODEL_ID
        track_agent_invocation(
            component="visualization_renderer",
            model_id=DEFAULT_MODEL_ID,
            response=result,
        )

        agent_text = str(result)

        # Parse the agent's JSON output
        chart_spec = self._extract_chart_from_agent(agent_text, columns, rows, payload, requested_chart)

        # Build description from agent insights + stats
        description = chart_spec.get("description", "Data visualization.")
        if stats_text and stats_text not in description:
            description = f"{description}\n\n{stats_text}"

        return RenderedOutput(
            output_type="chart" if chart_spec.get("chart_type") != "text" else "text",
            chart_type=chart_spec.get("chart_type"),
            chart_data=chart_spec.get("chart_data"),
            text_content=stats_text or None,
            description=description,
            metadata=metadata,
        )

    def _extract_chart_from_agent(
        self,
        agent_text: str,
        columns: list[str],
        rows: list[list],
        payload: dict[str, Any],
        requested_chart: str | None = None,
    ) -> dict[str, Any]:
        """Extract chart specification from agent output.

        Parses the JSON output from the visualization agent. The agent
        should return a JSON object with chart_type, chart_data, title,
        and description fields.

        Falls back to rule-based selection only if JSON parsing completely fails.

        Args:
            agent_text: The agent's text output.
            columns: Data columns.
            rows: Data rows.
            payload: Full payload.
            requested_chart: Explicitly requested chart type from user, if any.

        Returns:
            Dict with chart_type, chart_data, description.
        """
        # Try to extract JSON from agent output (may have surrounding text)
        spec = self._parse_json_from_text(agent_text)

        if spec:
            # Normalize field names (agent may use chart_type or type)
            chart_type = spec.get("chart_type") or spec.get("type")
            chart_data = spec.get("chart_data") or spec
            description = spec.get("description") or spec.get("title", "Data visualization.")
            title = spec.get("title", "")

            if chart_type and chart_type in ("bar", "line", "scatter", "pie", "table"):
                # If chart_data is the full spec itself, structure it properly
                if "chart_data" not in spec:
                    chart_data = {k: v for k, v in spec.items()
                                  if k not in ("chart_type", "description")}
                chart_data["type"] = chart_type
                if title:
                    chart_data["title"] = title

                return {
                    "chart_type": chart_type,
                    "chart_data": chart_data,
                    "description": description,
                }

        # If the user explicitly requested a chart type but agent failed to parse,
        # use rule-based with that type forced
        if requested_chart:
            result = self._rule_based_chart(columns, rows, payload)
            result["chart_type"] = requested_chart
            # Rebuild chart data for the requested type
            if requested_chart == "scatter":
                spec = _build_scatter_spec(columns, rows, {})
                spec["type"] = "scatter"
                result["chart_data"] = spec
            elif requested_chart == "line":
                spec = _build_line_spec(columns, rows, {})
                spec["type"] = "line"
                result["chart_data"] = spec
            elif requested_chart == "pie":
                spec = _build_pie_spec(columns, rows, {})
                spec["type"] = "pie"
                result["chart_data"] = spec
            return result

        # Full fallback to rule-based
        logger.warning(json.dumps({
            "service_name": "visualization_renderer",
            "operation": "_extract_chart_from_agent",
            "event": "json_parse_failed",
            "agent_text_preview": agent_text[:200],
        }))
        return self._rule_based_chart(columns, rows, payload)

    @staticmethod
    def _parse_json_from_text(text: str) -> dict[str, Any] | None:
        """Extract the first valid JSON object from text.

        Handles cases where the agent wraps JSON in markdown code blocks
        or adds surrounding text.

        Args:
            text: Raw text that may contain a JSON object.

        Returns:
            Parsed dict if found, None otherwise.
        """
        # Strip markdown code fences if present
        import re
        code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_block:
            try:
                return json.loads(code_block.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find the outermost JSON object
        start = text.find("{")
        if start < 0:
            return None

        # Find matching closing brace (handling nested objects)
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    # Try the next JSON object if this one is malformed
                    next_start = text.find("{", i + 1)
                    if next_start >= 0:
                        # Recurse on remainder
                        return VisualizationRenderer._parse_json_from_text(text[next_start:])
                    return None

        return None

    def _fallback_render(
        self, payload: dict[str, Any], metadata: dict, stats_text: str = "",
        requested_chart_type: str | None = None,
    ) -> RenderedOutput:
        """Rule-based fallback rendering that handles all payload formats.

        Converts aggregation/comparison payloads into chart-friendly
        columns+rows format before applying chart selection rules.
        If the user explicitly requested a chart type, forces that type.

        Args:
            payload: Data payload from the spoke agent.
            metadata: Output metadata.
            stats_text: Pre-computed statistical summary text.
            requested_chart_type: Explicitly requested chart type from user, if any.

        Returns:
            RenderedOutput with chart or text.
        """
        data_type = payload.get("data_type", "")
        
        # Convert payload to normalized columns + rows format
        columns, rows = self._normalize_payload(payload)
        
        if not columns and not rows:
            # Try to generate a text summary from aggregation data
            description = stats_text or self._generate_stats_description(payload)
            if description:
                return RenderedOutput(
                    output_type="text",
                    chart_type=None,
                    chart_data=None,
                    text_content=description,
                    description="Aggregated data summary.",
                    metadata=metadata,
                )
            return RenderedOutput(
                output_type="text",
                chart_type=None,
                chart_data=None,
                text_content="No data available to visualize.",
                description="Query returned no results.",
                metadata=metadata,
            )

        # If user explicitly requested a chart type, honor it
        if requested_chart_type and requested_chart_type in ("bar", "line", "scatter", "pie", "table"):
            chart_info = self._build_requested_chart(requested_chart_type, columns, rows, payload)
        else:
            chart_info = self._rule_based_chart(columns, rows, payload)
        
        # Use pre-computed stats or compute if not provided
        stats_desc = stats_text or self._generate_stats_description(payload)
        description = chart_info.get("description", "")
        if stats_desc:
            description = f"{description}\n\n{stats_desc}"

        return RenderedOutput(
            output_type="chart",
            chart_type=chart_info.get("chart_type", "table"),
            chart_data=chart_info.get("chart_data"),
            text_content=stats_desc,  # Always populated with stats
            description=description,
            metadata=metadata,
        )

    def _build_requested_chart(
        self, chart_type: str, columns: list[str], rows: list[list], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Build a chart spec for an explicitly user-requested chart type.

        Forces the requested chart type regardless of data shape, using
        the best available data mapping.

        Args:
            chart_type: The requested chart type.
            columns: Data columns.
            rows: Data rows.
            payload: Full payload for context.

        Returns:
            Dict with chart_type, chart_data, description.
        """
        if chart_type == "scatter":
            spec = _build_scatter_spec(columns, rows, {})
            spec["type"] = "scatter"
            return {
                "chart_type": "scatter",
                "chart_data": spec,
                "description": "Scatter plot as requested by user.",
            }
        elif chart_type == "line":
            spec = _build_line_spec(columns, rows, {})
            spec["type"] = "line"
            return {
                "chart_type": "line",
                "chart_data": spec,
                "description": "Line chart as requested by user.",
            }
        elif chart_type == "pie":
            spec = _build_pie_spec(columns, rows, {})
            spec["type"] = "pie"
            return {
                "chart_type": "pie",
                "chart_data": spec,
                "description": "Pie chart as requested by user.",
            }
        elif chart_type == "bar":
            spec = _build_bar_spec(columns, rows, {})
            spec["type"] = "bar"
            return {
                "chart_type": "bar",
                "chart_data": spec,
                "description": "Bar chart as requested by user.",
            }
        else:
            return {
                "chart_type": "table",
                "chart_data": {"type": "table", "columns": columns, "rows": rows[:100]},
                "description": "Data displayed as table.",
            }

    def _normalize_payload(self, payload: dict[str, Any]) -> tuple[list[str], list[list]]:
        """Normalize different payload formats into columns + rows.
        
        Handles:
        - Tabular: already has columns + rows
        - Aggregation: convert aggregations dict to rows
        - Comparison: convert groups dict to rows
        
        Returns:
            Tuple of (columns, rows as list of lists).
        """
        data_type = payload.get("data_type", "")
        
        # Already has rows
        if payload.get("rows") and payload.get("columns"):
            return payload["columns"], payload["rows"]
        
        # Aggregation format: {"aggregations": {"revenue": {"sum": X, "avg": Y, ...}}}
        if data_type == "aggregation" and "aggregations" in payload:
            aggs = payload["aggregations"]
            if not aggs:
                return [], []
            # Convert to table: metric | sum | avg | min | max | count
            columns = ["metric", "sum", "avg", "min", "max", "count"]
            rows = []
            for metric, values in aggs.items():
                rows.append([
                    metric,
                    values.get("sum", 0),
                    values.get("avg", 0),
                    values.get("min", 0),
                    values.get("max", 0),
                    values.get("count", 0),
                ])
            return columns, rows
        
        # Comparison format: {"groups": {"group1": {"count": N, "metric": {"sum": X}}}}
        if data_type == "comparison" and "groups" in payload:
            groups = payload["groups"]
            if not groups:
                return [], []
            group_col = payload.get("group_by", "group")
            # Get all numeric keys from first group
            sample = next(iter(groups.values()), {})
            numeric_keys = [k for k, v in sample.items() 
                          if isinstance(v, dict) and "sum" in v]
            
            columns = [group_col] + [f"{k}_sum" for k in numeric_keys] + ["count"]
            rows = []
            for group_name, group_data in groups.items():
                row = [group_name]
                for k in numeric_keys:
                    row.append(group_data.get(k, {}).get("sum", 0))
                row.append(group_data.get("count", 0))
                rows.append(row)
            return columns, rows
        
        # Multi-source comparison
        if "sources" in payload:
            # Merge data from all sources into a unified comparison
            all_columns = []
            all_rows = []
            for source in payload["sources"]:
                cols, rws = self._normalize_payload(source)
                if cols and rws:
                    if not all_columns:
                        all_columns = ["source"] + cols
                        for row in rws:
                            all_rows.append([source.get("data_source", "unknown")] + row)
                    else:
                        # Add rows with source label
                        for row in rws:
                            padded = [source.get("data_source", "unknown")]
                            # Align to all_columns
                            for col in all_columns[1:]:
                                if col in cols:
                                    idx = cols.index(col)
                                    padded.append(row[idx] if idx < len(row) else None)
                                else:
                                    padded.append(None)
                            all_rows.append(padded)
            if all_columns and all_rows:
                return all_columns, all_rows
            # If merging failed, use first source
            for source in payload["sources"]:
                cols, rws = self._normalize_payload(source)
                if cols and rws:
                    return cols, rws
        
        return [], []

    def _generate_stats_description(self, payload: dict[str, Any]) -> str:
        """Generate a statistical summary description from payload data.
        
        Args:
            payload: The data payload.
            
        Returns:
            A string with key statistics, or empty string.
        """
        data_type = payload.get("data_type", "")
        parts = []
        row_count = payload.get("row_count", 0)
        
        # Handle multi-source payloads
        if "sources" in payload:
            for source in payload["sources"]:
                source_name = source.get("data_source", "unknown")
                source_desc = self._generate_stats_description(source)
                if source_desc:
                    parts.append(f"[{source_name}]\n{source_desc}")
            return "\n\n".join(parts)
        
        if data_type == "aggregation" and "aggregations" in payload:
            parts.append(f"Aggregation across {row_count} records:")
            for metric, values in payload["aggregations"].items():
                parts.append(
                    f"  • {metric}: total={values.get('sum', 'N/A')}, "
                    f"avg={values.get('avg', 'N/A')}, "
                    f"range=[{values.get('min', 'N/A')} – {values.get('max', 'N/A')}], "
                    f"count={values.get('count', 'N/A')}"
                )
        elif data_type == "comparison" and "groups" in payload:
            groups = payload["groups"]
            parts.append(f"Comparison across {len(groups)} groups ({row_count} total records):")
            for group_name, group_data in groups.items():
                count = group_data.get("count", 0)
                numeric_summary = ", ".join(
                    f"{k}={v.get('sum', 'N/A')}"
                    for k, v in group_data.items()
                    if isinstance(v, dict) and "sum" in v
                )
                parts.append(f"  • {group_name} ({count} items): {numeric_summary}")
        elif data_type == "tabular":
            parts.append(f"Tabular data with {row_count} rows and {len(payload.get('columns', []))} columns.")
        
        return "\n".join(parts)

    def _rule_based_chart(
        self, columns: list[str], rows: list[list], payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Deterministic rule-based chart selection (fallback).

        Rules:
        - Comparison data type → bar (grouped)
        - Aggregation data type → bar
        - Time-series data → line
        - Single categorical + single numeric → bar
        - Two numeric columns → scatter
        - Single numeric with ≤8 categories → pie
        - Fallback → table
        """
        data_type = payload.get("data_type", "")
        
        if not columns or not rows:
            return {
                "chart_type": "table",
                "chart_data": {"type": "table", "columns": columns, "rows": rows},
                "description": "Data displayed as a table.",
            }

        # Detect column types
        has_time_col = any(
            any(p in col.lower() for p in DATE_PATTERNS) for col in columns
        )
        numeric_cols = [
            col for i, col in enumerate(columns)
            if rows and i < len(rows[0]) and isinstance(rows[0][i], (int, float))
            and not isinstance(rows[0][i], bool)
        ]
        categorical_cols = [c for c in columns if c not in numeric_cols]
        num_rows = len(rows)

        # Comparison queries: choose chart based on data shape
        if data_type == "comparison":
            group_col = payload.get("group_by", "")
            # Few groups with single numeric → pie for proportional view
            if num_rows <= 6 and len(numeric_cols) == 1:
                spec = _build_pie_spec(columns, rows, {})
                spec["type"] = "pie"
                return {
                    "chart_type": "pie",
                    "chart_data": spec,
                    "description": f"Proportional comparison across {num_rows} groups.",
                }
            # Time-based grouping → line chart
            if has_time_col or any(p in group_col.lower() for p in DATE_PATTERNS):
                spec = _build_line_spec(columns, rows, {})
                spec["type"] = "line"
                return {
                    "chart_type": "line",
                    "chart_data": spec,
                    "description": f"Comparison over time across {num_rows} periods.",
                }
            # Default comparison → bar
            spec = _build_bar_spec(columns, rows, {})
            spec["type"] = "bar"
            return {
                "chart_type": "bar",
                "chart_data": spec,
                "description": f"Comparison data displayed as a bar chart across {num_rows} groups.",
            }

        # Aggregation queries: summarize metrics
        if data_type == "aggregation":
            # Single metric → show as a simple stat/table rather than bar
            if num_rows == 1:
                return {
                    "chart_type": "table",
                    "chart_data": {"type": "table", "columns": columns, "rows": rows},
                    "description": "Aggregated metric summary.",
                }
            # Multiple metrics → horizontal bar
            spec = _build_bar_spec(columns, rows, {})
            spec["type"] = "bar"
            return {
                "chart_type": "bar",
                "chart_data": spec,
                "description": f"Aggregated data displayed as a bar chart with {num_rows} metrics.",
            }

        # Tabular/lookup data: apply smart rules
        if has_time_col and numeric_cols:
            chart_type = "line"
            spec = _build_line_spec(columns, rows, {})
        elif len(categorical_cols) >= 1 and len(numeric_cols) >= 1:
            # If few categories and one numeric → pie for proportional view
            if num_rows <= 8 and len(numeric_cols) == 1 and len(categorical_cols) == 1:
                chart_type = "pie"
                spec = _build_pie_spec(columns, rows, {})
            # If data has a time-like categorical (quarter names, months)
            elif self._looks_like_time_series(columns, rows, categorical_cols):
                chart_type = "line"
                spec = _build_line_spec(columns, rows, {})
            else:
                chart_type = "bar"
                spec = _build_bar_spec(columns, rows, {})
        elif len(numeric_cols) >= 2 and not categorical_cols:
            chart_type = "scatter"
            spec = _build_scatter_spec(columns, rows, {})
        else:
            chart_type = "table"
            spec = {"type": "table", "columns": columns, "rows": rows[:100]}

        spec["type"] = chart_type
        row_count = payload.get("row_count", len(rows))
        description = f"Data displayed as a {chart_type} with {len(columns)} columns and {row_count} rows."

        return {"chart_type": chart_type, "chart_data": spec, "description": description}

    @staticmethod
    def _looks_like_time_series(
        columns: list[str], rows: list[list], categorical_cols: list[str]
    ) -> bool:
        """Detect if categorical column values look like time periods.

        Checks for patterns like Q1, Q2, Q3, Q4, Jan, Feb, 2024-Q1, etc.

        Args:
            columns: All column names.
            rows: Data rows.
            categorical_cols: Identified categorical columns.

        Returns:
            True if the data looks like a time series.
        """
        import re

        time_patterns = [
            r"^Q[1-4]$",               # Q1, Q2, Q3, Q4
            r"^\d{4}[-\s]?Q[1-4]$",    # 2024-Q1, 2024 Q2
            r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)",  # Month names
            r"^\d{4}$",                 # Years: 2023, 2024
            r"^\d{4}[-/]\d{2}$",       # 2024-01, 2024/03
        ]

        if not categorical_cols or not rows:
            return False

        # Check first categorical column
        cat_col = categorical_cols[0]
        cat_idx = columns.index(cat_col) if cat_col in columns else None
        if cat_idx is None:
            return False

        values = [str(row[cat_idx]) for row in rows[:10] if cat_idx < len(row)]
        if not values:
            return False

        # If majority of values match time patterns, it's a time series
        matches = 0
        for val in values:
            for pattern in time_patterns:
                if re.match(pattern, val.strip(), re.IGNORECASE):
                    matches += 1
                    break

        return matches >= len(values) * 0.5

    def _extract_payload(self, response: OrchestratorResponse) -> dict[str, Any] | None:
        """Extract the first successful payload from agent results."""
        for result in response.results:
            if result.status == "success" and result.payload:
                return result.payload
        return None

    def _is_structured_data(self, payload: dict[str, Any]) -> bool:
        """Determine if payload contains structured data."""
        data_type = payload.get("data_type", "")
        if data_type in ("tabular", "aggregation", "comparison"):
            return True
        if "columns" in payload and ("rows" in payload or "aggregations" in payload):
            return True
        if "groups" in payload:
            return True
        return False

    def _format_as_text(self, payload: dict[str, Any]) -> str:
        """Format non-structured data as plain text."""
        if "content" in payload:
            return str(payload["content"])
        return json.dumps(payload, indent=2) if payload else "No data available."

    def _build_metadata(
        self,
        response: OrchestratorResponse,
        intent_metadata: dict | None,
    ) -> dict:
        """Build metadata dict for the rendered output."""
        data_sources = [r.data_source for r in response.results if r.status == "success"]
        metadata: dict[str, Any] = {
            "query_id": str(response.query_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_sources": data_sources,
        }
        if intent_metadata:
            metadata.update(intent_metadata)
        return metadata
