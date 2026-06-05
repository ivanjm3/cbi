"""Cost Tracker for all AWS service usage — S3-backed.

Tracks costs across all AWS services used by the project:
- Bedrock model invocations (input/output tokens)
- Bedrock Guardrails (per text unit)
- S3 operations (PUT, GET, LIST requests + storage)

Stores records as JSON objects in S3, organized by date for efficient querying.

S3 structure:
  s3://visualization-poc-bucket/costs/{YYYY-MM-DD}/{uuid}.json

Pricing:
- Claude Haiku: $0.25/$1.25 per 1M input/output tokens
- Claude 3.5 Haiku: $0.80/$4.00 per 1M input/output tokens
- Claude Sonnet 4: $3.00/$15.00 per 1M input/output tokens
- Titan Embeddings V2: $0.02 per 1M tokens
- Bedrock Guardrails: $0.75 per 1,000 text units (1 text unit = 1,000 chars)
- S3 Standard: $0.005 per 1,000 PUT/POST, $0.0004 per 1,000 GET, $0.023/GB-month storage
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.config import S3_BUCKET, S3_COSTS_PREFIX, get_s3_client

logger = logging.getLogger(__name__)

# Bedrock LLM pricing (per 1M tokens)
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

# Bedrock Guardrails pricing
GUARDRAIL_PRICE_PER_1K_TEXT_UNITS = 0.75  # $0.75 per 1,000 text units
GUARDRAIL_TEXT_UNIT_CHARS = 1000  # 1 text unit = 1,000 characters

# S3 pricing (us-east-1 Standard)
S3_PUT_PER_1K = 0.005       # $0.005 per 1,000 PUT/POST/COPY/LIST requests
S3_GET_PER_1K = 0.0004      # $0.0004 per 1,000 GET/SELECT requests
S3_STORAGE_PER_GB_MONTH = 0.023  # $0.023 per GB-month (first 50TB)


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
        self._write_record(
            service="bedrock_llm",
            component=component,
            cost_usd=cost,
            correlation_id=correlation_id,
            details={
                "model_id": model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            },
            metadata=metadata,
        )

    def log_guardrail_invocation(
        self,
        component: str,
        text_length_chars: int,
        action: str = "NONE",
        correlation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log a Bedrock Guardrails ApplyGuardrail invocation.

        Pricing: $0.75 per 1,000 text units (1 text unit = 1,000 characters).

        Args:
            component: Which component triggered the guardrail.
            text_length_chars: Length of text evaluated (in characters).
            action: Guardrail action result (NONE, GUARDRAIL_INTERVENED).
            correlation_id: Request correlation ID.
            metadata: Optional additional metadata.
        """
        text_units = max(1, text_length_chars / GUARDRAIL_TEXT_UNIT_CHARS)
        cost = (text_units / 1000) * GUARDRAIL_PRICE_PER_1K_TEXT_UNITS
        self._write_record(
            service="bedrock_guardrails",
            component=component,
            cost_usd=cost,
            correlation_id=correlation_id,
            details={
                "text_length_chars": text_length_chars,
                "text_units": round(text_units, 2),
                "action": action,
            },
            metadata=metadata,
        )

    def log_s3_operation(
        self,
        operation: str,
        component: str,
        object_size_bytes: int = 0,
        correlation_id: str | None = None,
    ) -> None:
        """Log an S3 API operation.

        Pricing:
        - PUT/POST/COPY/LIST: $0.005 per 1,000 requests
        - GET/SELECT: $0.0004 per 1,000 requests
        - Storage: $0.023 per GB-month (tracked separately)

        Args:
            operation: One of 'PUT', 'GET', 'LIST'.
            component: Which component made the S3 call.
            object_size_bytes: Size of object involved (for storage tracking).
            correlation_id: Request correlation ID.
        """
        op_upper = operation.upper()
        if op_upper in ("PUT", "POST", "COPY", "LIST"):
            cost = S3_PUT_PER_1K / 1000  # cost per single request
        elif op_upper in ("GET", "SELECT"):
            cost = S3_GET_PER_1K / 1000
        else:
            cost = 0.0

        self._write_record(
            service="s3",
            component=component,
            cost_usd=cost,
            correlation_id=correlation_id,
            details={
                "operation": op_upper,
                "object_size_bytes": object_size_bytes,
            },
        )

    def _write_record(
        self,
        service: str,
        component: str,
        cost_usd: float,
        correlation_id: str | None = None,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Write a cost record to S3.

        Args:
            service: AWS service name (bedrock_llm, bedrock_guardrails, s3).
            component: Application component that incurred the cost.
            cost_usd: Estimated cost in USD.
            correlation_id: Request correlation ID.
            details: Service-specific details.
            metadata: Optional additional metadata.
        """
        now = datetime.now(timezone.utc)
        record_id = str(uuid.uuid4())
        date_str = now.date().isoformat()

        record = {
            "id": record_id,
            "timestamp": now.isoformat(),
            "service": service,
            "component": component,
            "cost_usd": cost_usd,
            "correlation_id": correlation_id,
            "details": details or {},
            "metadata": metadata,
            # Legacy fields for backward compat with existing reports
            "model_id": (details or {}).get("model_id", ""),
            "input_tokens": (details or {}).get("input_tokens", 0),
            "output_tokens": (details or {}).get("output_tokens", 0),
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

        # Breakdown by service
        by_service: dict[str, dict] = {}
        for record in records:
            service = record.get("service", "bedrock_llm")  # legacy records default to bedrock_llm
            if service not in by_service:
                by_service[service] = {"service": service, "calls": 0, "cost_usd": 0.0}
            by_service[service]["calls"] += 1
            by_service[service]["cost_usd"] += record.get("cost_usd", 0.0)

        result: dict[str, Any] = {
            "total_calls": total_calls,
            "total_cost_usd": round(total_cost, 6),
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "breakdown": sorted(by_component.values(), key=lambda x: x["cost_usd"], reverse=True),
            "by_service": sorted(by_service.values(), key=lambda x: x["cost_usd"], reverse=True),
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
