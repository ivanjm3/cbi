"""Generic LRU Cache utility using OrderedDict."""

from collections import OrderedDict
from typing import TypeVar, Generic, Optional

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """Least Recently Used cache with configurable max size.

    Uses OrderedDict to track access order. Most recently accessed
    entries are at the end; least recently accessed are at the front
    and evicted first when the cache exceeds max_size.
    """

    def __init__(self, max_size: int = 1000) -> None:
        if max_size < 1:
            raise ValueError("max_size must be at least 1")
        self._max_size = max_size
        self._store: OrderedDict = OrderedDict()

    def get(self, key: K) -> Optional[V]:
        """Retrieve a value by key, marking it as most recently used.

        Returns None if the key is not present.
        """
        if key in self._store:
            self._store.move_to_end(key)
            return self._store[key]
        return None

    def put(self, key: K, value: V) -> None:
        """Insert or update a key-value pair.

        If the key already exists, its value is updated and it becomes
        most recently used. If inserting causes the cache to exceed
        max_size, the least recently used entry is evicted.
        """
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    @property
    def size(self) -> int:
        """Return the current number of entries in the cache."""
        return len(self._store)

    def clear(self) -> None:
        """Remove all entries from the cache."""
        self._store.clear()
