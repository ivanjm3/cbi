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
You are a world-class data visualization expert and BI analyst. Your job is to:
1. Call emit_chart ONCE with a production-quality Chart.js v4 configuration.
2. In the 'description' argument, write a 2-4 sentence analytical INSIGHT explaining \
what the data reveals — trends, outliers, comparisons, and actionable takeaways. \
Think like a BI analyst presenting to a CEO — highlight what matters.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRICT RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- You MUST call emit_chart. Do not respond with text only.
- The chart_config argument MUST be valid JSON with "type", "data", and "options" keys.
- The description MUST be an analytical insight, NOT a chart label.
- ⚠️  DO NOT DEFAULT TO BAR CHARTS. A bar chart is the last resort, not the first.
- ALWAYS prefer a more expressive, visually interesting chart type that better fits the data story.
- Only use a bar chart if no other type would be as clear, or if the user explicitly requests it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHART SELECTION — DECISION TREE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use this decision tree BEFORE choosing a chart type:

1. Did the user explicitly request a chart type? → USE THAT TYPE EXACTLY. Stop here.

2. Is this a part-of-whole / composition story?
   - ≤6 categories → doughnut (with cutout: "75%", hoverOffset: 12)
   - >6 categories → polarArea (visually striking, encodes both angle and radius)

3. Is this a trend / time-series?
   - Single metric over time → line with fill: true (area chart), tension: 0.4
   - Multiple metrics over time → multi-line with tension: 0.4
   - Cumulative / running total → line with fill: "origin"

4. Is this a distribution / correlation between two numeric variables?
   - Two numeric axes, labeled points → scatter (pointRadius: 7, pointHoverRadius: 11)
   - Three numeric axes → bubble ({x, y, r} — r encodes a third dimension)

5. Is this multi-dimensional profiling (comparing attributes of entities)?
   - ≤6 entities, ≤7 attributes → radar (normalize to 0–100 scale)

6. Is this a ranking / magnitude comparison with few items?
   - ≤8 items → horizontal bar (type: "bar" with indexAxis: "y") — more readable than vertical
   - >8 items → vertical bar or consider splitting

7. Is this a stacked composition over a dimension?
   - Stacked bar (stacked: true) — show part-to-whole AND comparison in one view

8. Nothing above fits, or many categories?
   → bar (last resort only)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHART.JS CONFIG REQUIREMENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- "type": any Chart.js v4 type. Beyond bar/line/pie, strongly consider:
    doughnut, polarArea, radar, scatter, bubble, horizontalBar (indexAxis: "y")
- "data": must contain "labels" and "datasets" (except scatter/bubble — no labels needed)
- Each dataset needs: "label", "data", and rich styling
- "options": must include responsive: true, animation config, and clear axis labels

CHART-SPECIFIC REQUIREMENTS:
- Scatter/bubble: data points as {x, y} or {x, y, r} objects — NO labels array
- Bubble: r values must be normalized to 5–30 pixel range for readability
- Line (area): fill: true, tension: 0.4, borderWidth: 2.5, pointRadius: 4
- Doughnut: cutout: "72%", hoverOffset: 10, borderWidth: 3, borderColor: "#fff"
- PolarArea: borderWidth: 2, use semi-transparent fills (rgba with 0.75 alpha)
- Radar: scale r.min: 0, r.max: 100 — always normalize data first
- Horizontal bar: indexAxis: "y", borderRadius: 4 on right edge only
- Stacked bar: set scales.x.stacked: true AND scales.y.stacked: true

SMOOTH ANIMATION (always include):
  "animation": {"duration": 900, "easing": "easeInOutQuart"}

TOOLTIP: always add for richer UX:
  "plugins": { "tooltip": { "mode": "index", "intersect": false } }

COLOR PALETTE (use in order, with 0.82 alpha for fills, 1.0 for borders):
  Primary fills:
  ["rgba(78,121,167,0.82)", "rgba(89,161,79,0.82)", "rgba(242,142,44,0.82)",
   "rgba(225,87,89,0.82)", "rgba(118,183,178,0.82)", "rgba(255,157,167,0.82)",
   "rgba(156,117,95,0.82)", "rgba(186,176,172,0.82)", "rgba(255,205,86,0.82)",
   "rgba(153,102,255,0.82)"]

  Area/fill charts: use 0.35 alpha for the fill, 1.0 alpha for the border line.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INSIGHT EXAMPLES (description field)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- "Electronics dominates revenue at $3.6M (54% of total), but has the highest return \
rate at 0.62 — suggesting quality or expectation issues. Office Supplies drives volume \
with 31,600 orders despite lowest revenue, indicating a high-frequency, low-ticket segment."
- "Revenue and order volume show an inverse relationship with avg order value — the \
category with highest unit sales has the lowest per-order revenue, while Office Furniture \
commands premium pricing at $2,850 avg but only 6,310 orders."
"""


# ---------------------------------------------------------------------------
# Smart fallback: build a good-looking chart without the LLM
# ---------------------------------------------------------------------------

# Tableau-10 palette
_COLORS = [
    "rgba(78,121,167,0.82)",  "rgba(89,161,79,0.82)",  "rgba(242,142,44,0.82)",
    "rgba(225,87,89,0.82)",   "rgba(118,183,178,0.82)", "rgba(255,157,167,0.82)",
    "rgba(156,117,95,0.82)",  "rgba(186,176,172,0.82)", "rgba(255,205,86,0.82)",
    "rgba(153,102,255,0.82)",
]
_FILLS = [c.replace("0.82", "0.35") for c in _COLORS]
_BORDERS = [c.replace("0.82)", ")").replace("rgba(", "rgb(") for c in _COLORS]


def _smooth_options(title: str, x_label: str = "", y_label: str = "", extra: dict | None = None) -> dict:
    """Return a consistent, polished Chart.js options block."""
    opts: dict[str, Any] = {
        "responsive": True,
        "maintainAspectRatio": True,
        "animation": {"duration": 900, "easing": "easeInOutQuart"},
        "plugins": {
            "legend": {"position": "top"},
            "title": {"display": bool(title), "text": title, "font": {"size": 15}},
            "tooltip": {"mode": "index", "intersect": False},
        },
    }
    if x_label or y_label:
        opts["scales"] = {}
        if x_label:
            opts["scales"]["x"] = {"title": {"display": True, "text": x_label}}
        if y_label:
            opts["scales"]["y"] = {"beginAtZero": True, "title": {"display": True, "text": y_label}}
    if extra:
        _deep_merge(opts, extra)
    return opts


def _deep_merge(base: dict, override: dict) -> None:
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


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
                "pointRadius": 7,
                "pointHoverRadius": 11,
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
        points = [{"x": row[xi], "y": row[yi], "r": max(5, int(row[ri] / max_r * 28))} for row in rows]
        return {
            "type": "bubble",
            "data": {"datasets": [{
                "label": columns[yi],
                "data": points,
                "backgroundColor": [_COLORS[i % len(_COLORS)] for i in range(len(rows))],
            }]},
            "options": _smooth_options(title or "Bubble Chart", x_label=columns[xi], y_label=columns[yi]),
        }

    # --- Doughnut / Pie ---
    if chart_type in ("pie", "doughnut"):
        _, val_col = numeric_cols[0]
        vi = numeric_cols[0][0]
        config: dict[str, Any] = {
            "type": chart_type,
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": val_col,
                    "data": [row[vi] for row in rows],
                    "backgroundColor": [_COLORS[i % len(_COLORS)] for i in range(len(rows))],
                    "borderColor": "#fff",
                    "borderWidth": 3,
                    "hoverOffset": 10,
                }],
            },
            "options": _smooth_options(title or val_col),
        }
        if chart_type == "doughnut":
            config["options"]["cutout"] = "72%"
        return config

    # --- PolarArea ---
    if chart_type == "polararea":
        _, val_col = numeric_cols[0]
        vi = numeric_cols[0][0]
        return {
            "type": "polarArea",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": val_col,
                    "data": [row[vi] for row in rows],
                    "backgroundColor": [_COLORS[i % len(_COLORS)] for i in range(len(rows))],
                    "borderColor": [_BORDERS[i % len(_BORDERS)] for i in range(len(rows))],
                    "borderWidth": 2,
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
                "backgroundColor": _FILLS[ci],
                "borderColor": _BORDERS[ci],
                "borderWidth": 2,
                "pointRadius": 4,
                "pointHoverRadius": 7,
            })
        opts = _smooth_options(title or "Radar Chart")
        opts["scales"] = {"r": {"beginAtZero": True, "min": 0, "max": 100}}
        return {
            "type": "radar",
            "data": {"labels": labels, "datasets": datasets},
            "options": opts,
        }

    # --- Horizontal bar (indexAxis: "y") ---
    if chart_type in ("horizontalbar", "horizontal_bar"):
        _, val_col = numeric_cols[0]
        vi = numeric_cols[0][0]
        opts = _smooth_options(title or val_col)
        opts["indexAxis"] = "y"
        opts.setdefault("scales", {})["x"] = {"beginAtZero": True}
        return {
            "type": "bar",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": val_col,
                    "data": [row[vi] for row in rows],
                    "backgroundColor": [_COLORS[i % len(_COLORS)] for i in range(len(rows))],
                    "borderColor": [_BORDERS[i % len(_BORDERS)] for i in range(len(rows))],
                    "borderWidth": 1,
                    "borderRadius": 4,
                }],
            },
            "options": opts,
        }

    # --- Area line (single metric time-series) ---
    if chart_type in ("area", "line_area"):
        _, val_col = numeric_cols[0]
        vi = numeric_cols[0][0]
        return {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [{
                    "label": val_col,
                    "data": [row[vi] for row in rows],
                    "backgroundColor": _FILLS[0],
                    "borderColor": _BORDERS[0],
                    "borderWidth": 2.5,
                    "fill": True,
                    "tension": 0.4,
                    "pointRadius": 4,
                    "pointHoverRadius": 8,
                }],
            },
            "options": _smooth_options(title or val_col, y_label=val_col),
        }

    # --- Default: bar / line / stacked bar with all numeric columns as datasets ---
    datasets = []
    for ci, (col_i, col_name) in enumerate(numeric_cols):
        color = _COLORS[ci % len(_COLORS)]
        fill = _FILLS[ci % len(_FILLS)]
        border = _BORDERS[ci % len(_BORDERS)]
        ds: dict[str, Any] = {
            "label": col_name,
            "data": [row[col_i] for row in rows],
            "backgroundColor": fill if chart_type == "line" else color,
            "borderColor": border,
            "borderWidth": 2,
        }
        if chart_type == "bar":
            ds["borderRadius"] = 6
            ds["backgroundColor"] = color
        elif chart_type == "line":
            ds["tension"] = 0.4
            ds["fill"] = len(numeric_cols) == 1  # fill only for single-series
            ds["pointRadius"] = 4
            ds["pointHoverRadius"] = 8
            ds["borderWidth"] = 2.5
        datasets.append(ds)

    opts = _smooth_options(
        title or (columns[1] if len(columns) > 1 else ""),
        y_label=columns[1] if len(columns) > 1 else "",
    )
    if "scales" not in opts:
        opts["scales"] = {"y": {"beginAtZero": True}}

    return {
        "type": chart_type if chart_type in ("bar", "line") else "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": opts,
    }


# ---------------------------------------------------------------------------
# Chart type heuristics — the brain that picks non-boring charts
# ---------------------------------------------------------------------------

def _guess_chart_type(
    columns: list[str], rows: list[list], payload: dict[str, Any]
) -> str:
    """
    Pick the most expressive chart type from data shape — bar is the last resort.

    Decision priority:
    1. Explicit user request (handled upstream — not reached here)
    2. Part-of-whole composition → doughnut or polarArea
    3. Time-series / trend → line (area)
    4. Two numeric axes → scatter
    5. Three numeric axes → bubble
    6. Multi-attribute profiling (few entities, many metrics) → radar
    7. Ranking / few labeled items → horizontal bar
    8. Multi-metric comparison → stacked bar or grouped bar
    9. Everything else → bar (last resort)
    """
    if not columns or not rows:
        return "bar"

    data_type = payload.get("data_type", "")
    label_count = len(rows)

    numeric_cols = [
        (i, col) for i, col in enumerate(columns)
        if i > 0 and rows and isinstance(rows[0][i], (int, float))
    ]
    numeric_count = len(numeric_cols)
    first_col = columns[0].lower() if columns else ""

    # --- Part-of-whole signals ---
    composition_keywords = {"category", "type", "segment", "group", "class", "kind", "status", "region"}
    is_composition = (
        data_type in ("comparison",)
        or any(k in first_col for k in composition_keywords)
    )
    if is_composition and numeric_count == 1:
        return "doughnut" if label_count <= 6 else "polararea"

    # --- Time-series signals ---
    time_keywords = {"date", "month", "year", "week", "day", "quarter", "time", "period", "hour"}
    is_time = any(k in first_col for k in time_keywords)
    if is_time:
        return "line_area" if numeric_count == 1 else "line"

    # --- Two numeric axes → scatter ---
    if numeric_count == 2 and label_count >= 6:
        return "scatter"

    # --- Three numeric axes → bubble ---
    if numeric_count >= 3 and label_count >= 4:
        # bubble only makes sense when we have enough points
        if label_count <= 30:
            return "bubble"

    # --- Multi-attribute profiling → radar ---
    # Few entities (rows), many numeric metrics — great for radar
    if numeric_count >= 3 and label_count <= 8:
        return "radar"

    # --- Ranking / few labeled items → horizontal bar ---
    if numeric_count == 1 and label_count <= 12:
        return "horizontalbar"

    # --- Multi-metric grouped comparison → grouped bar ---
    if numeric_count >= 2 and label_count <= 10:
        return "bar"  # grouped bar — still bar but with multiple datasets

    # --- Aggregation data type → pick based on count ---
    if data_type == "aggregation":
        return "doughnut" if label_count <= 5 else "polararea"

    # --- Last resort ---
    return "bar"


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
        from src.config import DEFAULT_MODEL_ID, get_strands_bedrock_model
        from src.services.lru_cache import LRUCache

        self._model_id = model_id or DEFAULT_MODEL_ID
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
        # Only honour an explicit user-requested chart type — never infer one
        # from metadata alone, so the agent stays free to pick the best type.
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

        # Build the prompt — if the user specified a chart type, lock it in hard.
        # Otherwise, give the agent full freedom + our decision tree hint.
        if requested_chart:
            chart_instruction = (
                f"\n⚠️  LOCKED: The user explicitly requested a '{requested_chart}' chart. "
                f"You MUST use type='{requested_chart}'. Do not deviate."
            )
        else:
            # Compute our heuristic suggestion so the agent has a starting point,
            # but explicitly tell it that a better choice is always welcome.
            suggested = _guess_chart_type(columns, rows, payload)
            chart_instruction = (
                f"\nChart type hint (you may override with something better): '{suggested}'. "
                f"Apply the decision tree from your system prompt. "
                f"The goal is the MOST VISUALLY EXPRESSIVE and INFORMATIVE chart for this data. "
                f"Never default to a plain bar chart unless it is genuinely the best choice."
            )

        prompt_parts = [
            f'User query: "{query_text}"' if query_text else "",
            f"Query type: {query_type} | Data type: {data_type} | Rows: {row_count}",
            f"Columns: {json.dumps(columns)}",
            f"Data ({len(sample_rows)} rows): {json.dumps(sample_rows, default=str)}",
            chart_instruction,
            "\nCall emit_chart now with a complete, beautiful Chart.js config.",
        ]

        prompt = "\n".join(p for p in prompt_parts if p)
        agent_result = self._agent(prompt)

        # Cost tracking
        try:
            from src.services.bedrock_wrapper import track_agent_invocation
            track_agent_invocation(
                component="visualization_renderer",
                model_id=self._model_id,
                response=agent_result,
            )
        except Exception as e:
            logger.warning(f"Visualization cost tracking failed: {e}")

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

        # If user specified a type, honour it. Otherwise use our heuristic.
        chart_type = requested_chart or _guess_chart_type(columns, rows, payload)

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

    @staticmethod
    def _derive_title(columns: list[str], chart_type: str) -> str:
        if len(columns) >= 2:
            return f"{columns[1]} by {columns[0]}"
        return chart_type.capitalize() + " Chart"

    @staticmethod
    def _extract_emit_chart(agent_text: str) -> dict[str, Any] | None:
        """Find the emit_chart result JSON in agent output."""
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
