"""
Global Query Cache Layer

Provides Redis-backed caching for query results to enable:
1. Cross-session result sharing (same query = same result)
2. Fast repeated queries (reduce orchestrator/renderer overhead)
3. Configurable TTL for cache expiration

Requirement #3: Global vs session-based caching

Usage:
    cache = GlobalQueryCache()
    cached_result = cache.get(query, context)
    if cached_result:
        return cached_result
    
    # ... execute query ...
    cache.set(query, context, result)
"""

import hashlib
import json
import logging
from typing import Any, Dict, Optional

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

logger = logging.getLogger(__name__)


class GlobalQueryCache:
    """
    Redis-backed cache for query results.
    
    Attributes:
        ttl: Time-to-live for cache entries in seconds (default: 3600 = 1 hour)
        redis_url: Redis connection URL (default: redis://localhost:6379)
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        ttl: int = 3600,
        enabled: bool = True,
    ):
        """
        Initialize cache layer.
        
        Args:
            redis_url: Redis connection URL
            ttl: Cache entry TTL in seconds
            enabled: Whether caching is enabled (can be disabled for testing)
        """
        self.ttl = ttl
        self.enabled = enabled
        self.redis_url = redis_url
        self.redis_client: Optional[Any] = None

        if not HAS_REDIS:
            logger.warning("redis not installed. Caching disabled.")
            self.enabled = False
            return

        if not self.enabled:
            logger.info("Query caching disabled.")
            return

        try:
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Query cache initialized (TTL: {ttl}s)")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Caching disabled.")
            self.enabled = False
            self.redis_client = None

    def _hash_query(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Hash query + context into deterministic cache key.
        
        The hash includes the query text and context metadata (but not results)
        to ensure identical queries with identical context hit the cache.
        
        Args:
            query: User's query text
            context: Context dict with keys like data_sources, user_id, etc.
        
        Returns:
            SHA256 hex digest for use as cache key
        """
        # Normalize context (exclude None values, sort keys)
        if context is None:
            context = {}
        normalized_context = {k: v for k, v in context.items() if v is not None}

        # Combine and hash
        combined = json.dumps(
            {
                "query": query.strip().lower(),  # Normalize query text
                "context": normalized_context,
            },
            sort_keys=True,
        )
        return hashlib.sha256(combined.encode()).hexdigest()

    def get(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached query result if it exists and is valid.
        
        Args:
            query: User's query text
            context: Context dict with keys like data_sources
        
        Returns:
            Cached result dict, or None if not found/caching disabled
        """
        if not self.enabled or not self.redis_client:
            return None

        try:
            cache_key = f"cbi:query:{self._hash_query(query, context)}"
            cached = self.redis_client.get(cache_key)

            if cached:
                logger.debug(f"Cache HIT for: {query[:50]}...")
                return json.loads(cached)
            else:
                logger.debug(f"Cache MISS for: {query[:50]}...")
                return None

        except Exception as e:
            logger.warning(f"Cache get() failed: {e}")
            return None

    def set(
        self,
        query: str,
        context: Optional[Dict[str, Any]],
        result: Dict[str, Any],
    ) -> bool:
        """
        Store query result in global cache.
        
        Args:
            query: User's query text
            context: Context dict
            result: Result dict to cache (will be JSON-serialized)
        
        Returns:
            True if successfully cached, False otherwise
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            cache_key = f"cbi:query:{self._hash_query(query, context)}"

            # Serialize result, handling non-JSON-serializable types
            serialized = json.dumps(result, default=str, allow_nan=False)

            # Store with TTL
            self.redis_client.setex(
                cache_key,
                self.ttl,
                serialized,
            )
            logger.debug(f"Cache SET for: {query[:50]}... (TTL: {self.ttl}s)")
            return True

        except Exception as e:
            logger.warning(f"Cache set() failed: {e}")
            return False

    def delete(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Remove specific query from cache.
        
        Args:
            query: User's query text
            context: Context dict
        
        Returns:
            True if deleted, False if not found or error
        """
        if not self.enabled or not self.redis_client:
            return False

        try:
            cache_key = f"cbi:query:{self._hash_query(query, context)}"
            result = self.redis_client.delete(cache_key)
            logger.debug(f"Cache DELETE: {query[:50]}...")
            return result > 0

        except Exception as e:
            logger.warning(f"Cache delete() failed: {e}")
            return False

    def clear_all(self, pattern: str = "cbi:query:*") -> int:
        """
        Clear all CBI cache entries (dangerous - use with caution).
        
        Args:
            pattern: Glob pattern for keys to delete (default: all CBI queries)
        
        Returns:
            Number of keys deleted
        """
        if not self.enabled or not self.redis_client:
            return 0

        try:
            deleted_count = 0
            for key in self.redis_client.scan_iter(pattern):
                self.redis_client.delete(key)
                deleted_count += 1

            logger.info(f"Cache CLEAR: Deleted {deleted_count} keys matching '{pattern}'")
            return deleted_count

        except Exception as e:
            logger.warning(f"Cache clear_all() failed: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics (for monitoring/debugging).
        
        Returns:
            Dict with info, memory usage, key count
        """
        if not self.enabled or not self.redis_client:
            return {"enabled": False}

        try:
            info = self.redis_client.info()
            key_count = self.redis_client.dbsize()

            return {
                "enabled": True,
                "connected": True,
                "memory_used_mb": info.get("used_memory_human", "N/A"),
                "key_count": key_count,
                "ttl_seconds": self.ttl,
            }
        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {"enabled": True, "connected": False, "error": str(e)}


# Global singleton instance (initialize in main app startup)
_cache_instance: Optional[GlobalQueryCache] = None


def get_cache() -> GlobalQueryCache:
    """Get or create global cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = GlobalQueryCache()
    return _cache_instance


def init_cache(redis_url: str = "redis://localhost:6379", ttl: int = 3600) -> GlobalQueryCache:
    """Initialize global cache instance with custom settings."""
    global _cache_instance
    _cache_instance = GlobalQueryCache(redis_url=redis_url, ttl=ttl)
    return _cache_instance
