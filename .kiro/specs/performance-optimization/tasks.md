# Implementation Plan: Performance Optimization

## Overview

Incrementally optimize the ontology-based NLP query system to reduce latency through prompt compression, guardrail streamlining, parallel execution, intelligent caching, and progressive response delivery. All changes preserve functional correctness and use Python with the existing project structure.

## Tasks

- [ ] 1. Create LRU Cache utility
  - [x] 1.1 Implement `src/services/lru_cache.py` with generic `LRUCache` class
    - Create `LRUCache` using `OrderedDict` with configurable `max_size`
    - Implement `get(key)` that moves accessed entries to end (most recent)
    - Implement `put(key, value)` that adds/updates and evicts LRU entries when exceeding `max_size`
    - Implement `size` property and `clear()` method
    - _Requirements: 5.3, 5.7_

  - [ ]* 1.2 Write property test for LRU cache eviction (Property 6)
    - **Property 6: LRU Cache Eviction**
    - Generate insertion sequences exceeding max_size, verify cache never exceeds max_size and evicts least recently accessed entries
    - Create `tests/properties/test_lru_cache.py`
    - **Validates: Requirements 5.3, 5.7**

  - [ ]* 1.3 Write unit tests for LRU cache
    - Test basic get/put, size limit, LRU ordering, clear, cache miss returns None
    - Create `tests/unit/test_lru_cache.py`
    - _Requirements: 5.3, 5.7_

- [ ] 2. Optimize spoke agent prompts
  - [x] 2.1 Compress spoke agent system prompt and add `max_tokens=500`
    - Modify `src/agents/spoke_agent.py`
    - Replace the current system prompt with a compressed version under 200 tokens focused on tool-call-only output
    - Add `model_kwargs={"max_tokens": 500}` to the `Agent()` constructor
    - Simplify the per-request prompt in `invoke_agent()` to include only `query_type`, `entity_refs`, and one-line tool descriptions
    - _Requirements: 1.2, 1.3, 1.4, 1.6_

  - [ ] 2.2 Write property test for spoke agent prompt minimalism (Property 1)
    - **Property 1: Spoke Agent Prompt Minimalism**
    - Generate random StructuredIntents, verify the constructed prompt contains only query_type, entity_refs, and single-line tool descriptions — no full schemas or verbose instructions
    - Create `tests/properties/test_spoke_prompt.py`
    - **Validates: Requirements 1.3**

- [ ] 3. Optimize visualization agent prompts and progressive stats
  - [x] 3.1 Compress visualization agent system prompt and add `max_tokens=500`
    - Modify `src/services/visualization_renderer.py`
    - Replace `VISUALIZER_SYSTEM_PROMPT` with a compressed version under 250 tokens with clear JSON-only output directive
    - Add `model_kwargs={"max_tokens": 500}` to the visualization `Agent()` constructor
    - _Requirements: 2.6, 2.7_

  - [x] 3.2 Ensure progressive response pattern: stats computed before LLM call
    - Modify `src/services/visualization_renderer.py` `render()` method
    - Compute `_generate_stats_description()` immediately from raw payload before calling `_agent_render()`
    - Ensure `text_content` is always populated with stats regardless of agent success
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

  - [ ]* 3.3 Write property test for chart type selection correctness (Property 2)
    - **Property 2: Chart Type Selection Correctness**
    - Generate random structured payloads with typed columns, verify rule-based chart selector produces correct chart types per documented rules
    - Create `tests/properties/test_chart_selection.py`
    - **Validates: Requirements 2.2**

  - [ ]* 3.4 Write property test for rendered output completeness (Property 4)
    - **Property 4: Rendered Output Completeness**
    - Generate structured payloads, verify RenderedOutput always contains non-empty `description`, non-null `text_content` with stats, and non-null `chart_data` for structured data
    - Create `tests/properties/test_rendered_output.py`
    - **Validates: Requirements 2.5, 6.2, 2.9**

  - [ ]* 3.5 Write property test for statistical summary correctness (Property 8)
    - **Property 8: Statistical Summary Correctness**
    - Generate numeric data payloads, verify computed stats (sum, avg, count, min, max) match actual values
    - Create `tests/properties/test_stats_correctness.py`
    - **Validates: Requirements 6.1**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Streamline guardrails to Bedrock-only
  - [x] 5.1 Remove local regex rules from input guardrails
    - Modify `src/services/nlp_api.py`
    - Remove `_INPUT_GUARDRAIL_PATTERNS` list and the regex-checking portion of `_check_input_guardrails()`
    - Replace with `_check_input_guardrails_bedrock()` that calls Bedrock Guardrails API with `source="INPUT"` only
    - On Bedrock unavailability: fail open (allow content, log structured warning)
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

  - [x] 5.2 Remove local rules engine from output guardrail layer
    - Modify `src/services/guardrail_layer.py`
    - Remove `GuardrailRule` class, `_load_rules()`, `_evaluate_rules()`, `_apply_redactions()` methods
    - Remove dependency on `data/guardrail_rules.json`
    - Simplify `validate()` to only: schema validation → Bedrock Guardrails (OUTPUT) → result
    - On Bedrock unavailability: fail open (allow content, log structured warning)
    - _Requirements: 3.1, 3.3, 3.4, 3.5_

- [ ] 6. Add parallel execution
  - [x] 6.1 Parallelize entity resolution and history bias in NLP Translator
    - Modify `src/services/nlp_translator.py` `translate()` method
    - Run `_resolve_entities()` and `_get_history_bias()` concurrently via `asyncio.gather` with `asyncio.to_thread`
    - _Requirements: 4.1_

  - [x] 6.2 Parallelize input guardrail check and NLP translation
    - Modify `src/services/nlp_api.py` `query_endpoint()`
    - Run `_check_input_guardrails_bedrock()` and `translator.translate()` concurrently via `asyncio.gather`
    - If input guardrail rejects, return 422 immediately; otherwise use translation result
    - _Requirements: 4.3_

  - [x] 6.3 Parallelize spoke agent dispatch in orchestrator hub
    - Modify `src/services/orchestrator_hub.py` `_direct_dispatch()` method
    - Convert sequential `for agent in resolved_agents` loop to concurrent dispatch using `asyncio.gather` with `asyncio.to_thread`
    - _Requirements: 4.2_

  - [ ]* 6.4 Write property test for entity resolution determinism (Property 9)
    - **Property 9: Entity Resolution Determinism**
    - Generate query texts, verify entity resolution produces identical entity_refs before and after parallelization
    - Create `tests/properties/test_entity_resolution.py`
    - **Validates: Requirements 8.3**

- [ ] 7. Add classification cache to NLP Translator
  - [x] 7.1 Integrate LRU classification cache into NLP Translator
    - Modify `src/services/nlp_translator.py`
    - Add `LRUCache(max_size=1000)` to `NLPTranslator.__init__()`
    - Implement `_classification_cache_key()` using SHA-256 of `normalized_query|sorted_entity_refs`
    - Check cache before calling `classifier.classify_query_type()`, store result on cache miss
    - _Requirements: 5.1, 5.2, 5.3_

  - [ ]* 7.2 Write property test for classification cache determinism (Property 5)
    - **Property 5: Classification Cache Determinism and Hit Behavior**
    - Generate random query+entity_refs combinations, verify cache key is deterministic and cache hits skip Bedrock calls
    - Create `tests/properties/test_classification_cache.py`
    - **Validates: Requirements 5.1, 5.2**

- [ ] 8. Add guardrail cache
  - [x] 8.1 Integrate LRU guardrail cache into Guardrail Layer
    - Modify `src/services/guardrail_layer.py`
    - Add `LRUCache(max_size=500)` to `GuardrailLayer.__init__()`
    - Implement `_compute_content_hash()` using SHA-256 of deterministically serialized response
    - Check cache before calling Bedrock Guardrails; store result (both pass and reject) on cache miss
    - _Requirements: 5.5, 5.6, 5.7_

  - [ ]* 8.2 Write property test for guardrail cache keying (Property 7)
    - **Property 7: Guardrail Cache Keying and Hit Behavior**
    - Generate random OrchestratorResponses, verify SHA-256 cache key is deterministic and cache hits skip Bedrock validation
    - Create `tests/properties/test_guardrail_cache.py`
    - **Validates: Requirements 5.5, 5.6**

- [ ] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Update frontend for progressive rendering
  - [x] 10.1 Update frontend to render stats text immediately alongside chart
    - Modify `frontend/index.html`
    - In `showResult()`, render `text_content` (statistics) in a visible section before/alongside the chart
    - Ensure the stats section is displayed prominently when `text_content` is present, even if `chart_data` is also present
    - _Requirements: 6.2, 6.3_

- [ ] 11. Integration verification
  - [ ]* 11.1 Write property test for chart spec validity (Property 3)
    - **Property 3: Chart Specification Validity**
    - Generate structured payloads, verify produced chart specs are valid Chart.js-compatible objects with required fields (`type`, `datasets` or `rows`, interactive options)
    - Create `tests/properties/test_chart_spec_validity.py`
    - **Validates: Requirements 2.3, 8.2**

  - [ ]* 11.2 Write property test for error response format preservation (Property 10)
    - **Property 10: Error Response Format Preservation**
    - Generate various error conditions, verify responses conform to NLPError/OrchestratorError schemas
    - Create `tests/properties/test_error_format.py`
    - **Validates: Requirements 8.4**

  - [ ]* 11.3 Write integration tests for end-to-end optimized pipeline
    - Verify existing tests in `tests/properties/` and `tests/unit/` still pass
    - Add test verifying Bedrock Guardrails fail-open behavior
    - Add test verifying parallel execution produces same results as sequential
    - Create `tests/integration/test_performance_optimization.py`
    - _Requirements: 8.5_

- [ ] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python (matching existing codebase and design document)
- All services already reference `DEFAULT_MODEL_ID` from `src/config.py` — no model verification code changes needed (Requirement 7)
