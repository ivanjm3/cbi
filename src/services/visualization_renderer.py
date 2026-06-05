"""Visualization Renderer — Strands Agent with dynamic chart generation.

Transforms validated agent responses into dynamic, context-aware visualizations
using LLM reasoning to select chart types and build complete Chart.js configs.

The Renderer feeds pre-normalized data directly to a focused agent prompt,
skipping the analyze_data_structure round-trip. The agent's sole job is to
call emit_chart with a complete, production-quality Chart.js configuration.

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7
"""

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from strands import Agent, tool

from src.models.shared import OrchestratorResponse, RenderedOutput

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strands tools
# ---------------------------------------------------------------------------

@tool
def emit_chart(chart_config: str, title: str, description: str) -> str:
    """Emit a complete Chart.js chart configuration for rendering.

    Call this ONCE with a complete, production-quality Chart.js config.
    The config must be valid JSON and must contain a 'type' field.

    Args:
        chart_config: Complete Chart.js JSON string — must include 'type',
            'data' (with 'labels' and 'datasets'), and 'options'.
            Use animation, tension, fill, borderWidth, pointRadius etc.
            to make charts smooth and visually rich.
        title: A concise, descriptive title for the chart.
        description: 2-3 sentence BI insight explaining what the data shows.

    Returns:
        JSON with chart_config, title, description.
    """
    try:
        config = json.loads(chart_config)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON: {exc}", "title": title, "description": description})

    if "type" not in config:
        return json.dumps({"error": "chart_config must contain a 'type' field", "title": title, "description": description})

    return json.dumps({"chart_config": config, "title": title, "description": description})


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

VISUALIZER_SYSTEM_PROMPT = """\
You are a data visualization expert. Your ONLY job is to call emit_chart ONCE with a \
complete, production-quality Chart.js v4 configuration.

STRICT RULES:
- You MUST call emit_chart. Do not respond with text only.
- The chart_config argument MUST be valid JSON with "type", "data", and "options" keys.
- Choose the chart type that BEST fits the data and the user's request.
- Make visualizations smooth, animated, and visually compelling.

CHART.JS CONFIG REQUIREMENTS:
- "type": any Chart.js type — bar, line, scatter, pie, doughnut, radar, polarArea, bubble, and not at all limited to listed types. Infact the more unique the better.
- "data": must contain "labels" (array) and "datasets" (array of dataset objects)
- Each dataset needs: "label", "data", and styling (backgroundColor, borderColor, etc.)
- "options": must include responsive:true, animation config, and clear axis labels

CHART TYPE GUIDANCE:
- Scatter/bubble: data points as {x, y} or {x, y, r} objects — NO labels array needed
- Line: use tension:0.4 for smooth curves, fill:true for area charts
- Bar: use borderRadius:6 for modern look; stack for multi-series comparisons
- Doughnut/pie: use hoverOffset:8 and rich color arrays
- Radar: normalize data to 0-100 scale for readability
- Similarly apply such constraints on decided charts

SMOOTH ANIMATION (always include):
  "animation": {"duration": 800, "easing": "easeInOutQuart"}

EXAMPLE for comparison data — grouped bar:
{
  "type": "bar",
  "data": {
    "labels": ["Electronics", "Office Furniture", "Office Supplies"],
    "datasets": [{
      "label": "Revenue",
      "data": [3616000, 2249000, 764000],
      "backgroundColor": ["rgba(78,121,167,0.8)","rgba(89,161,79,0.8)","rgba(242,142,44,0.8)"],
      "borderColor": ["#4e79a7","#59a14f","#f28e2c"],
      "borderWidth": 2,
      "borderRadius": 6
    }]
  },
  "options": {
    "responsive": true,
    "animation": {"duration": 800, "easing": "easeInOutQuart"},
    "plugins": {"legend": {"position": "top"}, "title": {"display": true, "text": "Revenue by Category"}},
    "scales": {"y": {"beginAtZero": true, "title": {"display": true, "text": "Revenue ($)"}}}
  }
}
"""


# ---------------------------------------------------------------------------
# Smart fallback: build a good-looking chart without the LLM
# ---------------------------------------------------------------------------

# Tableau-10 palette
_COLORS = [
    "rgba(78,121,167,0.82)", "rgba(89,161,79,0.82)", "rgba(242,142,44,0.82)",
    "rgba(225,87,89,0.82)",  "rgba(118,183,178,0.82)", "rgba(255,157,167,0.82)",
    "rgba(156,117,95,0.82)", "rgba(186,176,172,0.82)", "rgba(255,205,86,0.82)",
    "rgba(153,102,255,0.82)",
]
_BORDERS = [c.replace("0.82", "1").replace("rgba", "rgb").replace(",1)", ")") for c in _COLORS]


def _smooth_options(title: str, x_label: str = "", y_label: str = "") -> dict:
    """Return a consistent, polished Chart.js options block."""
    opts: dict[str, Any] = {
        "responsive": True,
        "maintainAspectRatio": True,
        "animation": {"duration": 800, "easing": "easeInOutQuart"},
        "plugins": {
            "legend": {"position": "top"},
            "title": {"display": bool(title), "text": title, "font": {"size": 15}},
        },
    }
    if x_label or y_label:
        opts["scales"] = {}
        if x_label:
            opts["scales"]["x"] = {"title": {"display": True, "text": x_label}}
        if y_label:
            opts["scales"]["y"] = {"beginAtZero": True, "title": {"display": True, "text": y_label}}
    return opts


def _build_fallback_chart(
    columns: list[str],
    rows: list[list],
    requested_type: str | None,
    title: str = "",
    stats_text: str = "",
) -> dict[str, Any]:
    """Build a polished Chart.js config from normalized columns + rows without LLM."""
    if not columns or not rows:
        return {}

    chart_type = (requested_type or "bar").lower()
    labels = [str(row[0]) for row in rows]

    # Find numeric columns (skip the first/label column)
    numeric_cols = [
        (i, col) for i, col in enumerate(columns)
        if i > 0 and rows and isinstance(rows[0][i], (int, float))
    ]

    if not numeric_cols:
        return {}

    # --- Scatter: use two numeric columns as x/y ---
    if chart_type == "scatter":
        x_idx, x_col = numeric_cols[0]
        y_idx, y_col = numeric_cols[1] if len(numeric_cols) > 1 else numeric_cols[0]
        points = [{"x": row[x_idx], "y": row[y_idx]} for row in rows]
        return {
            "type": "scatter",
            "data": {"datasets": [{
                "label": f"{y_col} vs {x_col}",
                "data": points,
                "backgroundColor": _COLORS[0],
                "borderColor": _BORDERS[0],
                "pointRadius": 6,
                "pointHoverRadius": 9,
            }]},
            "options": _smooth_options(
                title or f"{y_col} vs {x_col}",
                x_label=x_col, y_label=y_col,
            ),
        }

    # --- Bubble: three numeric columns as x, y, r ---
    if chart_type == "bubble" and len(numeric_cols) >= 3:
        xi, _ = numeric_cols[0]
        yi, _ = numeric_cols[1]
        ri, _ = numeric_cols[2]
        max_r = max(row[ri] for row in rows) or 1
        points = [{"x": row[xi], "y": row[yi], "r": max(4, int(row[ri] / max_r * 30))} for row in rows]
        return {
            "type": "bubble",
            "data": {"datasets": [{
                "label": columns[yi],
                "data": points,
                "backgroundColor": [_COLORS[i % len(_COLORS)] for i in range(len(rows))],
            }]},
            "options": _smooth_options(title or "Bubble Chart", x_label=columns[xi], y_label=columns[yi]),
        }

    # --- Pie / Doughnut: one numeric column as slices ---
    if chart_type in ("pie", "doughnut"):
        _, val_col = numeric_cols[0]
        vi = numeric_cols[0][0]
        return {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": val_col,
                    "data": [row[vi] for row in rows],
                    "backgroundColor": [_COLORS[i % len(_COLORS)] for i in range(len(rows))],
                    "borderColor": "#fff",
                    "borderWidth": 2,
                    "hoverOffset": 8,
                }],
            },
            "options": _smooth_options(title or val_col),
        }

    # --- Radar: normalize each numeric column to 0-100 scale ---
    if chart_type == "radar":
        datasets = []
        for ci, (col_i, col_name) in enumerate(numeric_cols[:4]):
            values = [row[col_i] for row in rows]
            max_v = max(values) if values and max(values) else 1
            datasets.append({
                "label": col_name,
                "data": [round(v / max_v * 100, 1) for v in values],
                "backgroundColor": _COLORS[ci].replace("0.82", "0.2"),
                "borderColor": _BORDERS[ci],
                "borderWidth": 2,
                "pointRadius": 4,
            })
        return {
            "type": "radar",
            "data": {"labels": labels, "datasets": datasets},
            "options": _smooth_options(title or "Radar Chart"),
        }

    # --- Default: bar / line / stacked bar with all numeric columns as datasets ---
    datasets = []
    for ci, (col_i, col_name) in enumerate(numeric_cols):
        color = _COLORS[ci % len(_COLORS)]
        border = _BORDERS[ci % len(_BORDERS)]
        ds: dict[str, Any] = {
            "label": col_name,
            "data": [row[col_i] for row in rows],
            "backgroundColor": color,
            "borderColor": border,
            "borderWidth": 2,
        }
        if chart_type == "bar":
            ds["borderRadius"] = 6
        elif chart_type == "line":
            ds["tension"] = 0.4
            ds["fill"] = False
            ds["pointRadius"] = 5
            ds["pointHoverRadius"] = 8

        datasets.append(ds)

    opts = _smooth_options(title or columns[1] if len(columns) > 1 else "", y_label=columns[1] if len(columns) > 1 else "")
    if "scales" not in opts:
        opts["scales"] = {"y": {"beginAtZero": True}}

    return {
        "type": chart_type,
        "data": {"labels": labels, "datasets": datasets},
        "options": opts,
    }


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class VisualizationRenderer:
    """Strands Agent-based visualization renderer.

    The agent is prompted with pre-normalized tabular data and asked to
    produce a single emit_chart call. A deterministic fallback builds a
    good-looking chart from the same data if the agent fails or is unavailable.
    """

    def __init__(self, model_id: str | None = None):
        from src.config import get_strands_bedrock_model
        from src.services.lru_cache import LRUCache

        self._agent = Agent(
            system_prompt=VISUALIZER_SYSTEM_PROMPT,
            tools=[emit_chart],
            callback_handler=None,
            model=get_strands_bedrock_model(model_id, max_tokens=2000),
        )
        self._render_cache: LRUCache[str, RenderedOutput] = LRUCache(max_size=200)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def render(
        self, response: OrchestratorResponse, intent_metadata: dict | None = None
    ) -> RenderedOutput:
        payload = self._extract_payload(response)
        metadata = self._build_metadata(response, intent_metadata)

        if not payload:
            return RenderedOutput(
                output_type="text", chart_type=None, chart_data=None,
                text_content="No data available to visualize.",
                description="Query returned no results.", metadata=metadata,
            )

        if not self._is_structured_data(payload):
            return RenderedOutput(
                output_type="text", chart_type=None, chart_data=None,
                text_content=self._format_as_text(payload),
                description="Query results displayed as text.", metadata=metadata,
            )

        query_type = (intent_metadata or {}).get("query_type", "lookup")
        query_text = (intent_metadata or {}).get("query_text", "")
        requested_chart = (intent_metadata or {}).get("requested_chart_type")

        cache_key = self._cache_key(payload, query_type + "|" + query_text)
        cached = self._render_cache.get(cache_key)
        if cached is not None:
            logger.info(json.dumps({"event": "render_cache_hit", "key": cache_key[:16]}))
            return RenderedOutput(
                output_type=cached.output_type, chart_type=cached.chart_type,
                chart_data=cached.chart_data, text_content=cached.text_content,
                description=cached.description, metadata=metadata,
            )

        stats_text = self._generate_stats_description(payload)

        try:
            result = await self._agent_render(
                payload, query_text, query_type, requested_chart, metadata, stats_text
            )
        except Exception as exc:
            logger.warning(json.dumps({
                "event": "agent_render_failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }))
            result = self._deterministic_render(
                payload, requested_chart, metadata, stats_text
            )

        self._render_cache.put(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Agent render path
    # ------------------------------------------------------------------

    async def _agent_render(
        self,
        payload: dict[str, Any],
        query_text: str,
        query_type: str,
        requested_chart: str | None,
        metadata: dict,
        stats_text: str,
    ) -> RenderedOutput:
        columns, rows = self._normalize_payload(payload)
        if not columns or not rows:
            return self._deterministic_render(payload, requested_chart, metadata, stats_text)

        sample_rows = rows[:20]
        data_type = payload.get("data_type", "unknown")
        row_count = payload.get("row_count", len(rows))

        prompt_parts = [
            f'User query: "{query_text}"' if query_text else "",
            f"Query type: {query_type} | Data type: {data_type} | Rows: {row_count}",
            f"Columns: {json.dumps(columns)}",
            f"Data ({len(sample_rows)} rows): {json.dumps(sample_rows, default=str)}",
        ]
        if requested_chart:
            prompt_parts.append(
                f"\n>>> The user EXPLICITLY requested a '{requested_chart}' chart. "
                f"You MUST use type='{requested_chart}'."
            )
        prompt_parts.append(
            "\nCall emit_chart now with a complete, beautiful Chart.js config."
        )

        prompt = "\n".join(p for p in prompt_parts if p)

        agent_result = self._agent(prompt)

        # Cost tracking
        try:
            from src.services.bedrock_wrapper import track_agent_invocation
            from src.config import DEFAULT_MODEL_ID
            track_agent_invocation(
                component="visualization_renderer",
                model_id=DEFAULT_MODEL_ID,
                response=agent_result,
            )
        except Exception:
            pass

        agent_text = str(agent_result)
        chart_spec = self._extract_emit_chart(agent_text)

        if chart_spec and "chart_config" in chart_spec:
            config = chart_spec["chart_config"]
            chart_type = config.get("type")
            description_text = chart_spec.get("description", "")
            if stats_text and stats_text not in description_text:
                description_text = f"{description_text}\n\n{stats_text}"
            return RenderedOutput(
                output_type="chart",
                chart_type=chart_type,
                chart_data=config,
                text_content=stats_text or None,
                description=description_text or stats_text,
                metadata=metadata,
            )

        # Agent didn't produce a valid emit_chart — fall back deterministically
        logger.warning(json.dumps({"event": "emit_chart_not_found_in_agent_response"}))
        return self._deterministic_render(payload, requested_chart, metadata, stats_text)

    # ------------------------------------------------------------------
    # Deterministic fallback
    # ------------------------------------------------------------------

    def _deterministic_render(
        self,
        payload: dict[str, Any],
        requested_chart: str | None,
        metadata: dict,
        stats_text: str = "",
    ) -> RenderedOutput:
        columns, rows = self._normalize_payload(payload)

        if not columns or not rows:
            return RenderedOutput(
                output_type="text", chart_type=None, chart_data=None,
                text_content=stats_text or "No data to display.",
                description="Data summary.", metadata=metadata,
            )

        # Pick a sensible default chart type from the data shape
        chart_type = requested_chart or self._guess_chart_type(columns, rows, payload)

        if chart_type == "table":
            return RenderedOutput(
                output_type="chart", chart_type="table",
                chart_data={"type": "table", "columns": columns, "rows": rows[:200]},
                text_content=stats_text,
                description=stats_text or "Data displayed as a table.",
                metadata=metadata,
            )

        title = self._derive_title(columns, chart_type)
        config = _build_fallback_chart(columns, rows, chart_type, title, stats_text)

        if not config:
            # last resort: table
            return RenderedOutput(
                output_type="chart", chart_type="table",
                chart_data={"type": "table", "columns": columns, "rows": rows[:200]},
                text_content=stats_text,
                description=stats_text or "Data displayed as a table.",
                metadata=metadata,
            )

        description = f"{title} — {stats_text}" if stats_text else title
        return RenderedOutput(
            output_type="chart",
            chart_type=chart_type,
            chart_data=config,
            text_content=stats_text or None,
            description=description,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _guess_chart_type(
        self, columns: list[str], rows: list[list], payload: dict[str, Any]
    ) -> str:
        """Pick a reasonable chart type from data shape without an LLM."""
        data_type = payload.get("data_type", "")
        numeric_count = sum(
            1 for i in range(1, len(columns))
            if rows and isinstance(rows[0][i], (int, float))
        )
        label_count = len(rows)

        if numeric_count >= 2:
            return "bar"  # multi-metric comparison
        if data_type == "comparison" and label_count <= 6:
            return "doughnut"
        if data_type == "comparison":
            return "bar"
        if data_type == "aggregation":
            return "bar"
        return "bar"

    @staticmethod
    def _derive_title(columns: list[str], chart_type: str) -> str:
        if len(columns) >= 2:
            return f"{columns[1]} by {columns[0]}"
        return chart_type.capitalize() + " Chart"

    @staticmethod
    def _extract_emit_chart(agent_text: str) -> dict[str, Any] | None:
        """Find the emit_chart result JSON in agent output.

        The Strands agent appends tool results to the response text.
        We search for any JSON object containing 'chart_config'.
        """
        # Try all JSON objects in the text
        pos = 0
        while True:
            start = agent_text.find("{", pos)
            if start < 0:
                break
            depth = 0
            for i in range(start, len(agent_text)):
                if agent_text[i] == "{":
                    depth += 1
                elif agent_text[i] == "}":
                    depth -= 1
                if depth == 0:
                    candidate = agent_text[start:i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if isinstance(parsed, dict) and "chart_config" in parsed:
                            return parsed
                    except json.JSONDecodeError:
                        pass
                    pos = i + 1
                    break
            else:
                break
        return None

    def _cache_key(self, payload: dict[str, Any], suffix: str) -> str:
        key_data = json.dumps(payload, sort_keys=True, default=str) + "|" + suffix
        return hashlib.sha256(key_data.encode()).hexdigest()

    def _normalize_payload(self, payload: dict[str, Any]) -> tuple[list[str], list[list]]:
        data_type = payload.get("data_type", "")

        if payload.get("rows") and payload.get("columns"):
            return payload["columns"], payload["rows"]

        if data_type == "aggregation" and "aggregations" in payload:
            aggs = payload["aggregations"]
            if not aggs:
                return [], []
            columns = ["metric", "sum", "avg", "min", "max", "count"]
            rows = [
                [m, v.get("sum", 0), v.get("avg", 0), v.get("min", 0),
                 v.get("max", 0), v.get("count", 0)]
                for m, v in aggs.items()
            ]
            return columns, rows

        if data_type == "comparison" and "groups" in payload:
            groups = payload["groups"]
            if not groups:
                return [], []
            group_col = payload.get("group_by", "group")
            sample = next(iter(groups.values()), {})
            numeric_keys = [k for k, v in sample.items() if isinstance(v, dict) and "sum" in v]
            columns = [group_col] + [f"{k}_sum" for k in numeric_keys] + ["count"]
            rows = []
            for name, data in groups.items():
                row = [name] + [data.get(k, {}).get("sum", 0) for k in numeric_keys]
                row.append(data.get("count", 0))
                rows.append(row)
            return columns, rows

        if "sources" in payload:
            all_columns: list[str] = []
            all_rows: list[list] = []
            for source in payload["sources"]:
                cols, rws = self._normalize_payload(source)
                if not cols or not rws:
                    continue
                source_label = source.get("data_source", "unknown")
                if not all_columns:
                    all_columns = ["source"] + cols
                    for row in rws:
                        all_rows.append([source_label] + row)
                else:
                    for row in rws:
                        padded = [source_label]
                        for col in all_columns[1:]:
                            if col in cols:
                                idx = cols.index(col)
                                padded.append(row[idx] if idx < len(row) else None)
                            else:
                                padded.append(None)
                        all_rows.append(padded)
            if all_columns and all_rows:
                return all_columns, all_rows
            for source in payload["sources"]:
                cols, rws = self._normalize_payload(source)
                if cols and rws:
                    return cols, rws

        return [], []

    def _generate_stats_description(self, payload: dict[str, Any]) -> str:
        data_type = payload.get("data_type", "")
        parts: list[str] = []
        row_count = payload.get("row_count", 0)

        if "sources" in payload:
            for source in payload["sources"]:
                name = source.get("data_source", "unknown")
                desc = self._generate_stats_description(source)
                if desc:
                    parts.append(f"[{name}]\n{desc}")
            return "\n\n".join(parts)

        if data_type == "aggregation" and "aggregations" in payload:
            parts.append(f"Aggregation across {row_count} records:")
            for metric, values in payload["aggregations"].items():
                parts.append(
                    f"  • {metric}: total={values.get('sum', 'N/A')}, "
                    f"avg={values.get('avg', 'N/A')}, "
                    f"range=[{values.get('min', 'N/A')} – {values.get('max', 'N/A')}]"
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
            parts.append(
                f"Tabular data with {row_count} rows and {len(payload.get('columns', []))} columns."
            )

        return "\n".join(parts)

    def _extract_payload(self, response: OrchestratorResponse) -> dict[str, Any] | None:
        for result in response.results:
            if result.status == "success" and result.payload:
                return result.payload
        return None

    def _is_structured_data(self, payload: dict[str, Any]) -> bool:
        data_type = payload.get("data_type", "")
        if data_type in ("tabular", "aggregation", "comparison"):
            return True
        if "columns" in payload and ("rows" in payload or "aggregations" in payload):
            return True
        if "groups" in payload or "sources" in payload:
            return True
        return False

    def _format_as_text(self, payload: dict[str, Any]) -> str:
        if "content" in payload:
            return str(payload["content"])
        return json.dumps(payload, indent=2) if payload else "No data available."

    def _build_metadata(
        self, response: OrchestratorResponse, intent_metadata: dict | None
    ) -> dict:
        data_sources = [r.data_source for r in response.results if r.status == "success"]
        metadata: dict[str, Any] = {
            "query_id": str(response.query_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_sources": data_sources,
        }
        if intent_metadata:
            metadata.update(intent_metadata)
        return metadata
