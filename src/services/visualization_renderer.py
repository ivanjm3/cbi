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

VISUALIZER_SYSTEM_PROMPT = (
    "You are a chart generation agent. Analyze the data and produce a single JSON response:\n"
    '{"chart_type": "bar|line|scatter|pie|table", "chart_data": <Chart.js spec>, "description": "<insights>"}\n\n'
    "Rules:\n"
    "- Time series → line. Categories + numbers → bar. Two numerics → scatter. ≤8 categories proportional → pie. Otherwise → table.\n"
    "- Include tooltips, legend, responsive sizing in chart_data.\n"
    "- Add trend lines/averages as annotations where useful.\n"
    "- Description: explain key patterns, notable stats (highs, lows, averages).\n"
    "- Output ONLY the JSON object. No surrounding text."
)


class VisualizationRenderer:
    """Strands Agent-based visualization renderer.

    Uses LLM reasoning to analyze data and produce context-aware,
    dynamic chart specifications. Falls back to rule-based selection
    if the agent is unavailable.
    """

    def __init__(self, model_id: str | None = None):
        """Initialize the Visualization Renderer agent.

        Args:
            model_id: Optional Bedrock model ID override for the Strands Agent.
        """
        from src.config import get_strands_bedrock_model

        agent_kwargs: dict[str, Any] = {
            "system_prompt": VISUALIZER_SYSTEM_PROMPT,
            "tools": [analyze_data_structure, generate_chart_spec, generate_visualization_description],
            "callback_handler": None,
            "model": get_strands_bedrock_model(model_id),
            "model_kwargs": {"max_tokens": 500},
        }

        self._agent = Agent(**agent_kwargs)

    async def render(
        self, response: OrchestratorResponse, intent_metadata: dict | None = None
    ) -> RenderedOutput:
        """Render an orchestrator response into a visualization.

        Uses the Strands Agent to analyze data and select the best
        visualization. Falls back to rule-based rendering on failure.

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

        # Progressive response: compute stats immediately before LLM call
        stats_text = self._generate_stats_description(payload)

        # Use Strands Agent for dynamic visualization with rule-based fallback
        try:
            return await self._agent_render(payload, intent_metadata, metadata, stats_text)
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
            return self._fallback_render(payload, metadata, stats_text)

    async def _agent_render(
        self,
        payload: dict[str, Any],
        intent_metadata: dict | None,
        metadata: dict,
        stats_text: str = "",
    ) -> RenderedOutput:
        """Use the Strands Agent to produce a visualization.

        Args:
            payload: The data payload to visualize.
            intent_metadata: Query context.
            metadata: Output metadata.
            stats_text: Pre-computed statistical summary text.

        Returns:
            RenderedOutput from agent reasoning.
        """
        # Normalize payload to columns + rows for the agent
        columns, rows = self._normalize_payload(payload)
        query_type = intent_metadata.get("query_type", "lookup") if intent_metadata else "lookup"
        row_count = payload.get("row_count", len(rows))

        if not columns or not rows:
            # Can't visualize empty data — use stats description
            return self._fallback_render(payload, metadata)

        # Prepare context for the agent
        sample_rows = rows[:10]  # Limit to reduce tokens
        prompt = (
            f"Visualize this query result data.\n\n"
            f"Query type: {query_type}\n"
            f"Total rows: {row_count}\n"
            f"Columns: {json.dumps(columns)}\n"
            f"Sample data (first {len(sample_rows)} rows): {json.dumps(sample_rows, default=str)}\n\n"
            f"Analyze the data, select the best chart type, generate the chart spec, "
            f"and write a description with insights."
        )

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

        # Parse agent output — the agent should have called our tools
        # which produce deterministic chart specs. Extract the chart info.
        chart_spec = self._extract_chart_from_agent(agent_text, columns, rows, payload)

        # Use pre-computed stats for text_content (always populated)
        description = chart_spec.get("description", "Data visualization.")
        if stats_text:
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
    ) -> dict[str, Any]:
        """Extract chart specification from agent output.

        The agent calls tools that produce JSON specs. We parse those
        from the conversation or fall back to rule-based if parsing fails.

        Args:
            agent_text: The agent's text output.
            columns: Data columns.
            rows: Data rows.
            payload: Full payload.

        Returns:
            Dict with chart_type, chart_data, description, etc.
        """
        # Try to find JSON chart spec in agent output
        try:
            # Look for JSON blocks in the agent response
            start = agent_text.find("{")
            if start >= 0:
                # Find the matching closing brace
                depth = 0
                for i in range(start, len(agent_text)):
                    if agent_text[i] == "{":
                        depth += 1
                    elif agent_text[i] == "}":
                        depth -= 1
                    if depth == 0:
                        json_str = agent_text[start:i + 1]
                        spec = json.loads(json_str)
                        if "type" in spec:
                            return {
                                "chart_type": spec.get("type"),
                                "chart_data": spec,
                                "description": spec.get("title", "Data visualization."),
                            }
                        break
        except (json.JSONDecodeError, ValueError):
            pass

        # If we can't parse agent output, use the tool outputs directly
        # (the tools were called during agent execution and produced results)
        # Fall back to rule-based
        return self._rule_based_chart(columns, rows, payload)

    def _fallback_render(
        self, payload: dict[str, Any], metadata: dict, stats_text: str = ""
    ) -> RenderedOutput:
        """Rule-based fallback rendering that handles all payload formats.

        Converts aggregation/comparison payloads into chart-friendly
        columns+rows format before applying chart selection rules.

        Args:
            payload: Data payload from the spoke agent.
            metadata: Output metadata.
            stats_text: Pre-computed statistical summary text.

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

        # Comparison queries → bar chart
        if data_type == "comparison":
            spec = _build_bar_spec(columns, rows, {})
            spec["type"] = "bar"
            row_count = payload.get("row_count", len(rows))
            return {
                "chart_type": "bar",
                "chart_data": spec,
                "description": f"Comparison data displayed as a bar chart across {len(rows)} groups.",
            }

        # Aggregation queries → bar chart
        if data_type == "aggregation":
            spec = _build_bar_spec(columns, rows, {})
            spec["type"] = "bar"
            return {
                "chart_type": "bar",
                "chart_data": spec,
                "description": f"Aggregated data displayed as a bar chart with {len(rows)} metrics.",
            }

        has_time_col = any(
            any(p in col.lower() for p in DATE_PATTERNS) for col in columns
        )
        numeric_cols = [
            col for i, col in enumerate(columns)
            if rows and i < len(rows[0]) and isinstance(rows[0][i], (int, float))
            and not isinstance(rows[0][i], bool)
        ]
        categorical_cols = [c for c in columns if c not in numeric_cols]

        if has_time_col and numeric_cols:
            chart_type = "line"
            spec = _build_line_spec(columns, rows, {})
        elif len(categorical_cols) >= 1 and len(numeric_cols) >= 1:
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
