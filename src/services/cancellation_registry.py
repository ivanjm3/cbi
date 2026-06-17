"""Cooperative cancellation registry for query cancellation propagation.

Provides an in-memory, thread-safe store of cancelled correlation IDs.
Each backend service instantiates its own CancellationRegistry to track
which queries have been cancelled and should stop processing.
"""

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional


@dataclass
class CancellationEntry:
    """A single cancellation record.

    Attributes:
        correlation_id: The unique query identifier that was cancelled.
        registered_at: Monotonic timestamp when cancellation was registered.
        source: Origin of the cancellation — "disconnect", "explicit", or "propagated".
    """

    correlation_id: str
    registered_at: float
    source: str


class CancellationRegistry:
    """Thread-safe in-memory cancellation token store.

    Supports TTL-based expiry, max capacity eviction (oldest-first),
    and O(1) lookups. Used by each service to track cancelled queries
    so that downstream processing can be terminated cooperatively.
    """

    def __init__(self, ttl_seconds: float = 300.0, max_entries: int = 1000) -> None:
        """Initialize the registry.

        Args:
            ttl_seconds: Time-to-live for entries before automatic expiry.
                         Defaults to 300 seconds (5 minutes).
            max_entries: Maximum number of concurrent cancellation records.
                         When exceeded, the oldest entries are evicted first.
                         Defaults to 1000.
        """
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._entries: OrderedDict[str, CancellationEntry] = OrderedDict()
        self._lock = threading.Lock()

    def register(self, correlation_id: str, source: str = "explicit") -> None:
        """Mark a correlation ID as cancelled.

        If the registry is at max capacity, the oldest entry is evicted
        before the new one is inserted.

        Args:
            correlation_id: The query identifier to cancel.
            source: Origin of cancellation — "disconnect", "explicit", or "propagated".
        """
        with self._lock:
            # If already registered, move to end (refresh)
            if correlation_id in self._entries:
                self._entries.move_to_end(correlation_id)
                self._entries[correlation_id] = CancellationEntry(
                    correlation_id=correlation_id,
                    registered_at=time.monotonic(),
                    source=source,
                )
                return

            # Evict oldest entries if at capacity
            while len(self._entries) >= self._max_entries:
                self._entries.popitem(last=False)

            self._entries[correlation_id] = CancellationEntry(
                correlation_id=correlation_id,
                registered_at=time.monotonic(),
                source=source,
            )

    def is_cancelled(self, correlation_id: str) -> bool:
        """Check if a correlation ID is marked as cancelled.

        O(1) lookup. Returns False for unknown or expired IDs.

        Args:
            correlation_id: The query identifier to check.

        Returns:
            True if the correlation ID is in the registry, False otherwise.
        """
        with self._lock:
            return correlation_id in self._entries

    def remove(self, correlation_id: str) -> None:
        """Explicitly remove a cancellation entry.

        Called when a query completes normally to free the entry
        without waiting for TTL expiry.

        Args:
            correlation_id: The query identifier to remove.
        """
        with self._lock:
            self._entries.pop(correlation_id, None)

    def cleanup(self) -> int:
        """Remove all entries that have exceeded their TTL.

        Returns:
            The number of entries removed.
        """
        now = time.monotonic()
        removed = 0
        with self._lock:
            # Iterate oldest-first; since OrderedDict preserves insertion
            # order, we can stop early once we hit a non-expired entry.
            expired_ids = []
            for cid, entry in self._entries.items():
                if now - entry.registered_at >= self._ttl_seconds:
                    expired_ids.append(cid)
                else:
                    # All subsequent entries are newer, so stop checking
                    break
            for cid in expired_ids:
                del self._entries[cid]
                removed += 1
        return removed

    @property
    def size(self) -> int:
        """Current number of entries in the registry."""
        with self._lock:
            return len(self._entries)

    def get_entry(self, correlation_id: str) -> Optional[CancellationEntry]:
        """Retrieve the full cancellation entry for a correlation ID.

        Args:
            correlation_id: The query identifier to look up.

        Returns:
            The CancellationEntry if found, None otherwise.
        """
        with self._lock:
            return self._entries.get(correlation_id)
