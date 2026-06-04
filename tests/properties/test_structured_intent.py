"""Property tests for StructuredIntent model validation.

Property 1: Structured Intent Completeness
- Verify that any StructuredIntent instance always contains:
  - A valid UUID query_id
  - Exactly one valid query_type from {lookup, aggregation, comparison}
  - Non-empty entity_refs list of strings
  - routing_metadata dict
  - A timestamp (datetime)

Validates: Requirements 2.1, 2.3
"""

from datetime import datetime, timezone
from uuid import UUID

import pytest
from hypothesis import given, HealthCheck, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from src.models.shared import StructuredIntent


# --- Strategies ---

valid_query_types = st.sampled_from(["lookup", "aggregation", "comparison"])

entity_ref_text = st.from_regex(r"ontology:[a-z_]{1,30}", fullmatch=True)

non_empty_entity_refs = st.lists(entity_ref_text, min_size=1, max_size=10)

routing_metadata_strategy = st.fixed_dictionaries(
    {},
    optional={
        "preferred_agent": st.text(min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz_-"),
        "source": st.sampled_from(["history_bias", "ontology_match", "default"]),
    },
)

timestamp_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
    timezones=st.just(timezone.utc),
)

valid_structured_intent_strategy = st.builds(
    dict,
    query_id=st.uuids(),
    query_type=valid_query_types,
    entity_refs=non_empty_entity_refs,
    routing_metadata=routing_metadata_strategy,
    timestamp=timestamp_strategy,
)


# --- Property Tests ---


class TestStructuredIntentCompleteness:
    """Property 1: Structured Intent Completeness.

    For any valid StructuredIntent, it always contains a valid UUID query_id,
    exactly one valid query_type, non-empty entity_refs, routing_metadata,
    and a timestamp.
    """

    @given(data=valid_structured_intent_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_intent_has_uuid_query_id(self, data: dict) -> None:
        """Any valid StructuredIntent has a proper UUID query_id."""
        intent = StructuredIntent(**data)
        assert isinstance(intent.query_id, UUID)

    @given(data=valid_structured_intent_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_intent_has_valid_query_type(self, data: dict) -> None:
        """query_type is exactly one of the allowed literal values."""
        intent = StructuredIntent(**data)
        assert intent.query_type in {"lookup", "aggregation", "comparison"}

    @given(data=valid_structured_intent_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_intent_has_non_empty_entity_refs(self, data: dict) -> None:
        """entity_refs is always a non-empty list of strings."""
        intent = StructuredIntent(**data)
        assert isinstance(intent.entity_refs, list)
        assert len(intent.entity_refs) >= 1
        assert all(isinstance(ref, str) for ref in intent.entity_refs)

    @given(data=valid_structured_intent_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_intent_has_routing_metadata(self, data: dict) -> None:
        """routing_metadata is always a dict."""
        intent = StructuredIntent(**data)
        assert isinstance(intent.routing_metadata, dict)

    @given(data=valid_structured_intent_strategy)
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_valid_intent_has_timestamp(self, data: dict) -> None:
        """timestamp is always a datetime instance."""
        intent = StructuredIntent(**data)
        assert isinstance(intent.timestamp, datetime)

    @given(
        query_id=st.uuids(),
        query_type=valid_query_types,
        entity_refs=non_empty_entity_refs,
        routing_metadata=routing_metadata_strategy,
        timestamp=timestamp_strategy,
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_all_fields_present_simultaneously(
        self,
        query_id: UUID,
        query_type: str,
        entity_refs: list[str],
        routing_metadata: dict,
        timestamp: datetime,
    ) -> None:
        """All required fields are present and correct in every instance."""
        intent = StructuredIntent(
            query_id=query_id,
            query_type=query_type,
            entity_refs=entity_refs,
            routing_metadata=routing_metadata,
            timestamp=timestamp,
        )
        assert isinstance(intent.query_id, UUID)
        assert intent.query_type in {"lookup", "aggregation", "comparison"}
        assert len(intent.entity_refs) >= 1
        assert isinstance(intent.routing_metadata, dict)
        assert isinstance(intent.timestamp, datetime)


class TestStructuredIntentRejection:
    """Verify the model rejects invalid inputs to guarantee completeness."""

    def test_rejects_empty_entity_refs(self) -> None:
        """StructuredIntent must reject empty entity_refs."""
        with pytest.raises(ValidationError):
            StructuredIntent(
                query_id="550e8400-e29b-41d4-a716-446655440000",
                query_type="lookup",
                entity_refs=[],
                routing_metadata={},
                timestamp=datetime.now(tz=timezone.utc),
            )

    @given(invalid_type=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz").filter(lambda s: s not in {"lookup", "aggregation", "comparison"}))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_rejects_invalid_query_type(self, invalid_type: str) -> None:
        """StructuredIntent must reject query_type not in the allowed set."""
        with pytest.raises(ValidationError):
            StructuredIntent(
                query_id="550e8400-e29b-41d4-a716-446655440000",
                query_type=invalid_type,
                entity_refs=["ontology:concept_a"],
                routing_metadata={},
                timestamp=datetime.now(tz=timezone.utc),
            )

    def test_rejects_missing_query_id(self) -> None:
        """StructuredIntent must reject construction without query_id."""
        with pytest.raises(ValidationError):
            StructuredIntent(
                query_type="lookup",
                entity_refs=["ontology:concept_a"],
                routing_metadata={},
                timestamp=datetime.now(tz=timezone.utc),
            )

    def test_rejects_missing_timestamp(self) -> None:
        """StructuredIntent must reject construction without timestamp."""
        with pytest.raises(ValidationError):
            StructuredIntent(
                query_id="550e8400-e29b-41d4-a716-446655440000",
                query_type="lookup",
                entity_refs=["ontology:concept_a"],
                routing_metadata={},
            )

    def test_rejects_invalid_uuid(self) -> None:
        """StructuredIntent must reject an invalid UUID string."""
        with pytest.raises(ValidationError):
            StructuredIntent(
                query_id="not-a-valid-uuid",
                query_type="lookup",
                entity_refs=["ontology:concept_a"],
                routing_metadata={},
                timestamp=datetime.now(tz=timezone.utc),
            )

    def test_rejects_missing_routing_metadata(self) -> None:
        """StructuredIntent must reject construction without routing_metadata."""
        with pytest.raises(ValidationError):
            StructuredIntent(
                query_id="550e8400-e29b-41d4-a716-446655440000",
                query_type="lookup",
                entity_refs=["ontology:concept_a"],
                timestamp=datetime.now(tz=timezone.utc),
            )
