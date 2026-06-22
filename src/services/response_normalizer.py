"""Response Normalizer — Converts Agent Responses to Flat Data Format

Transforms structured agent responses (comparison, aggregation, lookup)
into flat, queryable data suitable for text-only summarization.

This layer sits between agent response handlers and text generators,
ensuring all downstream consumers see consistent flat data formats.

IMPORTANT: All returned text and responses must be plain text only. Never use markdown 
syntax, formatting, code blocks, headers, bold, italics, lists with *, -, or any other 
markdown elements. Use simple plain text format exclusively when generating summaries 
or responses.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ResponseNormalizer:
    """Normalizes structured agent responses to flat list/dict format."""

    @staticmethod
    def normalize_for_text(payload: dict[str, Any]) -> Any:
        """Convert any agent response payload into flat data for text generation.

        Args:
            payload: Agent response payload with keys like data_type, rows, groups, etc.

        Returns:
            Flat data suitable for TextSummaryGenerator:
            - For lookup/tabular: list of dicts with row data
            - For aggregation: dict with metric names as keys
            - For comparison: list of dicts with group + metric columns
        """
        if not isinstance(payload, dict):
            return payload

        data_type = payload.get("data_type", "").lower()

        # Lookup/Tabular: rows + columns → list of dicts
        if data_type in ("tabular", "lookup"):
            return ResponseNormalizer._flatten_tabular(payload)

        # Aggregation: single metrics → dict with metric names
        if data_type == "aggregation":
            return ResponseNormalizer._flatten_aggregation(payload)

        # Comparison: grouped metrics → list of dicts with group column
        if data_type == "comparison":
            return ResponseNormalizer._flatten_comparison(payload)

        # Unknown type — pass through as-is
        logger.warning(f"Unknown response data_type: {data_type}, passing through")
        return payload

    @staticmethod
    def _flatten_tabular(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert tabular response (rows + columns) to list of dicts.

        Handles multiple row formats:
        - List of lists: [[val1, val2], ...] + separate columns
        - List of dicts: [{"col1": val1, "col2": val2}, ...]
        - Already flat dict list

        Args:
            payload: Must have 'rows' and optionally 'columns'

        Returns:
            List of dicts mapping column names to values
        """
        rows = payload.get("rows", [])
        columns = payload.get("columns", [])

        if not rows:
            return []

        # Case 1: Rows are already dicts
        if isinstance(rows[0], dict):
            return rows

        # Case 2: Rows are lists, need to zip with columns
        if isinstance(rows[0], (list, tuple)):
            if not columns:
                # No column names — use generic col_0, col_1, ...
                columns = [f"col_{i}" for i in range(len(rows[0]))]

            result = []
            for row in rows:
                if not isinstance(row, (list, tuple)):
                    continue
                row_dict = {}
                for col_idx, col_name in enumerate(columns):
                    if col_idx < len(row):
                        row_dict[col_name] = row[col_idx]
                result.append(row_dict)
            return result

        # Case 3: Single row or unexpected format
        return rows if isinstance(rows, list) else [rows]

    @staticmethod
    def _flatten_aggregation(payload: dict[str, Any]) -> dict[str, Any]:
        """Convert aggregation response to flat metric dict.

        Aggregation responses have structure:
        {
          "data_type": "aggregation",
          "aggregations": {
            "column_name": {"sum": X, "avg": Y, "min": Z, "max": W, "count": C},
            ...
          }
        }

        Flatten to:
        {
          "column_name_sum": X,
          "column_name_avg": Y,
          ...
        }

        Args:
            payload: Aggregation response with 'aggregations' key

        Returns:
            Flat dict with metric values
        """
        aggregations = payload.get("aggregations", {})

        if not aggregations:
            return {}

        result = {}
        for col_name, metrics in aggregations.items():
            if not isinstance(metrics, dict):
                continue

            for metric_name, value in metrics.items():
                # Flatten: "revenue" + "sum" → "revenue_sum"
                flat_key = f"{col_name}_{metric_name}"
                result[flat_key] = value

        return result

    @staticmethod
    def _flatten_comparison(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Convert comparison response (grouped data) to flat list of dicts.

        Comparison responses have structure:
        {
          "data_type": "comparison",
          "groups": {
            "group_name_1": {
              "metric_column_1": {"sum": X, "avg": Y},
              "metric_column_2": {"sum": Z, "avg": W}
            },
            ...
          },
          "group_column": "category"
        }

        Flatten to list of dicts:
        [
          {
            "category": "group_name_1",
            "metric_column_1_sum": X,
            "metric_column_1_avg": Y,
            "metric_column_2_sum": Z,
            ...
          },
          ...
        ]

        Args:
            payload: Comparison response with 'groups' and 'group_column'

        Returns:
            List of dicts with group column + flattened metrics
        """
        groups = payload.get("groups", {})
        group_column = payload.get("group_column", "group")

        if not groups:
            return []

        result = []
        for group_name, group_metrics in groups.items():
            if not isinstance(group_metrics, dict):
                continue

            row = {group_column: group_name}

            # Flatten all metrics for this group
            for metric_col, metric_values in group_metrics.items():
                if not isinstance(metric_values, dict):
                    continue

                for metric_name, value in metric_values.items():
                    flat_key = f"{metric_col}_{metric_name}"
                    row[flat_key] = value

            result.append(row)

        return result


def normalize_response_for_text(payload: dict[str, Any]) -> Any:
    """Convenience function to normalize a response payload for text generation.

    Args:
        payload: Agent response payload

    Returns:
        Normalized flat data suitable for TextSummaryGenerator
    """
    return ResponseNormalizer.normalize_for_text(payload)
