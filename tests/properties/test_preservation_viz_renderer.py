"""Property tests for Preservation: Caching, Normalization, Stats, and Metadata Unchanged.

**Property 2: Preservation** - Caching, Normalization, Stats, and Metadata Unchanged

These tests observe and verify that the following behaviors are preserved on
the UNFIXED code, establishing a baseline for regression prevention:

- `_normalize_payload` produces consistent columns + rows for all payload types
- `_generate_stats_description` produces deterministic text output
- `_compute_render_cache_key` produces deterministic SHA-256 hashes
- `_build_metadata` includes query_id, timestamp, data_sources

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**
"""

import json
from datetime import datetime, timezone
from uuid import uuid4

from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from src.models.shared import AgentResult, OrchestratorResponse
from src.services.visualization_renderer import VisualizationRenderer


# --- Strategies ---

# Strategy for metric names used in aggregation payloads
metric_names = st.sampled_from([
    "revenue", "cost", "profit", "count", "sales",
    "units", "margin", "expenses", "growth", "rate",
])

# Strategy for group names used in comparison payloads
group_names = st.sampled_from([
    "A", "B", "C", "D", "E", "North", "South", "East", "West",
    "Q1", "Q2", "Q3", "Q4", "Region1", "Region2",
])

# Strategy for query types
query_types = st.sampled_from(["lookup", "aggregation", "comparison"])

# Strategy for positive numbers (used in aggregation values)
positive_numbers = st.floats(min_value=0.1, max_value=1_000_000, allow_nan=False, allow_infinity=False)

# Strategy for non-negative integers (counts)
positive_integers = st.integers(min_value=1, max_value=100_000)


# Strategy for aggregation payloads
@st.composite
def aggregation_payloads(draw):
    """Generate valid aggregation payloads with at least one metric."""
    num_metrics = draw(st.integers(min_value=1, max_value=4))
    metrics = draw(st.lists(metric_names, min_size=num_metrics, max_size=num_metrics, unique=True))

    aggregations = {}
    for metric in metrics:
        sum_val = draw(positive_numbers)
        count_val = draw(positive_integers)
        avg_val = sum_val / count_val
        min_val = draw(st.floats(min_value=0.0, max_value=float(sum_val), allow_nan=False, allow_infinity=False))
        max_val = draw(st.floats(min_value=float(min_val), max_value=float(sum_val * 2), allow_nan=False, allow_infinity=False))

        aggregations[metric] = {
            "sum": round(sum_val, 2),
            "avg": round(avg_val, 2),
            "min": round(min_val, 2),
            "max": round(max_val, 2),
            "count": count_val,
        }

    return {
        "data_type": "aggregation",
        "aggregations": aggregations,
        "row_count": draw(positive_integers),
    }


# Strategy for comparison payloads
@st.composite
def comparison_payloads(draw):
    """Generate valid comparison payloads with at least 2 groups."""
    num_groups = draw(st.integers(min_value=2, max_value=5))
    groups_list = draw(st.lists(group_names, min_size=num_groups, max_size=num_groups, unique=True))
    num_metrics = draw(st.integers(min_value=1, max_value=3))
    metrics = draw(st.lists(metric_names, min_size=num_metrics, max_size=num_metrics, unique=True))
    group_by = draw(st.sampled_from(["region", "category", "segment", "department"]))

    groups = {}
    for group_name in groups_list:
        group_data = {}
        for metric in metrics:
            group_data[metric] = {
                "sum": round(draw(positive_numbers), 2),
            }
        group_data["count"] = draw(positive_integers)
        groups[group_name] = group_data

    return {
        "data_type": "comparison",
        "groups": groups,
        "group_by": group_by,
        "row_count": draw(positive_integers),
    }


# Strategy for tabular payloads
@st.composite
def tabular_payloads(draw):
    """Generate valid tabular payloads with columns and rows."""
    num_cols = draw(st.integers(min_value=2, max_value=5))
    col_names = draw(st.lists(
        st.sampled_from(["name", "category", "value", "amount", "date", "region", "count", "price", "total", "id"]),
        min_size=num_cols, max_size=num_cols, unique=True,
    ))
    num_rows = draw(st.integers(min_value=1, max_value=10))

    rows = []
    for _ in range(num_rows):
        row = []
        for col in col_names:
            if col in ("value", "amount", "count", "price", "total"):
                row.append(round(draw(positive_numbers), 2))
            else:
                row.append(draw(st.sampled_from(["alpha", "beta", "gamma", "delta", "epsilon"])))
        rows.append(row)

    return {
        "data_type": "tabular",
        "columns": col_names,
        "rows": rows,
        "row_count": num_rows,
    }


# Strategy for all valid payload shapes
all_payloads = st.one_of(aggregation_payloads(), comparison_payloads(), tabular_payloads())


# --- Helper to create a renderer instance without initializing agent ---

def _create_renderer():
    """Create a VisualizationRenderer instance bypassing __init__ (no LLM needed)."""
    renderer = VisualizationRenderer.__new__(VisualizationRenderer)
    return renderer


# --- Property Tests ---


class TestPreservationNormalizePayload:
    """Preservation: _normalize_payload produces consistent columns + rows for all payload types.

    **Validates: Requirements 3.1**
    """

    @given(payload=aggregation_payloads())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_aggregation_returns_correct_columns(self, payload: dict) -> None:
        """_normalize_payload with aggregation payload returns columns
        ["metric", "sum", "avg", "min", "max", "count"] and one row per metric.

        **Validates: Requirements 3.1**
        """
        renderer = _create_renderer()
        columns, rows = renderer._normalize_payload(payload)

        expected_columns = ["metric", "sum", "avg", "min", "max", "count"]
        assert columns == expected_columns, (
            f"Expected columns {expected_columns} but got {columns}"
        )
        assert len(rows) == len(payload["aggregations"]), (
            f"Expected {len(payload['aggregations'])} rows but got {len(rows)}"
        )
        # Each row has 6 elements: metric name + 5 stat values
        for row in rows:
            assert len(row) == 6
            assert isinstance(row[0], str)  # metric name

    @given(payload=comparison_payloads())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_comparison_returns_correct_structure(self, payload: dict) -> None:
        """_normalize_payload with comparison payload returns group_by column,
        metric_sum columns, and a count column with one row per group.

        **Validates: Requirements 3.1**
        """
        renderer = _create_renderer()
        columns, rows = renderer._normalize_payload(payload)

        # First column should be the group_by field
        assert columns[0] == payload["group_by"], (
            f"Expected first column to be '{payload['group_by']}' but got '{columns[0]}'"
        )
        # Last column should be 'count'
        assert columns[-1] == "count", (
            f"Expected last column to be 'count' but got '{columns[-1]}'"
        )
        # Number of rows equals number of groups
        assert len(rows) == len(payload["groups"]), (
            f"Expected {len(payload['groups'])} rows but got {len(rows)}"
        )
        # Each row's first element is the group name
        group_names_in_rows = [row[0] for row in rows]
        for group_name in payload["groups"]:
            assert group_name in group_names_in_rows

    @given(payload=tabular_payloads())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_tabular_passes_through(self, payload: dict) -> None:
        """_normalize_payload with tabular payload passes columns and rows through unchanged.

        **Validates: Requirements 3.1**
        """
        renderer = _create_renderer()
        columns, rows = renderer._normalize_payload(payload)

        assert columns == payload["columns"]
        assert rows == payload["rows"]

    @given(payload=all_payloads)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_normalize_is_deterministic(self, payload: dict) -> None:
        """_normalize_payload produces identical output on repeated calls with same input.

        **Validates: Requirements 3.1**
        """
        renderer = _create_renderer()
        columns1, rows1 = renderer._normalize_payload(payload)
        columns2, rows2 = renderer._normalize_payload(payload)

        assert columns1 == columns2
        assert rows1 == rows2


class TestPreservationStatsDescription:
    """Preservation: _generate_stats_description produces deterministic text for all payload types.

    **Validates: Requirements 3.4**
    """

    @given(payload=aggregation_payloads())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_stats_description_aggregation_format(self, payload: dict) -> None:
        """_generate_stats_description with aggregation payload produces text starting
        with 'Aggregation across N records:' and containing metric bullet points.

        **Validates: Requirements 3.4**
        """
        renderer = _create_renderer()
        result = renderer._generate_stats_description(payload)

        assert result.startswith(f"Aggregation across {payload['row_count']} records:")
        for metric in payload["aggregations"]:
            assert f"• {metric}:" in result

    @given(payload=comparison_payloads())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_stats_description_comparison_format(self, payload: dict) -> None:
        """_generate_stats_description with comparison payload produces text starting
        with 'Comparison across N groups' and containing group bullet points.

        **Validates: Requirements 3.4**
        """
        renderer = _create_renderer()
        result = renderer._generate_stats_description(payload)

        num_groups = len(payload["groups"])
        assert f"Comparison across {num_groups} groups" in result
        for group_name in payload["groups"]:
            assert f"• {group_name}" in result

    @given(payload=tabular_payloads())
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_stats_description_tabular_format(self, payload: dict) -> None:
        """_generate_stats_description with tabular payload produces text
        with 'Tabular data with N rows and M columns.'

        **Validates: Requirements 3.4**
        """
        renderer = _create_renderer()
        result = renderer._generate_stats_description(payload)

        expected = f"Tabular data with {payload['row_count']} rows and {len(payload['columns'])} columns."
        assert result == expected

    @given(payload=all_payloads)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_stats_description_is_deterministic(self, payload: dict) -> None:
        """_generate_stats_description produces identical text on repeated calls.

        **Validates: Requirements 3.4**
        """
        renderer = _create_renderer()
        result1 = renderer._generate_stats_description(payload)
        result2 = renderer._generate_stats_description(payload)

        assert result1 == result2


class TestPreservationCacheKey:
    """Preservation: _compute_render_cache_key produces deterministic SHA-256 hashes.

    **Validates: Requirements 3.2**
    """

    @given(payload=all_payloads, query_type=query_types)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_cache_key_deterministic(self, payload: dict, query_type: str) -> None:
        """_cache_key produces the same hash for identical payload + query_type.

        **Validates: Requirements 3.2**
        """
        renderer = _create_renderer()
        key1 = renderer._cache_key(payload, query_type)
        key2 = renderer._cache_key(payload, query_type)

        assert key1 == key2, (
            f"Cache key not deterministic: '{key1}' != '{key2}'"
        )

    @given(payload=all_payloads, query_type=query_types)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_cache_key_is_sha256_hex(self, payload: dict, query_type: str) -> None:
        """_cache_key returns a valid 64-character hex string (SHA-256).

        **Validates: Requirements 3.2**
        """
        renderer = _create_renderer()
        key = renderer._cache_key(payload, query_type)

        # SHA-256 hex digest is always 64 chars
        assert len(key) == 64, f"Expected 64-char hex but got {len(key)} chars"
        assert all(c in "0123456789abcdef" for c in key), (
            f"Cache key contains non-hex characters: {key}"
        )

    @given(
        payload=all_payloads,
        query_type1=query_types,
        query_type2=query_types,
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_cache_key_differs_for_different_query_types(
        self, payload: dict, query_type1: str, query_type2: str
    ) -> None:
        """_cache_key produces different hashes for different query_types.

        **Validates: Requirements 3.2**
        """
        assume(query_type1 != query_type2)
        renderer = _create_renderer()
        key1 = renderer._cache_key(payload, query_type1)
        key2 = renderer._cache_key(payload, query_type2)

        assert key1 != key2, (
            f"Different query types '{query_type1}' and '{query_type2}' "
            f"produced the same cache key: {key1}"
        )


class TestPreservationBuildMetadata:
    """Preservation: _build_metadata includes query_id, timestamp, data_sources.

    **Validates: Requirements 3.4, 3.5**
    """

    @given(
        query_type=query_types,
        num_results=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_build_metadata_includes_required_fields(
        self, query_type: str, num_results: int
    ) -> None:
        """_build_metadata always includes query_id, timestamp, and data_sources fields.

        **Validates: Requirements 3.4, 3.5**
        """
        query_id = uuid4()
        results = [
            AgentResult(
                status="success",
                payload={"data_type": "tabular", "columns": ["a"], "rows": [[1]]},
                agent_id=f"agent_{i}",
                data_source=f"source_{i}",
            )
            for i in range(num_results)
        ]
        response = OrchestratorResponse(
            query_id=query_id,
            results=results,
        )
        intent_metadata = {"query_type": query_type, "query_text": "test query"}

        renderer = _create_renderer()
        metadata = renderer._build_metadata(response, intent_metadata)

        # Must include query_id
        assert "query_id" in metadata, "metadata missing 'query_id'"
        assert metadata["query_id"] == str(query_id)

        # Must include timestamp
        assert "timestamp" in metadata, "metadata missing 'timestamp'"
        # Verify timestamp is a valid ISO format string
        datetime.fromisoformat(metadata["timestamp"])

        # Must include data_sources
        assert "data_sources" in metadata, "metadata missing 'data_sources'"
        assert len(metadata["data_sources"]) == num_results
        for i in range(num_results):
            assert f"source_{i}" in metadata["data_sources"]

    @given(query_type=query_types)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_build_metadata_with_no_intent_metadata(self, query_type: str) -> None:
        """_build_metadata works correctly when intent_metadata is None.

        **Validates: Requirements 3.4, 3.5**
        """
        query_id = uuid4()
        response = OrchestratorResponse(
            query_id=query_id,
            results=[
                AgentResult(
                    status="success",
                    payload={"data": "test"},
                    agent_id="agent_0",
                    data_source="db_source",
                )
            ],
        )

        renderer = _create_renderer()
        metadata = renderer._build_metadata(response, None)

        assert "query_id" in metadata
        assert "timestamp" in metadata
        assert "data_sources" in metadata
        assert metadata["data_sources"] == ["db_source"]

    @given(query_type=query_types)
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow])
    def test_build_metadata_excludes_failed_agents_from_data_sources(
        self, query_type: str
    ) -> None:
        """_build_metadata only includes data_sources from successful agent results.

        **Validates: Requirements 3.4, 3.5**
        """
        query_id = uuid4()
        response = OrchestratorResponse(
            query_id=query_id,
            results=[
                AgentResult(
                    status="success",
                    payload={"data": "test"},
                    agent_id="agent_ok",
                    data_source="good_source",
                ),
                AgentResult(
                    status="error",
                    error_type="TIMEOUT",
                    error_description="timed out",
                    agent_id="agent_fail",
                    data_source="bad_source",
                ),
            ],
        )

        renderer = _create_renderer()
        metadata = renderer._build_metadata(response, {"query_type": query_type})

        assert "good_source" in metadata["data_sources"]
        assert "bad_source" not in metadata["data_sources"]
