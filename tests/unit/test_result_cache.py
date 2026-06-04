"""Unit tests for the ResultCache service."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.models.shared import AgentResult, OrchestratorResponse, StructuredIntent
from src.services.result_cache import ResultCache


@pytest.fixture
def cache() -> ResultCache:
    return ResultCache()


@pytest.fixture
def sample_intent() -> StructuredIntent:
    return StructuredIntent(
        query_id=uuid4(),
        query_type="lookup",
        entity_refs=["ontology:sales_revenue", "ontology:quarterly_report"],
        routing_metadata={"preferred_agent": "spoke-agent-json"},
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_response() -> OrchestratorResponse:
    return OrchestratorResponse(
        query_id=uuid4(),
        results=[
            AgentResult(
                status="success",
                payload={"data": [1, 2, 3]},
                agent_id="spoke-agent-json",
                data_source="financial_data",
            )
        ],
        unavailable_agents=[],
    )


class TestResultCacheKeyGeneration:
    """Tests for deterministic cache key generation."""

    def test_same_intent_produces_same_key(self, sample_intent: StructuredIntent):
        key1 = ResultCache.generate_key(sample_intent)
        key2 = ResultCache.generate_key(sample_intent)
        assert key1 == key2

    def test_different_entity_ref_order_produces_same_key(self):
        intent1 = StructuredIntent(
            query_id=uuid4(),
            query_type="aggregation",
            entity_refs=["ontology:b", "ontology:a"],
            routing_metadata={"source": "history"},
            timestamp=datetime.now(timezone.utc),
        )
        intent2 = StructuredIntent(
            query_id=uuid4(),
            query_type="aggregation",
            entity_refs=["ontology:a", "ontology:b"],
            routing_metadata={"source": "history"},
            timestamp=datetime.now(timezone.utc),
        )
        assert ResultCache.generate_key(intent1) == ResultCache.generate_key(intent2)

    def test_different_metadata_order_produces_same_key(self):
        intent1 = StructuredIntent(
            query_id=uuid4(),
            query_type="lookup",
            entity_refs=["ontology:x"],
            routing_metadata={"a": "1", "b": "2"},
            timestamp=datetime.now(timezone.utc),
        )
        intent2 = StructuredIntent(
            query_id=uuid4(),
            query_type="lookup",
            entity_refs=["ontology:x"],
            routing_metadata={"b": "2", "a": "1"},
            timestamp=datetime.now(timezone.utc),
        )
        assert ResultCache.generate_key(intent1) == ResultCache.generate_key(intent2)

    def test_different_query_type_produces_different_key(self):
        intent1 = StructuredIntent(
            query_id=uuid4(),
            query_type="lookup",
            entity_refs=["ontology:x"],
            routing_metadata={},
            timestamp=datetime.now(timezone.utc),
        )
        intent2 = StructuredIntent(
            query_id=uuid4(),
            query_type="aggregation",
            entity_refs=["ontology:x"],
            routing_metadata={},
            timestamp=datetime.now(timezone.utc),
        )
        assert ResultCache.generate_key(intent1) != ResultCache.generate_key(intent2)

    def test_different_entity_refs_produce_different_key(self):
        intent1 = StructuredIntent(
            query_id=uuid4(),
            query_type="lookup",
            entity_refs=["ontology:a"],
            routing_metadata={},
            timestamp=datetime.now(timezone.utc),
        )
        intent2 = StructuredIntent(
            query_id=uuid4(),
            query_type="lookup",
            entity_refs=["ontology:b"],
            routing_metadata={},
            timestamp=datetime.now(timezone.utc),
        )
        assert ResultCache.generate_key(intent1) != ResultCache.generate_key(intent2)

    def test_key_ignores_query_id_and_timestamp(self):
        """Key depends only on query_type, entity_refs, routing_metadata."""
        intent1 = StructuredIntent(
            query_id=uuid4(),
            query_type="comparison",
            entity_refs=["ontology:x"],
            routing_metadata={"key": "value"},
            timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        intent2 = StructuredIntent(
            query_id=uuid4(),
            query_type="comparison",
            entity_refs=["ontology:x"],
            routing_metadata={"key": "value"},
            timestamp=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        assert ResultCache.generate_key(intent1) == ResultCache.generate_key(intent2)


class TestResultCacheOperations:
    """Tests for cache get/put/invalidate/clear operations."""

    def test_get_returns_none_for_missing_key(self, cache: ResultCache):
        assert cache.get("nonexistent") is None

    def test_put_and_get(self, cache: ResultCache, sample_response: OrchestratorResponse):
        cache.put("key1", sample_response)
        result = cache.get("key1")
        assert result == sample_response

    def test_put_overwrites_existing(self, cache: ResultCache):
        response1 = OrchestratorResponse(
            query_id=uuid4(), results=[], unavailable_agents=[]
        )
        response2 = OrchestratorResponse(
            query_id=uuid4(), results=[], unavailable_agents=["agent-x"]
        )
        cache.put("key1", response1)
        cache.put("key1", response2)
        assert cache.get("key1") == response2

    def test_invalidate_removes_entry(self, cache: ResultCache, sample_response: OrchestratorResponse):
        cache.put("key1", sample_response)
        cache.invalidate("key1")
        assert cache.get("key1") is None

    def test_invalidate_nonexistent_key_is_safe(self, cache: ResultCache):
        cache.invalidate("nonexistent")  # Should not raise

    def test_clear_removes_all_entries(self, cache: ResultCache, sample_response: OrchestratorResponse):
        cache.put("key1", sample_response)
        cache.put("key2", sample_response)
        cache.clear()
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.size == 0

    def test_size_tracks_entries(self, cache: ResultCache, sample_response: OrchestratorResponse):
        assert cache.size == 0
        cache.put("key1", sample_response)
        assert cache.size == 1
        cache.put("key2", sample_response)
        assert cache.size == 2
        cache.invalidate("key1")
        assert cache.size == 1
