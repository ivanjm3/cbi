"""Cost Tracker for AWS Bedrock usage — S3-backed.

Tracks every Bedrock model invocation with input/output tokens and estimated cost.
Stores records as JSON objects in S3, organized by date for efficient querying.

S3 structure:
  s3://visualization-poc-bucket/costs/{YYYY-MM-DD}/{uuid}.json

Cost data is based on current Bedrock pricing:
- Claude Haiku: $0.25 per 1M input tokens, $1.25 per 1M output tokens
- Titan Embeddings V2: $0.02 per 1M tokens
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.config import S3_BUCKET, S3_COSTS_PREFIX, get_s3_client

logger = logging.getLogger(__name__)

# Bedrock pricing (per 1M tokens)
PRICING = {
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": {
        "input_per_1m": 0.80,
        "output_per_1m": 4.00,
    },
    "anthropic.claude-haiku-4-5-20251001-v1:0": {
        "input_per_1m": 0.25,
        "output_per_1m": 1.25,
    },
    "us.anthropic.claude-sonnet-4-20250514-v1:0": {
        "input_per_1m": 3.00,
        "output_per_1m": 15.00,
    },
    "amazon.titan-embed-text-v2:0": {
        "input_per_1m": 0.02,
        "output_per_1m": 0.0,
    },
    "amazon.titan-embed-text-v1": {
        "input_per_1m": 0.10,
        "output_per_1m": 0.0,
    },
}


class CostTracker:
    """S3-backed cost tracker for Bedrock usage.

    Records every model invocation as a JSON file in S3, organized by date.
    Provides daily, monthly, and all-time reporting.
    """

    def __init__(self, bucket: str = S3_BUCKET, prefix: str = S3_COSTS_PREFIX):
        """Initialize the cost tracker.

        Args:
            bucket: S3 bucket name.
            prefix: S3 key prefix for cost records.
        """
        self.bucket = bucket
        self.prefix = prefix
        self._s3 = get_s3_client()

    def log_invocation(
        self,
        model_id: str,
        component: str,
        input_tokens: int,
        output_tokens: int,
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a Bedrock model invocation to S3.

        Args:
            model_id: The Bedrock model ID.
            component: Which component made the call.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            correlation_id: Request correlation ID.
            metadata: Optional additional metadata.
        """
        cost = self._calculate_cost(model_id, input_tokens, output_tokens)
        now = datetime.now(timezone.utc)
        record_id = str(uuid.uuid4())
        date_str = now.date().isoformat()

        record = {
            "id": record_id,
            "timestamp": now.isoformat(),
            "model_id": model_id,
            "component": component,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "correlation_id": correlation_id,
            "metadata": metadata,
        }

        try:
            key = f"{self.prefix}{date_str}/{record_id}.json"
            self._s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(record),
                ContentType="application/json",
            )
        except Exception as e:
            # Don't let tracking failures break the application
            logger.warning(f"Failed to log cost record to S3: {e}")

    def _calculate_cost(self, model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate estimated cost for a model invocation."""
        pricing = PRICING.get(model_id, PRICING["anthropic.claude-haiku-4-5-20251001-v1:0"])
        input_cost = (input_tokens / 1_000_000) * pricing["input_per_1m"]
        output_cost = (output_tokens / 1_000_000) * pricing["output_per_1m"]
        return input_cost + output_cost

    def get_daily_summary(self, date: str | None = None) -> dict[str, Any]:
        """Get cost summary for a specific date.

        Args:
            date: Date in YYYY-MM-DD format. Defaults to today.

        Returns:
            Dict with total_cost, total_calls, breakdown by component.
        """
        if date is None:
            date = datetime.now(timezone.utc).date().isoformat()

        records = self._load_records_for_prefix(f"{self.prefix}{date}/")
        return self._summarize_records(records, date=date)

    def get_monthly_summary(self, year: int, month: int) -> dict[str, Any]:
        """Get cost summary for a specific month.

        Args:
            year: Year.
            month: Month (1-12).

        Returns:
            Dict with total_cost, total_calls, daily breakdown.
        """
        month_prefix = f"{self.prefix}{year}-{month:02d}"
        records = self._load_records_for_prefix(month_prefix)

        summary = self._summarize_records(records)
        summary["year"] = year
        summary["month"] = month

        # Daily breakdown
        daily: dict[str, dict] = {}
        for record in records:
            day = record["timestamp"][:10]
            if day not in daily:
                daily[day] = {"date": day, "calls": 0, "cost_usd": 0.0}
            daily[day]["calls"] += 1
            daily[day]["cost_usd"] += record.get("cost_usd", 0.0)

        summary["daily"] = sorted(daily.values(), key=lambda x: x["date"])
        return summary

    def get_all_time_summary(self) -> dict[str, Any]:
        """Get all-time cost summary."""
        records = self._load_records_for_prefix(self.prefix)
        summary = self._summarize_records(records)

        # Breakdown by model
        by_model: dict[str, dict] = {}
        for record in records:
            model = record.get("model_id", "unknown")
            if model not in by_model:
                by_model[model] = {"model_id": model, "calls": 0, "cost_usd": 0.0}
            by_model[model]["calls"] += 1
            by_model[model]["cost_usd"] += record.get("cost_usd", 0.0)

        summary["by_model"] = sorted(by_model.values(), key=lambda x: x["cost_usd"], reverse=True)
        return summary

    def _summarize_records(self, records: list[dict], date: str | None = None) -> dict[str, Any]:
        """Summarize a list of cost records."""
        total_calls = len(records)
        total_cost = sum(r.get("cost_usd", 0.0) for r in records)
        total_input = sum(r.get("input_tokens", 0) for r in records)
        total_output = sum(r.get("output_tokens", 0) for r in records)

        # Breakdown by component
        by_component: dict[str, dict] = {}
        for record in records:
            comp = record.get("component", "unknown")
            if comp not in by_component:
                by_component[comp] = {
                    "component": comp,
                    "calls": 0,
                    "cost_usd": 0.0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                }
            by_component[comp]["calls"] += 1
            by_component[comp]["cost_usd"] += record.get("cost_usd", 0.0)
            by_component[comp]["input_tokens"] += record.get("input_tokens", 0)
            by_component[comp]["output_tokens"] += record.get("output_tokens", 0)

        result: dict[str, Any] = {
            "total_calls": total_calls,
            "total_cost_usd": round(total_cost, 4),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "breakdown": sorted(by_component.values(), key=lambda x: x["cost_usd"], reverse=True),
        }
        if date:
            result["date"] = date
        return result

    def _load_records_for_prefix(self, prefix: str) -> list[dict]:
        """Load all cost records matching an S3 prefix."""
        records: list[dict] = []
        try:
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".json"):
                        try:
                            response = self._s3.get_object(Bucket=self.bucket, Key=key)
                            body = response["Body"].read().decode("utf-8")
                            records.append(json.loads(body))
                        except Exception as e:
                            logger.warning(f"Failed to read cost record {key}: {e}")
        except Exception as e:
            logger.error(f"Failed to list cost records: {e}")
        return records


# Global singleton instance
_tracker: CostTracker | None = None


def get_cost_tracker() -> CostTracker:
    """Get the global CostTracker instance."""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker
