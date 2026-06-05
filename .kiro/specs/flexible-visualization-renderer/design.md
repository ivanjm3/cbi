# Flexible Visualization Renderer Bugfix Design

## Overview

The visualization renderer is architecturally constrained by a rigid, rule-based design that limits chart output to 5 hardcoded types (bar, line, scatter, pie, table). This prevents the LLM agent from leveraging the full Chart.js ecosystem. The fix replaces the tool-per-chart-type architecture and deterministic fallback logic with a single `emit_chart` tool that accepts any valid Chart.js JSON configuration, enabling the agent to produce any chart type (radar, doughnut, bubble, polarArea, stacked bar, area, treemap, etc.) without code changes.

The fix is minimal and targeted: it removes the builder functions and rule-based selection, replaces the `generate_chart_spec` tool with `emit_chart`, updates the system prompt to encourage full Chart.js usage, widens `RenderedOutput.chart_type` from a `Literal` to `str`, and updates the frontend to pass arbitrary configs to Chart.js.

## Glossary

- **Bug_Condition (C)**: The condition where the LLM agent attempts to use a chart type outside the hardcoded 5 (bar, line, scatter, pie, table) or where the system overrides the agent's choice via rule-based fallback logic
- **Property (P)**: The desired behavior — the system accepts any valid Chart.js chart type string and passes the full configuration to the frontend without rule-based overrides
- **Preservation**: LRU caching, payload normalization, stats generation, metadata, the API contract (POST /internal/render with RenderRequest → RenderedOutput), and table rendering via HTML must remain unchanged
- **`emit_chart` tool**: The new single Strands `@tool` that accepts a complete Chart.js configuration JSON (type, data, options) and returns it for rendering
- **`generate_chart_spec` tool**: The existing tool that restricts chart_type to 5 literals and routes through per-type builder functions (to be removed)
- **`_rule_based_chart`**: The deterministic fallback method that selects chart type based on data shape heuristics (to be removed)
- **Builder functions**: `_build_bar_spec`, `_build_line_spec`, `_build_scatter_spec`, `_build_pie_spec` — per-chart-type data mapping functions (to be removed)

## Bug Details

### Bug Condition

The bug manifests when the LLM agent needs to produce a visualization beyond the 5 hardcoded types, or when it produces valid Chart.js output that gets rejected/overridden by the rule-based fallback. The `generate_chart_spec` tool restricts `chart_type` to a string literal, the `_extract_chart_from_agent` method validates against a hardcoded set, and `RenderedOutput.chart_type` is typed as `Literal["bar", "line", "scatter", "pie", "table"]`.

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type {agent_output: ChartSpec, system_config: RendererConfig}
  OUTPUT: boolean

  RETURN (input.agent_output.chart_type NOT IN ['bar', 'line', 'scatter', 'pie', 'table']
          AND input.agent_output IS valid Chart.js configuration)
         OR (input.system_config.fallback_overrides_agent_choice == true
             AND input.agent_output IS valid Chart.js configuration)
         OR (input.system_config.tool_restricts_type_to_literals == true)
END FUNCTION
```

### Examples

- **Radar chart blocked**: Agent wants to show multi-dimensional comparison as a radar chart → `generate_chart_spec` rejects "radar" as invalid `chart_type` → falls back to bar chart
- **Doughnut chart blocked**: Agent determines proportional data is best shown as doughnut → system forces pie because doughnut is not in the literal set
- **Stacked bar chart blocked**: Agent wants stacked bar for multi-series comparison → even though Chart.js supports stacked bars via options, the builder functions don't support stacking configuration
- **Bubble chart blocked**: Agent identifies 3-variable data perfect for bubble chart → system can't represent it, falls back to scatter (losing the third dimension)
- **Valid agent output overridden**: Agent produces perfect Chart.js JSON with type "polarArea" → `_extract_chart_from_agent` fails the `chart_type in ("bar", "line", "scatter", "pie", "table")` check → falls through to `_rule_based_chart` which picks "bar"

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- LRU render cache must continue to cache rendered outputs keyed by hash of (payload + query_type + query_text), avoiding redundant LLM calls for identical requests
- Payload normalization (`_normalize_payload`) must continue to convert aggregation/comparison/tabular/multi-source payloads into columns + rows format for the LLM agent
- Statistical summary generation (`_generate_stats_description`) must continue to produce human-readable stats for all payload types
- Metadata construction (`_build_metadata`) must continue to include query_id, timestamp, data_sources
- The API contract: POST /internal/render accepts `RenderRequest` (validated_response + structured_intent) and returns `RenderedOutput`
- Table rendering on the frontend must continue to use HTML table elements (not Chart.js canvas)
- Text/no-data responses must continue to work unchanged
- The `analyze_data_structure` tool must remain available for the agent to reason about data shape
- `generate_visualization_description` tool must remain available

**Scope:**
All inputs that do NOT involve chart type selection or chart spec generation should be completely unaffected by this fix. This includes:
- Cache hit/miss logic
- Payload extraction from OrchestratorResponse
- Structured vs unstructured data detection
- Text-only output paths
- Metadata and stats generation
- The RenderRequest/RenderedOutput schema structure (only the `chart_type` field type widens)

## Hypothesized Root Cause

Based on the bug description, the root causes are:

1. **Hardcoded Literal type in `RenderedOutput.chart_type`**: The Pydantic model uses `Literal["bar", "line", "scatter", "pie", "table"]` which rejects any other string at validation time. This is in `src/models/shared.py`.

2. **`generate_chart_spec` tool restricts input**: The tool's `chart_type` parameter is documented as `One of "bar", "line", "scatter", "pie", "table"` and the implementation routes through per-type builder functions that only handle those 5 types.

3. **`_extract_chart_from_agent` validates against hardcoded set**: Line `if chart_type and chart_type in ("bar", "line", "scatter", "pie", "table")` explicitly rejects any other type and falls through to rule-based fallback.

4. **`_rule_based_chart` deterministically overrides agent decisions**: When the agent's output doesn't match the expected format or contains an unsupported type, the system falls back to deterministic rules that can only produce the same 5 types.

5. **System prompt limits choices**: `VISUALIZER_SYSTEM_PROMPT` explicitly instructs `"chart_type": "bar|line|scatter|pie|table"` and provides rigid decision rules.

6. **Frontend builds config from parts**: The `renderChart` function constructs a Chart.js config by extracting `labels` and `datasets` separately, rather than passing a complete configuration object. This works for simple types but doesn't support the full range of Chart.js options.

## Correctness Properties

Property 1: Bug Condition - Any Valid Chart.js Type Accepted

_For any_ chart configuration where the chart type is a valid Chart.js type string (bar, line, scatter, pie, doughnut, radar, polarArea, bubble, etc.) and the configuration contains valid data and options, the fixed `emit_chart` tool SHALL accept the configuration and the system SHALL pass it through to `RenderedOutput` without rejection or rule-based override.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Caching, Stats, Normalization, and API Contract

_For any_ input that exercises the LRU caching path, payload normalization, stats generation, metadata construction, or the API endpoint contract, the fixed code SHALL produce the same result as the original code, preserving all existing functionality for these non-chart-selection concerns.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `src/models/shared.py`

**Change**: Widen `RenderedOutput.chart_type` type

**Specific Changes**:
1. **Change `chart_type` field type**: Replace `Literal["bar", "line", "scatter", "pie", "table"] | None` with `str | None` to accept any Chart.js chart type string.

---

**File**: `src/services/visualization_renderer.py`

**Function**: Multiple — remove tools and methods, add `emit_chart`

**Specific Changes**:
1. **Remove `generate_chart_spec` tool**: Delete the entire `@tool` function and its restrictive `chart_type` parameter.

2. **Remove per-chart-type builder functions**: Delete `_build_line_spec`, `_build_bar_spec`, `_build_scatter_spec`, `_build_pie_spec`.

3. **Remove `_rule_based_chart` method**: Delete the deterministic fallback chart selection logic entirely.

4. **Remove `_build_requested_chart` method**: No longer needed without per-type builders.

5. **Remove `_extract_chart_from_agent` method**: Replace with simpler JSON parsing that accepts any valid Chart.js config without type validation against a hardcoded set.

6. **Remove `_looks_like_time_series` method**: Only used by `_rule_based_chart`.

7. **Add `emit_chart` tool**: A single `@tool` function that accepts a complete Chart.js JSON configuration (type, data, options) plus title and description. Returns the config as-is for the renderer to include in `RenderedOutput`.

8. **Update `VISUALIZER_SYSTEM_PROMPT`**: Replace the rigid type instructions with encouragement to use the full Chart.js ecosystem. Remove the fixed decision rules. Instruct the agent to call `emit_chart` with a complete configuration.

9. **Update `__init__`**: Change the `tools` list from `[analyze_data_structure, generate_chart_spec, generate_visualization_description]` to `[analyze_data_structure, emit_chart, generate_visualization_description]`.

10. **Update `_agent_render`**: Simplify to parse `emit_chart` output directly without type validation or fallback to rule-based logic.

11. **Simplify `_fallback_render`**: Since rule-based chart selection is removed, the fallback should return a table representation (columns + rows) which is the safest generic fallback when the agent is unavailable.

---

**File**: `frontend/index.html`

**Function**: `renderChart`

**Specific Changes**:
1. **Accept full Chart.js config**: If `chartData` contains a complete Chart.js configuration (with `type`, `data`, `options`), pass it directly to `new Chart(canvas, chartData)` instead of constructing config piecemeal.

2. **Fallback to current behavior**: If chartData is in the legacy format (flat `labels`/`datasets`), continue constructing the config as before for backward compatibility.

3. **Remove chart type restriction**: The `renderChart` function should not assume only 5 chart types — pass whatever type is in the config to Chart.js.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Write tests that attempt to render chart types beyond the hardcoded 5 through the current system and observe failures. Run these tests on the UNFIXED code to observe rejections and fallback overrides.

**Test Cases**:
1. **Radar chart rejection**: Call `generate_chart_spec` with `chart_type="radar"` and observe it falls through to rule-based fallback (will fail on unfixed code)
2. **Doughnut type in agent output**: Mock agent output with `{"chart_type": "doughnut", ...}` and pass to `_extract_chart_from_agent` — observe it rejects and falls back (will fail on unfixed code)
3. **RenderedOutput validation failure**: Attempt to construct `RenderedOutput(chart_type="radar", ...)` and observe Pydantic validation error (will fail on unfixed code)
4. **Stacked bar config discarded**: Mock agent output with stacked bar options and observe the builder functions strip custom options (will fail on unfixed code)

**Expected Counterexamples**:
- Agent output with `chart_type: "radar"` gets overridden to "bar" by `_rule_based_chart`
- Pydantic raises `ValidationError` for `RenderedOutput(chart_type="doughnut")`
- Possible causes: hardcoded Literal type, explicit set membership check in `_extract_chart_from_agent`, builder functions ignoring unknown types

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  result := emit_chart(input.chart_config)
  rendered := render_pipeline(result)
  ASSERT rendered.chart_type == input.chart_config.type
  ASSERT rendered.chart_data contains input.chart_config
  ASSERT no rule-based override occurred
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT render_fixed(input).cache_behavior == render_original(input).cache_behavior
  ASSERT render_fixed(input).stats_text == render_original(input).stats_text
  ASSERT render_fixed(input).metadata == render_original(input).metadata
  ASSERT render_fixed(input).normalized_payload == render_original(input).normalized_payload
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many test cases automatically across the input domain (various payload shapes, query types, cache states)
- It catches edge cases that manual unit tests might miss (empty payloads, single-row aggregations, multi-source comparisons)
- It provides strong guarantees that caching, normalization, and stats generation are unchanged

**Test Plan**: Observe behavior on UNFIXED code first for caching, normalization, and stats generation, then write property-based tests capturing that behavior.

**Test Cases**:
1. **LRU Cache Preservation**: Verify that identical payload + query combinations still return cached results without LLM calls after the fix
2. **Payload Normalization Preservation**: Verify that aggregation, comparison, tabular, and multi-source payloads are normalized identically to columns + rows
3. **Stats Generation Preservation**: Verify that `_generate_stats_description` produces identical output for all payload types
4. **API Contract Preservation**: Verify POST /internal/render still accepts RenderRequest and returns RenderedOutput with all required fields
5. **Table Rendering Preservation**: Verify table-type outputs continue to include columns + rows for HTML table rendering
6. **Text Output Preservation**: Verify no-data and unstructured-data paths still return text output unchanged

### Unit Tests

- Test `emit_chart` tool accepts any valid Chart.js type string (radar, doughnut, polarArea, bubble, etc.)
- Test `emit_chart` tool passes through data and options without modification
- Test that `RenderedOutput` model accepts any string for `chart_type`
- Test that agent render path handles `emit_chart` output correctly
- Test fallback render produces table output when agent is unavailable
- Test frontend `renderChart` handles full Chart.js config objects

### Property-Based Tests

- Generate random valid Chart.js configurations with arbitrary type strings and verify they pass through `emit_chart` and `RenderedOutput` without rejection
- Generate random payload shapes (aggregation, comparison, tabular, multi-source) and verify normalization output matches the original implementation
- Generate random payload + query_type combinations and verify cache key computation is deterministic and consistent
- Generate random payloads and verify `_generate_stats_description` output is unchanged

### Integration Tests

- Test full render pipeline: RenderRequest → agent call → emit_chart → RenderedOutput with a non-standard chart type
- Test cache hit path with a previously rendered non-standard chart type
- Test fallback path when agent fails — verify it produces a valid table RenderedOutput
- Test frontend rendering of radar, doughnut, bubble, and polarArea chart types via Chart.js
