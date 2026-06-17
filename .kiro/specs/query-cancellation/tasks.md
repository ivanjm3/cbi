# Implementation Plan: Query Cancellation

## Overview

Implements cooperative query cancellation across the full service chain (Frontend → NLP API → Orchestrator Hub → Spoke Agents) using a correlation-ID-based cancellation token pattern. Backend components are built first (shared registry → NLP API → orchestrator → spoke agents), then frontend, then integration testing.

## Tasks

- [x] 1. Implement CancellationRegistry shared module
  - [x] 1.1 Create `src/services/cancellation_registry.py` with the `CancellationRegistry` class
    - Implement `__init__(ttl_seconds, max_entries)` with configurable TTL (default 300s) and max capacity (default 1000)
    - Implement `register(correlation_id)` to mark a correlation ID as cancelled with timestamp
    - Implement `is_cancelled(correlation_id)` for O(1) lookup returning bool
    - Implement `remove(correlation_id)` for explicit entry removal on query completion
    - Implement `cleanup()` to remove expired entries and return count removed
    - Implement `size` property for current entry count
    - Implement max capacity eviction (oldest-first) when registering beyond limit
    - Use `threading.Lock` for thread safety
    - Define `CancellationEntry` dataclass with `correlation_id`, `registered_at` (monotonic timestamp), and `source` field
    - _Requirements: 8.1, 8.2, 8.3, 9.1_

  - [ ]* 1.2 Write property tests for CancellationRegistry (Properties 1-5)
    - **Property 1: Registration makes cancellation detectable** — after `register(id)`, `is_cancelled(id)` returns True
    - **Property 2: Cancellation isolation** — registering cancellation for A does not affect `is_cancelled(B)`
    - **Property 3: TTL-based cleanup removes expired entries** — after TTL elapses and cleanup runs, entry is removed
    - **Property 4: Explicit removal clears entries** — after `remove(id)`, `is_cancelled(id)` returns False
    - **Property 5: Maximum capacity enforcement** — registry size never exceeds max_entries, oldest evicted first
    - **Validates: Requirements 8.1, 8.2, 8.3, 9.1, 3.1, 4.2, 5.2**

- [x] 2. Implement NLP API cancellation support
  - [x] 2.1 Add POST `/cancel` endpoint to `src/services/nlp_api.py`
    - Define `CancelRequest` model with `correlation_id: str`
    - Define `CancelResponse` model with `cancelled: bool`, `correlation_id: str`, `message: str`
    - Instantiate a module-level `CancellationRegistry` in nlp_api.py
    - Implement the endpoint: register the correlation ID, propagate to Orchestrator Hub via POST `/internal/cancel`, return 200 with confirmation
    - Return 200 with no-op acknowledgment if correlation ID is not active
    - Ensure response time stays under 50ms by making orchestrator propagation a background task
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 2.2 Add client disconnect detection to the `/query` endpoint in `src/services/nlp_api.py`
    - Add a background coroutine that polls `request.is_disconnected()` during the orchestrator call
    - When disconnect is detected, register the correlation ID in the local CancellationRegistry
    - Propagate cancellation to Orchestrator Hub via POST `/internal/cancel`
    - Cancel the in-progress `httpx` request to the orchestrator using `asyncio.Task.cancel()` or response stream abort
    - _Requirements: 3.1, 3.2, 3.3_

  - [ ]* 2.3 Write unit tests for NLP API cancel endpoint
    - Test POST `/cancel` with valid active correlation ID returns 200 with `cancelled: true`
    - Test POST `/cancel` with unknown correlation ID returns 200 with no-op acknowledgment
    - Test disconnect detection triggers cancellation registration
    - **Validates: Requirements 4.2, 4.3, 4.4, 3.1**

- [x] 3. Implement Orchestrator Hub cancellation support
  - [x] 3.1 Add POST `/internal/cancel` endpoint to `src/services/orchestrator_api.py`
    - Define `InternalCancelRequest` model with `correlation_id: str`
    - Define `InternalCancelResponse` model with `cancelled: bool`, `correlation_id: str`
    - Instantiate a module-level `CancellationRegistry` in orchestrator_api.py (or share via the hub instance)
    - Implement the endpoint: register the correlation ID in the orchestrator's registry, return 200
    - _Requirements: 5.1, 5.2_

  - [x] 3.2 Add cancellation check to the dispatch loop in `src/services/orchestrator_hub.py`
    - Add a `_cancellation_registry` attribute to `OrchestratorHub.__init__`
    - In `_direct_dispatch`: before each agent dispatch, check `self._cancellation_registry.is_cancelled(correlation_id)` — if True, break and skip remaining agents
    - In `_agent_dispatch`: check cancellation before invoking the Strands Agent
    - When cancellation is detected mid-dispatch, return `OrchestratorError` with `error_type="QUERY_CANCELLED"`
    - Remove cancellation entry on normal query completion via `registry.remove(correlation_id)`
    - _Requirements: 5.3, 5.4, 5.5, 8.2_

  - [ ]* 3.3 Write property tests for dispatch interruption (Properties 6-7)
    - **Property 6: Dispatch interruption on cancellation** — given N agents and cancellation after K dispatches, at most K+1 agents receive calls
    - **Property 7: Cancelled query produces QUERY_CANCELLED error** — any cancelled correlation ID in the registry causes process_intent to return OrchestratorError with error_type="QUERY_CANCELLED"
    - **Validates: Requirements 5.3, 5.5**

- [x] 4. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Spoke Agent cancellation support
  - [x] 5.1 Add pre-operation cancellation check to `src/agents/redshift_spoke_agent.py`
    - Before executing the SQL query (expensive operation), call `await request.is_disconnected()` to check if the upstream connection was closed
    - If disconnected, return a JSONResponse with status code 499 and body `{"status": "CANCELLED", "agent_id": agent_id}`
    - Release any held resources (skip the Redshift Data API call)
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 5.2 Add pre-operation cancellation check to the CSV/JSON spoke agent (port 8010)
    - Apply the same disconnect detection pattern before file I/O or LLM calls
    - Return status "CANCELLED" with appropriate error response on disconnect
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 5.3 Write property test for spoke agent cancellation (Property 8)
    - **Property 8: Spoke agent cancellation detection and response** — when upstream connection is closed, spoke agent returns "CANCELLED" status and does NOT execute the expensive operation
    - **Validates: Requirements 6.1, 6.3**

- [x] 6. Implement Frontend cancellation support
  - [x] 6.1 Add correlation ID generation and cancel API to `frontend/src/api/queryApi.ts`
    - Implement `generateCorrelationId()` using `crypto.randomUUID()`
    - Implement `cancelQuery(correlationId: string)` that sends POST to `/cancel` with fire-and-forget error handling
    - Modify the existing query function to accept and propagate a correlation ID as `X-Correlation-ID` header and an `AbortSignal`
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 6.2 Add cancel action to `frontend/src/store/sessionStore.ts`
    - Add transient state: `_activeAbortController` and `_activeCorrelationId` module-level variables
    - On query submission: create new `AbortController`, generate correlation ID, store both
    - Implement `cancelQuery` action: call `AbortController.abort()`, call `cancelQuery()` API (fire-and-forget), set loading to false, append system message "Query cancelled", re-enable input
    - On query completion/failure: clear the active AbortController and correlation ID
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 10.1, 10.2, 10.3_

  - [x] 6.3 Update `frontend/src/components/ChatInput.tsx` to show cancel button
    - When `loading` is true, render a Cancel button in place of the submit button
    - Wire the Cancel button's click handler to call the store's `cancelQuery` action
    - When `loading` is false, show the normal submit button
    - Style the cancel button distinctively (e.g., red/stop icon) for clear affordance
    - _Requirements: 1.1, 1.2, 1.3_

  - [ ]* 6.4 Write property test for correlation ID uniqueness (Property 9)
    - **Property 9: Correlation ID uniqueness per query** — any two generated correlation IDs are distinct and conform to UUID v4 format
    - **Validates: Requirements 10.3**

  - [ ]* 6.5 Write frontend unit tests (Vitest + Testing Library)
    - Test ChatInput renders cancel button when `loading=true`
    - Test cancel button click calls `cancelQuery` store action
    - Test store action aborts controller, sends POST `/cancel`, appends message, resets loading
    - Test correlation ID is generated and sent as header with each query
    - **Validates: Requirements 1.1, 1.2, 1.3, 2.1, 2.3**

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Integration wiring and end-to-end validation
  - [x] 8.1 Wire cancellation propagation end-to-end
    - Verify the NLP API `/cancel` endpoint correctly propagates to Orchestrator Hub `/internal/cancel`
    - Verify the Orchestrator Hub's registry is shared with its dispatch loop (the same instance used by the endpoint and by `process_intent`)
    - Verify the frontend sends both `AbortController.abort()` and POST `/cancel` on cancel button click
    - Verify CORS allows the `/cancel` POST from the frontend origin
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 8.2 Write integration tests for end-to-end cancellation flow
    - Test: submit query, cancel mid-flight, verify NLP API registers cancellation and propagates to orchestrator
    - Test: two concurrent queries, cancel one, verify the other completes unaffected
    - Test: cancel after query completion is a no-op (idempotent)
    - **Validates: Requirements 7.1, 7.2, 7.3, 9.1, 9.2, 9.3**

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The CancellationRegistry is a shared module instantiated independently by each service (not shared across processes)
- Backend is built first so the frontend can be tested against real endpoints
