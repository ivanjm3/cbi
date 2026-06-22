"""Tests for Response Normalizer

Verifies that all agent response formats are correctly converted to flat data.
"""

import pytest
from src.services.response_normalizer import ResponseNormalizer


class TestTabularNormalization:
    """Test flattening of tabular responses."""

    def test_rows_as_lists_with_columns(self):
        """List of lists + column names → list of dicts."""
        payload = {
            "data_type": "tabular",
            "columns": ["quarter", "revenue"],
            "rows": [["Q1", 100000], ["Q2", 150000]],
        }
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == [
            {"quarter": "Q1", "revenue": 100000},
            {"quarter": "Q2", "revenue": 150000},
        ]

    def test_rows_as_dicts(self):
        """List of dicts (already flat) → pass through."""
        payload = {
            "data_type": "tabular",
            "rows": [
                {"category": "Electronics", "orders": 23680},
                {"category": "Furniture", "orders": 6310},
            ],
        }
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == [
            {"category": "Electronics", "orders": 23680},
            {"category": "Furniture", "orders": 6310},
        ]

    def test_empty_rows(self):
        """Empty rows → empty list."""
        payload = {"data_type": "tabular", "rows": []}
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == []

    def test_missing_columns_uses_generic_names(self):
        """No column names → use col_0, col_1, ..."""
        payload = {
            "data_type": "tabular",
            "rows": [["value1", "value2"], ["value3", "value4"]],
        }
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == [
            {"col_0": "value1", "col_1": "value2"},
            {"col_0": "value3", "col_1": "value4"},
        ]


class TestAggregationNormalization:
    """Test flattening of aggregation responses."""

    def test_simple_aggregation(self):
        """Aggregation metrics → flat dict with metric names as keys."""
        payload = {
            "data_type": "aggregation",
            "aggregations": {
                "revenue": {"sum": 6629000.0, "avg": 275375.0, "min": 0, "max": 3616000},
                "orders": {"sum": 61590, "avg": 2566, "min": 0, "max": 31600},
            },
        }
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == {
            "revenue_sum": 6629000.0,
            "revenue_avg": 275375.0,
            "revenue_min": 0,
            "revenue_max": 3616000,
            "orders_sum": 61590,
            "orders_avg": 2566,
            "orders_min": 0,
            "orders_max": 31600,
        }

    def test_empty_aggregations(self):
        """No aggregations → empty dict."""
        payload = {"data_type": "aggregation", "aggregations": {}}
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == {}


class TestComparisonNormalization:
    """Test flattening of comparison (grouped) responses."""

    def test_comparison_groups(self):
        """Groups with metrics → list of dicts with group column."""
        payload = {
            "data_type": "comparison",
            "group_column": "category",
            "groups": {
                "Electronics": {
                    "revenue": {"sum": 3616000.0, "avg": 152681},
                    "orders": {"sum": 23680, "avg": 987},
                },
                "Office Furniture": {
                    "revenue": {"sum": 2249000.0, "avg": 356500},
                    "orders": {"sum": 6310, "avg": 1050},
                },
            },
        }
        result = ResponseNormalizer.normalize_for_text(payload)

        # Should be list with one dict per group
        assert len(result) == 2

        # Check first group
        electronics = next(r for r in result if r["category"] == "Electronics")
        assert electronics["revenue_sum"] == 3616000.0
        assert electronics["revenue_avg"] == 152681
        assert electronics["orders_sum"] == 23680
        assert electronics["orders_avg"] == 987

        # Check second group
        furniture = next(r for r in result if r["category"] == "Office Furniture")
        assert furniture["revenue_sum"] == 2249000.0
        assert furniture["orders_sum"] == 6310

    def test_empty_groups(self):
        """No groups → empty list."""
        payload = {"data_type": "comparison", "groups": {}, "group_column": "category"}
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == []

    def test_default_group_column_name(self):
        """Missing group_column → use 'group' as default."""
        payload = {
            "data_type": "comparison",
            "groups": {
                "Group A": {"metric": {"sum": 100}},
            },
        }
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == [{"group": "Group A", "metric_sum": 100}]


class TestUnknownFormat:
    """Test handling of unknown response formats."""

    def test_unknown_data_type(self):
        """Unknown data_type → pass through as-is."""
        payload = {
            "data_type": "unknown_future_type",
            "some_field": "some_value",
        }
        result = ResponseNormalizer.normalize_for_text(payload)
        assert result == payload

    def test_non_dict_input(self):
        """Non-dict input → pass through."""
        result = ResponseNormalizer.normalize_for_text("just a string")
        assert result == "just a string"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
