# Implementation Plan: Service Latency Optimization

## Overview

This plan implements 10 optimization areas to reduce end-to-end query pipeline latency by 40–70%. Tasks are organized by priority: Immediate (HTTP/connection fixes), Medium (caching, LLM prompt reduction), and High Impact (service merge, streaming, semantic caching). Each task builds incrementally on previous steps and includes property-based tests using Hypothesis for the 10 correctness properties defined in the design.

## Tasks

- [ ] 1. HTTP timeout reduction and connection pooling in `nlp_api.py`
  - [x] 1.1 Implement shared connection pool with `httpx.AsyncClient` at module level
    - Create a module-level `httpx.AsyncClient` with `httpx.Limits(max_keepalive_connections=10, max_connections=20)`
    - Initialize the pool eagerly on FastAPI `startup` event, close on `shutdown` event
    - Add `get_http_pool() -> httpx.AsyncClient` accessor function
    - Replace all per-request `async with httpx.AsyncClient(...)` blocks in `query_endpoint` with the shared pool
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 1.2 Configure per-service timeout values
    - Set orchestrator call timeout to 45 seconds
    - Set guardrail/viz call timeout to 60 seconds (merged service)
    - Set total pipeline timeout cap to 135 seconds
    - Add timeout constants to `src/config.py` for configurability
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [ ]* 1.3 Write unit tests for connection pool configuration and timeout values
    - Test that pool has `max_keepalive_connections=10` and `max_connections=20`
    - Test that per-service timeouts are applied correctly (45s, 60s)
    - Test pool lifecycle: startup initializes, shutdown closes cleanly
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [ ] 2. Implement S3 file-level caching in `spoke_agent.py`
  - [ ] 2.1 Create `S3Cache` class with LRU eviction and TTL
    - Implement `S3Cache` class with `max_size` and `ttl_seconds=300` parameters
    - Implement `get(key: str) -> bytes | None` that checks TTL before returning
    - Implement `put(key: str, content: bytes) -> None` with LRU eviction at capacity
    - Implement stale-on-error fallback: return expired content on S3 fetch failure with logged warning
    - Use `S3CacheEntry` dataclass with `content`, `cached_at` (monotonic), and `s3_key` fields
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 2.2 Write property test: S3 cache TTL correctness (Property 1)
    - **Property 1: S3 cache TTL correctness**
    - Generate random keys/values and time offsets (0–600s)
    - Verify `get()` returns content iff entry stored < 300s ago; entries ≥ 300s are misses
    - **Validates: Requirements 5.1, 5.2, 5.3**

  - [ ]* 2.3 Write property test: S3 cache LRU eviction order (Property 2)
    - **Property 2: S3 cache LRU eviction order**
    - Generate random sequences of put/get operations exceeding cache capacity
    - Verify the evicted entry is always the least recently used (oldest access time)
    - **Validates: Requirements 5.4**

  - [ ]* 2.4 Write property test: S3 cache stale-on-error fallback (Property 3)
    - **Property 3: S3 cache stale-on-error fallback**
    - Generate random expired entries and simulate S3 fetch failure
    - Verify stale content is returned rather than raising an error
    - **Validates: Requirements 5.5**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Normalize cache parameters in `result_cache.py`
  - [ ] 4.1 Update `ResultCache.generate_key()` to exclude volatile fields
    - Modify key computation to exclude `timestamp`, `query_id`, `correlation_id`, and `source` from routing_metadata
    - Normalize `query_text` in routing_metadata: strip whitespace, convert to lowercase
    - Sort `entity_refs` before hashing
    - Include only `query_type`, sorted `entity_refs`, and normalized `query_text` in the key
    - _Requirements: 9.1, 9.2, 9.3_

  - [ ]* 4.2 Write property test: Volatile field exclusion (Property 4)
    - **Property 4: Normalized cache key volatile field exclusion**
    - Generate random StructuredIntent pairs differing only in volatile fields (uuid timestamps, query_ids, correlation_ids, source)
    - Verify `generate_key()` produces identical keys for both
    - **Validates: Requirements 9.1, 9.2, 9.3**

  - [ ]* 4.3 Write property test: Text normalization (Property 5)
    - **Property 5: Normalized cache key text normalization**
    - Generate random query strings with injected leading/trailing whitespace and casing variations
    - Verify normalized cache key is identical for semantically equivalent queries
    - **Validates: Requirements 9.2, 9.3**

- [ ] 5. Reduce LLM prompt size in `nlp_translator.py`
  - [ ] 5.1 Cap `_build_ontology_context()` output to 5 concepts maximum
    - Modify `_build_ontology_context()` to accept a relevance scoring function
    - Score concepts by keyword match relevance (count of matching keywords from query)
    - Sort by score descending, truncate to top 5
    - Return only the 5 most relevant concepts in the prompt context
    - _Requirements: 4.1, 4.2_

  - [ ]* 5.2 Write property test: Ontology context capped at 5 concepts (Property 7)
    - **Property 7: Ontology context capped at 5 concepts**
    - Generate random concept lists of length 1–50 with random relevance scores
    - Verify output always has ≤ 5 concepts and they are the top-scored ones
    - **Validates: Requirements 4.1, 4.2**

- [ ] 6. Expand direct dispatch in `orchestrator_hub.py`
  - [ ] 6.1 Update `process_intent()` routing logic for direct dispatch
    - Change condition: direct dispatch for `query_type in ("lookup", "aggregation")` regardless of resolved agent count
    - Only route through LLM agent for `query_type == "comparison"` with multiple agents
    - Keep single-agent comparison queries on direct dispatch path
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 6.2 Write property test: Direct dispatch for non-comparison queries (Property 8)
    - **Property 8: Direct dispatch for non-comparison queries**
    - Generate random intents with `query_type` ∈ {"lookup", "aggregation"} and varying agent counts
    - Verify the LLM routing agent is never invoked (direct dispatch path taken)
    - **Validates: Requirements 7.1, 7.2**

  - [ ]* 6.3 Write property test: LLM routing for comparison queries (Property 9)
    - **Property 9: LLM routing for comparison queries**
    - Generate random intents with `query_type == "comparison"` and 2+ resolved agents
    - Verify the LLM routing agent is invoked for multi-agent coordination
    - **Validates: Requirements 7.3**

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement pre-warm data on startup
  - [ ] 8.1 Add pre-warming logic to orchestrator startup
    - Add a configurable list of frequently accessed S3 file keys (in `src/config.py`)
    - Implement `pre_warm(keys: list[str]) -> None` method on `S3Cache`
    - Call `pre_warm()` during orchestrator startup (FastAPI `startup` event or module init)
    - Enforce 10-second timeout for pre-warming; continue on partial failure with logged warnings
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 8.2 Write unit tests for pre-warming
    - Test that configured files are loaded into cache on startup
    - Test that partial failure (one file fails) doesn't block remaining files
    - Test that pre-warming completes within 10 seconds
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 9. Create merged Guardrail + Visualization service (`guardrail_viz_api.py`)
  - [ ] 9.1 Create `guardrail_viz_api.py` with combined endpoint
    - Create new file `src/services/guardrail_viz_api.py`
    - Implement `POST /internal/validate-and-render` endpoint
    - Define `ValidateAndRenderRequest` and `ValidateAndRenderResponse` Pydantic models
    - Import and reuse existing guardrail validation logic from `guardrail_layer.py`
    - Import and reuse existing visualization rendering logic from `visualization_renderer.py`
    - Flow: validate → if pass → render → return; if reject → return rejection immediately
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 9.2 Write property test: Guardrail rejection short-circuits rendering (Property 10)
    - **Property 10: Guardrail rejection short-circuits rendering**
    - Generate random orchestrator responses that fail guardrail validation
    - Verify the visualization renderer is never invoked when guardrail rejects
    - **Validates: Requirements 3.5**

  - [ ] 9.3 Update `nlp_api.py` to call merged service instead of separate Guardrail and Visualization
    - Replace the two sequential calls (Guardrail then Visualization) with a single call to `/internal/validate-and-render`
    - Use the 60-second timeout for the merged service call
    - Remove the separate 15-second guardrail timeout constant (no longer needed as separate call)
    - Update URL configuration in `src/config.py` to point to merged service
    - _Requirements: 3.2, 1.3_

  - [ ]* 9.4 Write unit tests for merged service endpoint
    - Test validate-then-render happy path
    - Test rejection returns immediately without rendering
    - Test that all existing guardrail policy rules are preserved
    - Test that all existing chart generation behavior is preserved
    - _Requirements: 3.1, 3.3, 3.4, 3.5_

- [ ] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implement SSE streaming for visualization responses
  - [ ] 11.1 Add SSE streaming support to `guardrail_viz_api.py`
    - Stream LLM-generated chart configuration chunks as they become available
    - Use `event: chunk` for partial chart config data
    - Send `event: metadata` with latency breakdown after all chunks delivered
    - Send `event: error` if streaming is interrupted with partial response indication
    - _Requirements: 8.1, 8.3, 8.4_

  - [ ] 11.2 Update `nlp_api.py` to forward SSE stream to client
    - Add SSE response forwarding using `StreamingResponse` from FastAPI
    - Forward `event: chunk`, `event: metadata`, and `event: error` events to client
    - Handle stream interruption gracefully with partial response indication
    - _Requirements: 8.2, 8.3, 8.4_

  - [ ]* 11.3 Write unit tests for SSE event format and streaming
    - Test `event: chunk` format and progressive delivery
    - Test `event: metadata` contains latency breakdown
    - Test `event: error` on stream interruption
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 12. Implement semantic similarity caching in `result_cache.py`
  - [ ] 12.1 Create `SemanticCache` class with embedding-based matching
    - Implement `SemanticCache` class with `similarity_threshold=0.85`
    - Implement `find_similar(query_text: str) -> CachedResult | None` using cosine similarity
    - Implement `store(query_text: str, embedding: list[float], result: OrchestratorResponse) -> None`
    - Use `SemanticCacheEntry` dataclass with `query_text`, `embedding`, `result`, `stored_at`
    - Log match score and original cached query on cache hit for observability
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 12.2 Write property test: Semantic cache threshold correctness (Property 6)
    - **Property 6: Semantic cache threshold correctness**
    - Generate random embedding vector pairs with known cosine similarity values
    - Verify cache returns result iff maximum cosine similarity ≥ 0.85; below threshold always misses
    - **Validates: Requirements 10.1, 10.2**

  - [ ]* 12.3 Write unit tests for semantic cache
    - Test cache stores and retrieves by embedding similarity
    - Test match score logging on hit
    - Test cache miss when below threshold
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis (already in the project)
- Unit tests validate specific examples and edge cases
- The implementation language is Python, matching the existing codebase and design document
- All 10 correctness properties from the design are covered by property-based test tasks
