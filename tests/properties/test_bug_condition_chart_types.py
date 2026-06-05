"""Property tests for Bug Condition: Non-Standard Chart Types Rejected by Renderer.

**Property 1: Bug Condition** - Non-Standard Chart Types Rejected by Renderer

These tests encode the EXPECTED BEHAVIOR: the system SHALL accept any valid
Chart.js chart type string without restriction.

On UNFIXED code, these tests are EXPECTED TO FAIL — failure confirms the bug exists
by showing that non-standard chart types (radar, doughnut, polarArea, bubble, etc.)
are rejected by RenderedOutput validation, overridden by _extract_chart_from_agent,
or restricted by generate_chart_spec.

Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.2, 2.3
"""

import json

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from pydantic import ValidationError

from src.models.shared import RenderedOutput
from src.services.visualization_renderer import (
    VisualizationRenderer,
)


# --- Strategies ---

# Valid Chart.js chart types NOT in the hardcoded set ['bar', 'line', 'scatter', 'pie', 'table']
non_standard_chartjs_types = st.sampled_from([
    "radar",
    "doughnut",
    "polarArea",
    "bubble",
    "area",
    "radialBar",
])

# The hardcoded types that the current system allows
hardcoded_types = {"bar", "line", "scatter", "pie", "table"}


# --- Property Tests ---


class TestBugConditionRenderedOutputAcceptsAnyChartType:
    """Bug Condition: RenderedOutput.chart_type should accept any valid Chart.js type string.

    On unfixed code, RenderedOutput uses Literal["bar", "line", "scatter", "pie", "table"]
    which causes Pydantic ValidationError for non-standard types like "radar", "doughnut", etc.

    **Validates: Requirements 1.1, 2.1, 2.5**
    """

    @given(chart_type=non_standard_chartjs_types)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_rendered_output_accepts_non_standard_chart_type(self, chart_type: str) -> None:
        """RenderedOutput SHALL accept any valid Chart.js chart type string.

        Expected behavior: No ValidationError raised.
        Bug behavior: Pydantic raises ValidationError because chart_type is
        Literal["bar", "line", "scatter", "pie", "table"].
        """
        # This should NOT raise a ValidationError for any valid Chart.js type
        output = RenderedOutput(
            output_type="chart",
            chart_type=chart_type,
            chart_data={"type": chart_type, "data": {"labels": ["A"], "datasets": []}},
            text_content=None,
            description=f"A {chart_type} chart visualization.",
            metadata={"query_id": "test-123", "timestamp": "2024-01-01T00:00:00Z", "data_sources": []},
        )
        assert output.chart_type == chart_type


class TestBugConditionExtractChartFromAgent:
    """Bug Condition: emit_chart output parser SHALL preserve any chart type.

    The new architecture uses _extract_emit_chart to parse the emit_chart tool
    result from agent text. It must not restrict or override the chart type.

    **Validates: Requirements 1.2, 2.2, 2.3**
    """

    @given(chart_type=non_standard_chartjs_types)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_extract_chart_preserves_non_standard_type(self, chart_type: str) -> None:
        """_extract_emit_chart SHALL preserve any valid Chart.js chart type from agent output.

        Expected behavior: chart_config.type equals the agent's chosen type.
        Bug behavior (old): chart_type was overridden to one of 5 hardcoded values.
        """
        # Simulate what the emit_chart tool returns as part of agent response text
        emit_chart_result = json.dumps({
            "chart_config": {
                "type": chart_type,
                "data": {"labels": ["A", "B", "C"], "datasets": [{"label": "val", "data": [1, 2, 3]}]},
                "options": {"responsive": True},
            },
            "title": f"A {chart_type} chart",
            "description": f"Data displayed as {chart_type}",
        })

        result = VisualizationRenderer._extract_emit_chart(emit_chart_result)

        assert result is not None, "Failed to extract emit_chart result from agent output"
        config = result.get("chart_config", {})
        assert config.get("type") == chart_type, (
            f"Expected chart type='{chart_type}' but got '{config.get('type')}'. "
            f"The system overrode the agent's chart type choice."
        )


class TestBugConditionGenerateChartSpecRestriction:
    """Bug Condition: generate_chart_spec tool restriction is removed.

    On unfixed code, generate_chart_spec only routes through builder functions
    for the 5 hardcoded types. Non-standard types get no builder and produce
    incomplete specs (missing data mappings).

    After fix: generate_chart_spec is entirely removed. The system uses emit_chart
    which accepts any valid Chart.js configuration without type restriction.

    **Validates: Requirements 1.3, 2.1, 2.3**
    """

    def test_generate_chart_spec_no_longer_exists(self) -> None:
        """generate_chart_spec tool SHALL no longer exist in the module.

        Expected behavior: The restrictive tool is removed, replaced by emit_chart.
        Bug behavior: The tool exists and only handles 5 hardcoded types.
        """
        import src.services.visualization_renderer as vr
        assert not hasattr(vr, 'generate_chart_spec'), (
            "generate_chart_spec still exists — it should be removed "
            "as it restricts chart types to the 5 hardcoded literals."
        )

    @given(chart_type=non_standard_chartjs_types)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_no_rule_based_chart_override(self, chart_type: str) -> None:
        """No rule-based chart selection SHALL override agent chart type choices.

        Expected behavior: _rule_based_chart method does not exist.
        Bug behavior: _rule_based_chart deterministically overrides non-standard types.
        """
        assert not hasattr(VisualizationRenderer, '_rule_based_chart'), (
            "_rule_based_chart still exists — it should be removed "
            "as it overrides agent chart type choices with hardcoded rules."
        )
        assert not hasattr(VisualizationRenderer, '_extract_chart_from_agent'), (
            "_extract_chart_from_agent still exists — it should be removed "
            "as it validates chart types against a hardcoded set."
        )
