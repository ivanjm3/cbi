# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - Non-Standard Chart Types Rejected by Renderer
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Generate valid Chart.js chart type strings NOT in the hardcoded set (e.g., "radar", "doughnut", "polarArea", "bubblx`e") and verify the system rejects them
  - Test that `RenderedOutput(chart_type="radar", ...)` raises Pydantic `ValidationError` (from Bug Condition: `input.agent_output.chart_type NOT IN ['bar', 'line', 'scatter', 'pie', 'table']`)
  - Test that `_extract_chart_from_agent` with agent output containing `chart_type: "doughnut"` falls through to `_rule_based_chart` and overrides to a hardcoded type
  - Test that `generate_chart_spec` tool only accepts one of the 5 hardcoded types, ignoring valid Chart.js types like "radar", "polarArea", "bubble"
  - The test assertions should match the Expected Behavior: system SHALL accept any valid Chart.js chart type string without restriction
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists by showing non-standard types are rejected)
  - Document counterexamples found (e.g., `RenderedOutput(chart_type="radar")` raises ValidationError, agent output with "doughnut" gets overridden to "bar")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Caching, Normalization, Stats, and Metadata Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - Observe: `_normalize_payload` with aggregation payload `{"data_type": "aggregation", "aggregations": {"revenue": {"sum": 100, "avg": 50, "min": 10, "max": 90, "count": 5}}}` returns `(["metric", "sum", "avg", "min", "max", "count"], [["revenue", 100, 50, 10, 90, 5]])` on unfixed code
  - Observe: `_normalize_payload` with comparison payload `{"data_type": "comparison", "groups": {"A": {"revenue": {"sum": 100}, "count": 5}, "B": {"revenue": {"sum": 200}, "count": 10}}, "group_by": "region"}` returns correct columns + rows on unfixed code
  - Observe: `_generate_stats_description` produces identical text for aggregation, comparison, tabular, and multi-source payloads on unfixed code
  - Observe: `_compute_render_cache_key` produces the same deterministic SHA-256 hash for identical payload + query_type combinations on unfixed code
  - Observe: `_build_metadata` includes query_id, timestamp, data_sources on unfixed code
  - Write property-based test: for all valid payload shapes (aggregation, comparison, tabular, multi-source), `_normalize_payload` produces consistent columns + rows (from Preservation Requirements in design)
  - Write property-based test: for all valid payloads, `_generate_stats_description` output is deterministic and matches observed format
  - Write property-based test: for identical payload + query_type, cache key is always the same (deterministic hashing)
  - Write property-based test: `_build_metadata` always includes query_id, timestamp, data_sources fields
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Implement flexible visualization renderer fix

  - [x] 3.1 Widen RenderedOutput.chart_type from Literal to str
    - In `src/models/shared.py`, change `chart_type: Literal["bar", "line", "scatter", "pie", "table"] | None = None` to `chart_type: str | None = None`
    - Remove the `Literal` import if no longer used elsewhere in the file
    - _Bug_Condition: isBugCondition(input) where input.agent_output.chart_type NOT IN ['bar', 'line', 'scatter', 'pie', 'table']_
    - _Expected_Behavior: RenderedOutput accepts any valid Chart.js chart type string_
    - _Preservation: API contract RenderedOutput schema structure unchanged (only field type widens)_
    - _Requirements: 1.1, 2.1, 2.5_

  - [x] 3.2 Remove builder functions and rule-based chart selection from visualization_renderer.py
    - Delete `_build_line_spec`, `_build_bar_spec`, `_build_scatter_spec`, `_build_pie_spec` helper functions
    - Delete `_rule_based_chart` method from `VisualizationRenderer` class
    - Delete `_build_requested_chart` method from `VisualizationRenderer` class
    - Delete `_looks_like_time_series` static method from `VisualizationRenderer` class
    - Delete `_extract_chart_from_agent` method from `VisualizationRenderer` class
    - Delete `generate_chart_spec` tool function
    - Remove the `DATE_PATTERNS` constant (only used by rule-based logic)
    - _Bug_Condition: system_config.tool_restricts_type_to_literals == true AND system_config.fallback_overrides_agent_choice == true_
    - _Expected_Behavior: No rule-based override occurs; no per-type builder functions exist_
    - _Preservation: `analyze_data_structure` and `generate_visualization_description` tools remain available_
    - _Requirements: 1.2, 1.3, 2.2, 2.3_

  - [x] 3.3 Add emit_chart tool
    - Add a new `@tool` function `emit_chart` that accepts: `chart_config` (str - complete Chart.js JSON with type, data, options), `title` (str), `description` (str)
    - The tool should validate that chart_config is parseable JSON and contains a `type` field
    - Return the parsed config as JSON string for the renderer to include in RenderedOutput
    - _Bug_Condition: system restricts to 5 types via per-type tools_
    - _Expected_Behavior: Single emit_chart tool accepts any valid Chart.js JSON configuration_
    - _Preservation: Tool still returns JSON string for consistent agent interaction_
    - _Requirements: 2.1, 2.3_

  - [x] 3.4 Update VISUALIZER_SYSTEM_PROMPT
    - Replace the rigid chart type instructions (`"chart_type": "bar|line|scatter|pie|table"`) with encouragement to use the full Chart.js ecosystem
    - Remove the fixed decision rules (e.g., "Category comparisons with ≤6 items → pie chart")
    - Instruct the agent to call `emit_chart` with a complete Chart.js configuration (type, data, options)
    - List example chart types: bar, line, scatter, pie, doughnut, radar, polarArea, bubble, stacked bar, area, treemap, heatmap
    - Instruct the agent to use `analyze_data_structure` first, then call `emit_chart` with a full config
    - _Bug_Condition: System prompt limits choices to "bar|line|scatter|pie|table"_
    - _Expected_Behavior: System prompt encourages creative use of full Chart.js type ecosystem_
    - _Requirements: 1.4, 2.4_

  - [x] 3.5 Simplify agent render and fallback paths
    - Update `__init__` tools list: replace `generate_chart_spec` with `emit_chart`
    - Update `_agent_render`: parse `emit_chart` output from agent response — look for the tool result containing Chart.js config, extract type/data/options directly
    - Remove `_extract_chart_from_agent` calls and rule-based fallback logic from `_agent_render`
    - Simplify `_fallback_render`: when agent is unavailable, return a table representation (columns + rows) as the safe generic fallback
    - _Bug_Condition: Agent render path validates chart_type against hardcoded set and falls back to rule-based selection_
    - _Expected_Behavior: Agent render path passes emit_chart output directly to RenderedOutput without type validation_
    - _Preservation: LRU caching, payload normalization, stats generation, metadata construction remain unchanged_
    - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

  - [x] 3.6 Update frontend/index.html to handle arbitrary Chart.js configs
    - Modify `renderChart` to detect if `chartData` contains a complete Chart.js config (has `type`, `data`, `options` fields)
    - If full config detected: pass it directly to `new Chart(canvas, chartData)` (or merge with sensible defaults for responsive/maintainAspectRatio)
    - If legacy format (flat `labels`/`datasets`): continue constructing the config as before for backward compatibility
    - Remove the hardcoded scatter/bubble special-casing — full configs handle their own options
    - _Bug_Condition: Frontend only expects 5 hardcoded chart types and constructs config piecemeal_
    - _Expected_Behavior: Frontend renders any valid Chart.js chart type by passing full config to Chart.js constructor_
    - _Preservation: Table rendering via HTML elements unchanged; legacy chart format still supported_
    - _Requirements: 1.5, 2.5, 3.6_

  - [x] 3.7 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Non-Standard Chart Types Accepted by Renderer
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (any valid Chart.js type accepted)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed — non-standard types are now accepted)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.8 Verify preservation tests still pass
    - **Property 2: Preservation** - Caching, Normalization, Stats, and Metadata Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions in caching, normalization, stats, metadata)
    - Confirm all preservation tests still pass after fix (no regressions in non-chart-selection behavior)

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite to ensure no regressions
  - Verify bug condition test (Property 1) passes — non-standard chart types accepted
  - Verify preservation tests (Property 2) pass — caching, normalization, stats, metadata unchanged
  - Verify existing unit and property tests in `tests/` still pass
  - Ensure all tests pass, ask the user if questions arise.