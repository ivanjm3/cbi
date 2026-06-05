# Bugfix Requirements Document

## Introduction

The visualization renderer (`src/services/visualization_renderer.py`) is overly constrained by a rigid, rule-based architecture that limits the LLM agent to only 5 hardcoded chart types (bar, line, scatter, pie, table). This prevents the system from leveraging the full Chart.js ecosystem (stacked bar, area, radar, doughnut, bubble, treemap, heatmap, etc.) and forces chart selection through deterministic fallback rules rather than letting the LLM freely choose the most insightful visualization.

The fix replaces the tool-per-chart-type architecture and rule-based fallback with a single flexible `emit_chart` tool that accepts any valid Chart.js configuration JSON, and updates the system prompt to encourage creative, unconstrained chart type selection.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the LLM agent selects a chart type THEN the system restricts it to only one of 5 hardcoded literal types ("bar", "line", "scatter", "pie", "table") via the `generate_chart_spec` tool's `chart_type` parameter and the `RenderedOutput.chart_type` field

1.2 WHEN the LLM agent fails to produce parseable output or selects a type outside the hardcoded 5 THEN the system falls back to rigid rule-based chart selection logic (`_rule_based_chart`) that deterministically picks from the same 5 types based on data shape heuristics

1.3 WHEN the LLM agent needs to generate a chart specification THEN the system forces it through per-chart-type builder functions (`_build_bar_spec`, `_build_line_spec`, `_build_scatter_spec`, `_build_pie_spec`) that produce fixed data mappings rather than allowing free-form Chart.js configuration

1.4 WHEN the system prompt instructs the agent on chart selection THEN it explicitly limits choices to "bar|line|scatter|pie|table" and provides rigid decision rules (e.g., "Category comparisons with ≤6 items → pie chart")

1.5 WHEN the frontend receives a chart type THEN it passes it directly to `new Chart(canvas, { type: chartType, ... })` but only expects the 5 hardcoded types, limiting rendering to those types

### Expected Behavior (Correct)

2.1 WHEN the LLM agent selects a chart type THEN the system SHALL accept any valid Chart.js chart type string (bar, line, scatter, pie, doughnut, radar, polarArea, bubble, etc.) without restriction via a single `emit_chart` tool that accepts a complete Chart.js configuration JSON

2.2 WHEN the LLM agent produces a chart specification THEN the system SHALL pass the full Chart.js configuration directly to the frontend without rule-based overrides or fallback chart selection logic

2.3 WHEN the LLM agent needs to generate a chart THEN the system SHALL provide a single `emit_chart` tool that accepts any valid Chart.js JSON configuration (type, data, options) rather than routing through per-chart-type builder functions

2.4 WHEN the system prompt instructs the agent on chart selection THEN it SHALL encourage creative use of the full Chart.js type ecosystem (stacked bar, area, radar, doughnut, bubble, treemap, heatmap, etc.) and not constrain choices to a fixed set

2.5 WHEN the frontend receives a chart configuration THEN it SHALL render any valid Chart.js chart type by passing the configuration directly to the Chart.js constructor, and the `RenderedOutput.chart_type` field SHALL accept any string (not a Literal)

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the renderer receives structured data (tabular, aggregation, comparison) THEN the system SHALL CONTINUE TO normalize payloads into columns + rows format for the LLM agent to reason about

3.2 WHEN the renderer encounters identical payload + query combinations THEN the system SHALL CONTINUE TO return cached results from the LRU render cache without making redundant LLM calls

3.3 WHEN the renderer receives a response with no data or unstructured data THEN the system SHALL CONTINUE TO return text-based output with appropriate descriptions

3.4 WHEN the renderer generates output THEN the system SHALL CONTINUE TO include statistical summaries, metadata (query_id, timestamp, data_sources), and BI insight descriptions

3.5 WHEN the visualization service receives a render request via POST /internal/render THEN the system SHALL CONTINUE TO accept the same `RenderRequest` schema (validated_response + structured_intent) and return a `RenderedOutput` response

3.6 WHEN the frontend renders table-type data THEN the system SHALL CONTINUE TO render tables using HTML table elements (not Chart.js canvas)
