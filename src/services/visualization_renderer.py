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

# Module-level accumulator for emit_chart results.
# The @tool function stores its output here so the renderer can retrieve it
# reliably regardless of how the Strands SDK formats the final agent response.
_last_emit_chart_result: dict[str, Any] | None = None


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
    global _last_emit_chart_result

    try:
        config = json.loads(chart_config)
    except json.JSONDecodeError as exc:
        _last_emit_chart_result = None
        return json.dumps({"error": f"Invalid JSON: {exc}", "title": title, "description": description})
    if "type" not in config:
        _last_emit_chart_result = None
        return json.dumps({"error": "chart_config must contain a 'type' field", "title": title, "description": description})

    result = {"chart_config": config, "title": title, "description": description}
    _last_emit_chart_result = result
    return json.dumps(result)


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

    # Maximum retries before giving up on agent path
    MAX_AGENT_RETRIES = 3

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

        # AGENTIC-FIRST: The agent is the primary rendering path.
        # We retry up to MAX_AGENT_RETRIES times with error feedback before
        # raising an error. The deterministic fallback is commented out —
        # the agent MUST produce valid output or the request fails with a
        # clear error indicating what went wrong.
        result = await self._agent_render_with_retry(
            payload, query_text, query_type, requested_chart, metadata, stats_text
        )

        self._render_cache.put(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Agent render path — with retry and error feedback
    # ------------------------------------------------------------------

    async def _agent_render_with_retry(
        self,
        payload: dict[str, Any],
        query_text: str,
        query_type: str,
        requested_chart: str | None,
        metadata: dict,
        stats_text: str,
    ) -> RenderedOutput:
        """Agentic rendering with retry. No silent fallback.

        Tries up to MAX_AGENT_RETRIES attempts. On each failure, feeds the
        error back into the prompt so the agent can self-correct.
        If all attempts fail, raises with a clear error message.
        """
        columns, rows = self._normalize_payload(payload)
        if not columns or not rows:
            return RenderedOutput(
                output_type="text", chart_type=None, chart_data=None,
                text_content=stats_text or "No data to display.",
                description="Data summary.", metadata=metadata,
            )

        sample_rows = rows[:20]
        data_type = payload.get("data_type", "unknown")
        row_count = payload.get("row_count", len(rows))

        # Build chart type instruction — constraint at START and END of prompt
        if requested_chart:
            chart_prefix = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"MANDATORY CHART TYPE: {requested_chart.upper()}\n"
                f"The user EXPLICITLY requested a {requested_chart} chart.\n"
                f"You MUST set \"type\": \"{requested_chart}\" in chart_config.\n"
                f"Any other chart type is WRONG and will be REJECTED.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            )
            if requested_chart == "radar":
                chart_prefix += (
                    "\nRADAR CHART DATA FORMAT:\n"
                    "- \"type\": \"radar\" (MANDATORY — NOT bar, NOT line)\n"
                    "- \"data.labels\": entity names array\n"
                    "- \"data.datasets\": one dataset PER METRIC with normalized 0-100 values\n"
                    "  Example: {\"label\": \"Revenue\", \"data\": [100, 62.2, 21.1]}\n"
                    "- \"options.scales.r\": {\"beginAtZero\": true, \"min\": 0, \"max\": 100}\n"
                    "- Normalize: (value / max_in_metric) * 100\n\n"
                )
            elif requested_chart == "scatter":
                chart_prefix += "\nSCATTER: data as [{x,y},...], NO labels array.\n\n"
            elif requested_chart == "bubble":
                chart_prefix += "\nBUBBLE: data as [{x,y,r},...], r in 5-30px range.\n\n"
            elif requested_chart in ("pie", "doughnut"):
                chart_prefix += f"\n{requested_chart.upper()}: labels array + single dataset.\n\n"

            chart_suffix = (
                f"\n\n⚠️ FINAL CHECK: \"type\" MUST be \"{requested_chart}\". "
                f"NOT bar. NOT line. ONLY \"{requested_chart}\". "
                f"If you use any other type, your response is INVALID."
            )
        else:
            suggested = _guess_chart_type(columns, rows, payload)
            chart_prefix = ""
            chart_suffix = (
                f"\nChart type hint (you may override): '{suggested}'. "
                f"Apply the decision tree. Pick the MOST EXPRESSIVE chart. "
                f"Bar is last resort."
            )

        base_prompt_parts = [
            chart_prefix,
            f'User query: "{query_text}"' if query_text else "",
            f"Query type: {query_type} | Data type: {data_type} | Rows: {row_count}",
            f"Columns: {json.dumps(columns)}",
            f"Data ({len(sample_rows)} rows): {json.dumps(sample_rows, default=str)}",
            chart_suffix,
            "\nCall emit_chart now with a complete, beautiful Chart.js config.",
        ]
        base_prompt = "\n".join(p for p in base_prompt_parts if p)

        global _last_emit_chart_result
        last_error = ""
        for attempt in range(self.MAX_AGENT_RETRIES):
            try:
                # Reset the module-level accumulator before each attempt
                _last_emit_chart_result = None
                # On retry, append the error feedback so the agent can self-correct
                if attempt > 0 and last_error:
                    prompt = (
                        f"{base_prompt}\n\n"
                        f"⚠️ RETRY (attempt {attempt + 1}/{self.MAX_AGENT_RETRIES}): "
                        f"Your previous response was invalid. Error: {last_error}\n"
                        f"You MUST call emit_chart with valid JSON. Try again."
                    )
                else:
                    prompt = base_prompt

                agent_result = self._agent(prompt)

                agent_text = str(agent_result)
                chart_spec = self._extract_emit_chart_from_result(agent_result, agent_text)

                if chart_spec and "chart_config" in chart_spec:
                    config = chart_spec["chart_config"]
                    # Validate the config has required structure
                    validation_error = self._validate_chart_config(config)
                    if validation_error:
                        last_error = validation_error
                        logger.warning(json.dumps({
                            "event": "agent_chart_validation_failed",
                            "attempt": attempt + 1,
                            "error": validation_error,
                        }))
                        continue  # Retry with feedback

                    # Validate chart type matches user request
                    if requested_chart and config.get("type") != requested_chart:
                        wrong_type = config.get("type", "unknown")
                        logger.warning(json.dumps({
                            "event": "agent_wrong_chart_type_correcting",
                            "attempt": attempt + 1,
                            "expected": requested_chart,
                            "got": wrong_type,
                        }))
                        # Agent did the hard work (data, styling, description).
                        # Correct the type and restructure data to match.
                        config = self._transform_chart_type(config, requested_chart)


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
                else:
                    last_error = "emit_chart tool was not called or returned invalid JSON structure"
                    logger.warning(json.dumps({
                        "event": "emit_chart_not_found",
                        "attempt": attempt + 1,
                    }))

            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(json.dumps({
                    "event": "agent_render_exception",
                    "attempt": attempt + 1,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }))

        # All retry attempts exhausted — agent failed to produce valid output.
        # FALLBACK COMMENTED OUT: uncomment below if you want deterministic fallback.
        # return self._deterministic_render(payload, requested_chart, metadata, stats_text)

        # Instead, return an error-state RenderedOutput so the frontend knows
        # the agent failed and can display an appropriate message.
        logger.error(json.dumps({
            "event": "agent_render_all_retries_exhausted",
            "attempts": self.MAX_AGENT_RETRIES,
            "last_error": last_error,
        }))
        return RenderedOutput(
            output_type="text",
            chart_type=None,
            chart_data=None,
            text_content=(
                f"Visualization generation failed after {self.MAX_AGENT_RETRIES} attempts. "
                f"Last error: {last_error}\n\n"
                f"Data summary:\n{stats_text}"
            ),
            description=f"Agent rendering failed: {last_error}",
            metadata=metadata,
        )

    @staticmethod
    def _validate_chart_config(config: dict) -> str | None:
        """Validate a Chart.js config has the minimum required structure.

        Returns None if valid, or an error string describing what's wrong.
        """
        if not isinstance(config, dict):
            return "chart_config must be a JSON object"
        if "type" not in config:
            return "chart_config missing required 'type' field"
        if "data" not in config:
            return "chart_config missing required 'data' field"
        data = config["data"]
        if not isinstance(data, dict):
            return "'data' must be an object"
        # Scatter/bubble don't need labels
        if config["type"] not in ("scatter", "bubble"):
            if "labels" not in data and "datasets" not in data:
                return "'data' must contain 'labels' and/or 'datasets'"
        if "datasets" not in data:
            return "'data' must contain 'datasets' array"
        if not isinstance(data["datasets"], list) or len(data["datasets"]) == 0:
            return "'datasets' must be a non-empty array"
        return None

    @staticmethod
    def _transform_chart_type(config: dict, target_type: str) -> dict:
        """Transform a chart config from its current type to the target type.

        The agent already structured the data intelligently — we just need
        to change the type and reformat data where the structure differs.
        This is NOT a fallback: the agent did the analytical work, we're
        correcting a single field the LLM stubbornly got wrong.

        Args:
            config: The agent-produced Chart.js config (wrong type).
            target_type: The user-requested chart type to transform to.

        Returns:
            Transformed config with correct type and compatible data structure.
        """
        import copy
        result = copy.deepcopy(config)
        source_type = result.get("type", "bar")
        result["type"] = target_type

        data = result.get("data", {})
        datasets = data.get("datasets", [])
        labels = data.get("labels", [])
        options = result.get("options", {})

        if target_type == "radar":
            # Radar needs: labels (entities), datasets (one per metric, normalized 0-100)
            # If coming from bar: labels are categories, datasets have metric values
            # Normalize each dataset to 0-100 scale
            for ds in datasets:
                values = ds.get("data", [])
                if values and all(isinstance(v, (int, float)) for v in values):
                    max_val = max(values) if max(values) > 0 else 1
                    ds["data"] = [round((v / max_val) * 100, 1) for v in values]
                # Add radar-specific styling
                ds.setdefault("fill", True)
                ds.setdefault("tension", 0)
                if "backgroundColor" in ds:
                    # Make fill semi-transparent for radar
                    bg = ds["backgroundColor"]
                    if isinstance(bg, str) and "0.82" in bg:
                        ds["backgroundColor"] = bg.replace("0.82", "0.25")
                ds.setdefault("pointRadius", 4)
                ds.setdefault("pointHoverRadius", 7)
                ds.setdefault("borderWidth", 2)

            # Set radar scales
            options.setdefault("scales", {})
            options["scales"]["r"] = {
                "beginAtZero": True,
                "min": 0,
                "max": 100,
                "ticks": {"stepSize": 20},
            }
            # Remove x/y scales that don't apply to radar
            options["scales"].pop("x", None)
            options["scales"].pop("y", None)

        elif target_type == "scatter":
            # Scatter needs data as [{x, y}, ...] — no labels
            if labels and datasets:
                for ds in datasets:
                    values = ds.get("data", [])
                    if values and not isinstance(values[0], dict):
                        # Convert parallel arrays to point objects
                        if len(datasets) >= 2:
                            x_data = datasets[0].get("data", [])
                            y_data = datasets[1].get("data", [])
                            ds["data"] = [
                                {"x": x_data[i] if i < len(x_data) else 0,
                                 "y": y_data[i] if i < len(y_data) else 0}
                                for i in range(min(len(x_data), len(y_data)))
                            ]
                            break
                data.pop("labels", None)
                ds.setdefault("pointRadius", 7)
                ds.setdefault("pointHoverRadius", 11)

        elif target_type in ("pie", "doughnut"):
            # Pie/doughnut: single dataset with values, labels for categories
            if len(datasets) > 1:
                # Merge multiple datasets into one (use first dataset values)
                pass  # Keep first dataset, it's usually fine
            if target_type == "doughnut":
                options["cutout"] = "72%"
            for ds in datasets:
                ds.setdefault("hoverOffset", 10)
                ds.setdefault("borderWidth", 3)
                ds.setdefault("borderColor", "#fff")
            # Remove axes
            options.pop("scales", None)

        elif target_type == "polarArea":
            result["type"] = "polarArea"
            options.pop("scales", None)
            for ds in datasets:
                ds.setdefault("borderWidth", 2)

        elif target_type == "line":
            for ds in datasets:
                ds.setdefault("tension", 0.4)
                ds.setdefault("fill", False)
                ds.setdefault("pointRadius", 4)
                ds.setdefault("borderWidth", 2.5)

        elif target_type == "bubble":
            # Bubble needs {x, y, r} — normalize r to 5-30
            pass  # Complex transform, leave data as-is if agent structured it

        result["data"] = data
        result["options"] = options
        return result

    # ------------------------------------------------------------------
    # Deterministic fallback — COMMENTED OUT for agentic-first approach.
    # The agent MUST produce valid output via retry. Uncomment this and
    # the line in _agent_render_with_retry if you need silent fallback.
    # ------------------------------------------------------------------
    #
    # def _deterministic_render(
    #     self,
    #     payload: dict[str, Any],
    #     requested_chart: str | None,
    #     metadata: dict,
    #     stats_text: str = "",
    # ) -> RenderedOutput:
    #     columns, rows = self._normalize_payload(payload)
    #     if not columns or not rows:
    #         return RenderedOutput(
    #             output_type="text", chart_type=None, chart_data=None,
    #             text_content=stats_text or "No data to display.",
    #             description="Data summary.", metadata=metadata,
    #         )
    #     chart_type = requested_chart or _guess_chart_type(columns, rows, payload)
    #     if chart_type == "table":
    #         return RenderedOutput(
    #             output_type="chart", chart_type="table",
    #             chart_data={"type": "table", "columns": columns, "rows": rows[:200]},
    #             text_content=stats_text, description=stats_text or "Data displayed as a table.",
    #             metadata=metadata,
    #         )
    #     title = self._derive_title(columns, chart_type)
    #     config = _build_fallback_chart(columns, rows, chart_type, title, stats_text)
    #     if not config:
    #         return RenderedOutput(
    #             output_type="chart", chart_type="table",
    #             chart_data={"type": "table", "columns": columns, "rows": rows[:200]},
    #             text_content=stats_text, description=stats_text or "Data displayed as a table.",
    #             metadata=metadata,
    #         )
    #     description = f"{title} — {stats_text}" if stats_text else title
    #     return RenderedOutput(
    #         output_type="chart", chart_type=chart_type, chart_data=config,
    #         text_content=stats_text or None, description=description, metadata=metadata,
    #     )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_title(columns: list[str], chart_type: str) -> str:
        if len(columns) >= 2:
            return f"{columns[1]} by {columns[0]}"
        return chart_type.capitalize() + " Chart"

    @staticmethod
    def _extract_emit_chart_from_result(agent_result: Any, agent_text: str) -> dict[str, Any] | None:
        """Extract emit_chart result using multiple strategies.

        Strategy 1: Module-level accumulator (most reliable — the @tool function
                    stores its output in _last_emit_chart_result).
        Strategy 2: Parse JSON from agent text output (fallback for edge cases).
        Strategy 3: Inspect agent_result.message for toolUse content blocks.

        Args:
            agent_result: The Strands AgentResult object.
            agent_text: String representation of the agent result.

        Returns:
            Dict with chart_config, title, description if found, else None.
        """
        global _last_emit_chart_result

        # Strategy 1: Module-level accumulator (set by emit_chart @tool)
        if _last_emit_chart_result is not None:
            result = _last_emit_chart_result
            _last_emit_chart_result = None  # Reset for next call
            if "chart_config" in result and "error" not in result:
                return result

        # Strategy 2: Parse from agent text (catches cases where tool result
        # is echoed in the final response text)
        text_result = VisualizationRenderer._extract_emit_chart(agent_text)
        if text_result:
            return text_result

        # Strategy 3: Inspect message content blocks for tool results
        try:
            if hasattr(agent_result, "message") and agent_result.message:
                message = agent_result.message
                content = message.get("content", []) if isinstance(message, dict) else []
                for block in content:
                    if isinstance(block, dict):
                        # Look for toolResult blocks
                        tool_result = block.get("toolResult", {})
                        if tool_result:
                            tr_content = tool_result.get("content", [])
                            for tr_block in tr_content:
                                if isinstance(tr_block, dict) and "text" in tr_block:
                                    try:
                                        parsed = json.loads(tr_block["text"])
                                        if isinstance(parsed, dict) and "chart_config" in parsed:
                                            return parsed
                                    except (json.JSONDecodeError, TypeError):
                                        pass
        except Exception:
            pass  # Don't fail on message inspection

        return None

    @staticmethod
    def _extract_emit_chart(agent_text: str) -> dict[str, Any] | None:
        """Find the emit_chart result JSON in agent output text."""
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
