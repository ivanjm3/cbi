"""Result Cache service for the Orchestrator Hub.
Provides an in-memory cache that stores previous query results keyed by
a deterministic hash of the structured intent fields, avoiding redundant
agent invocations for identical queries.
Phase 1: Uses a Python dict as backend with no TTL management.
Cache is cleared on process restart.
"""

import hashlib
from typing import Any
from src.models.shared import OrchestratorResponse, StructuredIntent


class ResultCache:
    """In-memory result cache keyed by deterministic intent hashes.
    The cache key is generated from the query_type, sorted entity_refs,
    and sorted routing_metadata items to ensure identical intents always
    produce the same key regardless of field ordering.
    """

    def __init__(self) -> None:
        self._store: dict[str, OrchestratorResponse] = {}

    @staticmethod
    def generate_key(intent: StructuredIntent) -> str:
        """Generate a deterministic cache key from a StructuredIntent.
        The key is a SHA-256 hash of the tuple:
            (query_type, sorted(entity_refs), sorted(routing_metadata.items()))
        This ensures that two intents with the same semantic content produce
        the same key regardless of list or dict ordering.
        Args:
            intent: The structured intent to generate a key for.
        Returns:
            A hex string representing the deterministic hash.
        """
        key_parts = (
            intent.query_type,
            tuple(sorted(intent.entity_refs)),
            tuple(sorted(_flatten_metadata(intent.routing_metadata).items())),
        )
        key_string = repr(key_parts)
        return hashlib.sha256(key_string.encode("utf-8")).hexdigest()

    def get(self, intent_key: str) -> OrchestratorResponse | None:
        """Retrieve a cached response by intent key.
        Args:
            intent_key: The deterministic hash key for the intent.
        Returns:
            The cached OrchestratorResponse if found, otherwise None.
        """
        return self._store.get(intent_key)

    def put(self, intent_key: str, response: OrchestratorResponse) -> None:
        """Store a response in the cache.
        Args:
            intent_key: The deterministic hash key for the intent.
            response: The orchestrator response to cache.
        """
        self._store[intent_key] = response

    def invalidate(self, intent_key: str) -> None:
        """Remove a specific entry from the cache.
        Args:
            intent_key: The deterministic hash key to invalidate.
        """
        self._store.pop(intent_key, None)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._store.clear()

    @property
    def size(self) -> int:
        """Return the number of entries currently in the cache."""
        return len(self._store)


def _flatten_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Flatten metadata values to strings for deterministic hashing.
    Converts all values to their string representation to ensure
    consistent ordering and hashing regardless of value types.
    Args:
        metadata: The routing_metadata dict from a StructuredIntent.
    Returns:
        A dict with all values converted to strings.
    """
    return {str(k): repr(v) for k, v in metadata.items()}
