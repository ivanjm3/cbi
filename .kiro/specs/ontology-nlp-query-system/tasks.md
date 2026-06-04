# Implementation Plan: Ontology NLP Query System

## Overview

This plan implements Phase 1 of the ontology-based NLP query system as a set of local Python/FastAPI services following a hub-and-spoke architecture. Tasks are ordered for incremental development: foundational data models and shared utilities first, then individual components building toward the full end-to-end flow.

## Tasks

- [x] 1. Set up project structure, dependencies, and shared data models
  - [x] 1.1 Create project directory structure and Python package layout
    - Create top-level project with directories: `src/`, `src/models/`, `src/services/`, `src/agents/`, `data/ontology/`, `data/`, `tests/`, `tests/properties/`, `tests/unit/`, `tests/integration/`
    - Create `pyproject.toml` with dependencies: fastapi, uvicorn, pydantic, hypothesis, pytest, numpy, httpx, boto3, strands-agents
    - Create a shared config module with port assignments (NLP: 8001, Orchestrator: 8002, Guardrail: 8003, Viz: 8004, Agent A: 8010, Agent B: 8011)
    - _Requirements: All (project foundation)_

  - [x] 1.2 Implement shared data models (Pydantic)
    - Implement `StructuredIntent` with fields: query_id (UUID), query_type (Literal["lookup", "aggregation", "comparison"]), entity_refs (list[str]), routing_metadata (dict), timestamp (datetime)
    - Implement `AgentResult` with fields: status (Literal["success", "error"]), payload (dict | None), error_type (str | None), error_description (str | None), agent_id (str), data_source (str)
    - Implement `OrchestratorResponse` with fields: query_id (UUID), results (list[AgentResult]), unavailable_agents (list[str])
    - Implement `OrchestratorError` with fields: error_type (Literal["NO_AGENTS_RESOLVED", "ALL_AGENTS_TIMED_OUT"]), message (str), query_id (UUID)
    - Implement `NLPError` with fields: error_code (Literal["UNPARSEABLE_QUERY", "NO_ONTOLOGY_MATCH", "AMBIGUOUS_INTENT"]), error_message (str), query_id (UUID)
    - Implement `GuardrailResult` with fields: status (Literal["passed", "redacted", "rejected", "error"]), validated_response (OrchestratorResponse | None), applied_rules (list[str]), error_details (str | None)
    - Implement `RenderedOutput` with fields: output_type (Literal["chart", "text"]), chart_type (Literal["bar", "line", "scatter", "pie", "table"] | None), chart_data (dict | None), text_content (str | None), description (str), metadata (dict)
    - Implement `AgentRegistration` with fields: agent_id (str), agent_name (str), data_source (str), endpoint_url (str), entity_refs (list[str])
    - _Requirements: 2.1, 6.3, 7.2, 8.1_

  - [x] 1.3 Write property tests for StructuredIntent model validation
    - **Property 1: Structured Intent Completeness** — verify that any StructuredIntent instance always contains valid UUID query_id, exactly one valid query_type, non-empty entity_refs, routing_metadata, and timestamp
    - **Validates: Requirements 2.1, 2.3**

- [x] 2. Implement Observability Bus (cross-cutting concern)
  - [x] 2.1 Implement the observability decorator and structured JSON logging
    - Create `src/services/observability.py` with `observability_decorator(service_name)` function
    - Emit structured JSON logs with fields: service_name, operation_name, correlation_id, timestamp (ISO 8601), request_duration_ms
    - Generate new UUID as correlation_id when not present on inbound request
    - On unhandled exceptions, emit additional fields: exception_type, exception_message, stack_trace
    - Implement correlation ID extraction from `X-Correlation-ID` header and propagation helper for downstream calls
    - _Requirements: 11.2, 11.3, 11.4, 11.5_

  - [x] 2.2 Write property tests for observability telemetry correctness
    - **Property 14: Observability Telemetry Correctness** — verify that for any service invocation the decorator emits correct structured JSON with all required fields, generates correlation_id if missing, and propagates it to downstream calls
    - **Validates: Requirements 11.2, 11.3, 11.4, 11.5**

- [x] 3. Implement Ontology Store (flat-file backend)
  - [x] 3.1 Implement OntologyConcept, OntologyRelationship, OntologyDefinition models
    - Create `src/models/ontology.py` with Pydantic models for OntologyConcept (concept_id, label, properties, relationships), OntologyRelationship (source_id, target_id, relation_type, properties), OntologyDefinition (concepts, relationships, metadata)
    - _Requirements: 3.1, 12.1_

  - [x] 3.2 Implement flat-file OntologyStore with uniform query interface
    - Create `src/services/ontology_store.py` with class `OntologyStore`
    - Implement `lookup_concept(concept_id)` — returns OntologyConcept or None
    - Implement `traverse_hierarchy(concept_id, direction)` — returns list of related concepts
    - Implement `search_concepts(keyword)` — keyword search over concept labels
    - Implement CRUD methods: `create_definition`, `update_definition`, `delete_definition`
    - Implement `serialize` / `deserialize` / `pretty_print` for JSON round-trip
    - Backend reads/writes JSON files from `./data/ontology/` directory
    - Reject malformed or duplicate-identifier definitions with structured errors, preserving existing state
    - _Requirements: 3.1, 3.3, 3.5, 3.6, 3.7, 3.8, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 3.3 Write property tests for ontology serialization round-trip
    - **Property 15: Ontology Serialization Round-Trip** — for any valid OntologyDefinition, serialize then deserialize produces same concepts, relationships, and properties regardless of ordering
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [x] 3.4 Write property tests for ontology pretty-print round-trip
    - **Property 16: Ontology Pretty-Print Round-Trip** — for any valid OntologyDefinition, pretty-print then parse produces same concepts, relationships, and properties
    - **Validates: Requirements 12.4, 12.5**

  - [x] 3.5 Write property tests for malformed ontology rejection
    - **Property 4: Malformed Ontology Definition Rejection Preserves State** — for any malformed/duplicate definition submitted, the store rejects with structured error and state remains unchanged
    - **Property 17: Malformed Serialized Data Rejection** — for any malformed serialized data, deserialization rejects with structured error indicating parse failure location
    - **Validates: Requirements 3.8, 12.6**

  - [x] 3.6 Create sample ontology data files for development
    - Create `./data/ontology/enterprise_ontology.json` with sample concepts (sales_revenue, quarterly_report, employee_count, product_catalog) and relationships
    - Include concepts that map to both demo spoke agents (JSON file agent and CSV agent)
    - _Requirements: 3.3_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement Query History Store (SQLite + numpy)
  - [x] 5.1 Implement QueryHistoryStore with SQLite backend and embedding similarity search
    - Create `src/services/query_history_store.py` with class `QueryHistoryStore`
    - Create SQLite schema with table: record_id, query_text, structured_intent (JSON), embedding (BLOB), created_at, user_id, expires_at
    - Implement `persist(query_text, intent)` — generate embedding via Bedrock Titan Embeddings, store in SQLite
    - Implement `find_similar(query_text, threshold=0.85)` — generate embedding for new query, load stored embeddings, compute cosine similarity with numpy, return matches >= threshold
    - Implement `expire_old_records(retention_days)` — delete records older than configured period
    - Handle unavailability gracefully: log structured error, return empty results on read failure
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [ ]* 5.2 Write property tests for similarity threshold filtering
    - **Property 12: Similarity Threshold Filtering** — for any set of embeddings and a query embedding, find_similar returns all and only records with cosine similarity >= 0.85
    - **Validates: Requirements 10.3**

  - [ ]* 5.3 Write property tests for history retention expiry
    - **Property 13: History Retention Expiry** — for any retention period and set of records, expire_old_records removes all records older than the period while preserving records within the window
    - **Validates: Requirements 10.4**

- [ ] 6. Implement Result Cache (in-memory dict)
  - [x] 6.1 Implement ResultCache with deterministic key hashing
    - Create `src/services/result_cache.py` with class `ResultCache`
    - Implement `get(intent_key)`, `put(intent_key, response)`, `invalidate(intent_key)`, `clear()`
    - Implement cache key generation as deterministic hash of (query_type, sorted(entity_refs), sorted(routing_metadata.items()))
    - Use Python dict as backend (no TTL, cleared on restart)
    - _Requirements: 4.1, 4.2_

  - [ ]* 6.2 Write property tests for cache hit behavior
    - **Property 5: Cache Hit Prevents Agent Dispatch** — for any intent whose key is in the cache, get() returns the cached result (verifying key generation determinism)
    - **Validates: Requirements 4.2**

- [ ] 7. Implement NLP Translator service
  - [x] 7.1 Implement NLPTranslator with Bedrock Claude integration
    - Create `src/services/nlp_translator.py` with class `NLPTranslator`
    - Implement `translate(query_text, user_id="anonymous")` method
    - Step 1: Check Query History Store for similar past intents (cosine >= 0.85)
    - Step 2: Resolve entities against Ontology Store using keyword search
    - Step 3: Classify query type via Bedrock Claude with structured prompt including ontology context
    - Step 4: Produce StructuredIntent with all required fields
    - Return NLPError for unparseable queries, no ontology matches, or ambiguous intents
    - Gracefully degrade if Query History Store is unavailable (skip bias step)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 10.6_

  - [x] 7.2 Create FastAPI app for NLP Translator on port 8001
    - Create `src/services/nlp_api.py` with FastAPI app
    - Implement `POST /query` endpoint accepting `{"query_text": "string"}`
    - Apply observability decorator to the endpoint
    - Handle X-Correlation-ID header propagation
    - Wire the full flow: NLP translate → Orchestrator → Guardrail → Renderer, return RenderedOutput
    - Return 422 with NLPError on translation failures
    - _Requirements: 2.1, 2.5, 11.2_

  - [ ]* 7.3 Write property tests for entity resolution and intent completeness
    - **Property 2: Entity Resolution Against Ontology** — for any query containing references to existing ontology concepts, the translator resolves them to canonical identifiers in entity_refs
    - **Validates: Requirements 2.2**

  - [ ]* 7.4 Write property tests for history-based routing bias
    - **Property 3: History-Based Routing Bias** — for any query where history returns matches with similarity >= 0.85, routing_metadata is set to the agent path from the most recent match
    - **Validates: Requirements 2.4**

- [ ] 8. Implement Orchestrator Hub service
  - [x] 8.1 Implement OrchestratorHub as a Strands Agent with tool-based dispatch
    - Rewrite `src/services/orchestrator_hub.py` with class `OrchestratorHub` using Strands Agents SDK
    - Implement as a Strands `Agent` with `@tool`-decorated functions for cache access, agent resolution, and spoke agent dispatch
    - Implement `process_intent(intent)` method:
      - Check Result Cache for existing result
      - On cache miss: use Strands Agent to reason about which spoke agents to invoke based on entity_refs and ontology context
      - Dispatch to spoke agents via `@tool` function with per-agent timeout (default 30s, configurable 1-300s)
      - Mark timed-out agents as unavailable
      - Merge results into OrchestratorResponse
    - Implement `register_agent(agent_config)` and `deregister_agent(agent_id)` for runtime agent management
    - Return OrchestratorError for "NO_AGENTS_RESOLVED" and "ALL_AGENTS_TIMED_OUT" cases
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 4.9, 6.5, 6.6_

  - [x] 8.2 Create FastAPI app for Orchestrator Hub on port 8002
    - Create `src/services/orchestrator_api.py` with FastAPI app
    - Implement `POST /internal/process` accepting StructuredIntent
    - Implement `POST /admin/agents` for agent registration
    - Implement `DELETE /admin/agents/{agent_id}` for agent deregistration
    - Apply observability decorator to all endpoints
    - Propagate X-Correlation-ID to downstream spoke agent calls
    - _Requirements: 4.1, 6.5, 11.4_

  - [ ]* 8.3 Write property tests for concurrent dispatch and result merge
    - **Property 6: Concurrent Dispatch and Result Merge Correctness** — for any set of agents and any combination of responses/timeouts, the hub dispatches concurrently, marks timed-out agents as unavailable, and produces correct merged response
    - **Validates: Requirements 4.4, 4.6, 4.7**

- [ ] 9. Implement Spoke Agents (2 demo agents with Strands SDK)
  - [x] 9.1 Implement Spoke Agent A (JSON file data source)
    - Create `src/agents/spoke_agent_json.py` using Strands Agents SDK
    - Implement `@tool` decorated function that translates StructuredIntent into a file-based JSON query
    - Agent queries only its designated JSON data source file
    - Return AgentResult with status, payload (structured data with columns/rows), or error info
    - No retry on data source errors (single-attempt semantics)
    - Create sample JSON data file at `./data/sources/financial_data.json`
    - Run as FastAPI process on port 8010 with `POST /agents/spoke-agent-json/invoke`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 9.2 Implement Spoke Agent B (CSV file data source)
    - Create `src/agents/spoke_agent_csv.py` using Strands Agents SDK
    - Implement `@tool` decorated function that translates StructuredIntent into a CSV query (pandas/csv read + filter)
    - Agent queries only its designated CSV data source file
    - Return AgentResult with status, payload, or error info
    - No retry on data source errors
    - Create sample CSV data file at `./data/sources/product_catalog.csv`
    - Run as FastAPI process on port 8011 with `POST /agents/spoke-agent-csv/invoke`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 9.3 Write property tests for spoke agent data source isolation
    - **Property 7: Spoke Agent Data Source Isolation** — for any intent dispatched to an agent, it queries only its single designated data source
    - **Validates: Requirements 6.1**

  - [ ]* 9.4 Write property tests for spoke agent output schema compliance
    - **Property 8: Spoke Agent Output Schema Compliance** — for any intent dispatched, the agent returns a response conforming to AgentResult schema with status and payload
    - **Validates: Requirements 6.2, 6.3**

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implement Guardrail Layer service
  - [x] 11.1 Implement GuardrailLayer with schema validation and policy rules
    - Create `src/services/guardrail_layer.py` with class `GuardrailLayer`
    - Implement `validate(response, intent)` method:
      - Step 1: Validate response against registered JSON Schema for the query_type
      - Step 2: Evaluate response against all configured safety/policy rules (loaded from JSON config file)
      - Step 3: For partial violations → redact violating content, annotate with rule IDs, forward
      - Step 4: For full violations → reject with structured error
      - Step 5: On success → persist query + intent to Query History Store (async, fire-and-forget)
    - Create rule configuration file format with: rule_id, rule_name, rule_type, action (redact/reject), pattern (regex/keyword), severity, enabled
    - Create `./data/guardrail_rules.json` with sample rules (PII detection, profanity filter)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 10.1_

  - [x] 11.2 Create FastAPI app for Guardrail Layer on port 8003
    - Create `src/services/guardrail_api.py` with FastAPI app
    - Implement `POST /internal/validate` accepting OrchestratorResponse and StructuredIntent
    - On passed/redacted: call Visualization Renderer and return RenderedOutput
    - On rejected: return 422 with error details
    - Apply observability decorator, propagate correlation ID
    - _Requirements: 7.1, 7.7, 11.4_

  - [ ]* 11.3 Write property tests for guardrail schema validation
    - **Property 9: Guardrail Schema Validation** — for any response failing schema validation, it is rejected with structured error and never forwarded
    - **Validates: Requirements 7.2, 7.4**

  - [ ]* 11.4 Write property tests for guardrail partial redaction
    - **Property 10: Guardrail Partial Redaction** — for any response with mixed valid/violating content, only violating content is redacted, rule IDs are annotated, and response is forwarded
    - **Validates: Requirements 7.5**

- [ ] 12. Implement Visualization Renderer service
  - [ ] 12.1 Implement VisualizationRenderer as a Strands Agent with dynamic chart generation
    - Rewrite `src/services/visualization_renderer.py` with class `VisualizationRenderer` using Strands Agents SDK
    - Implement as a Strands `Agent` with `@tool`-decorated functions for data analysis, chart spec generation, and description writing
    - Implement `render(response)` method:
      - Present data payload and query context to the Strands Agent
      - Agent analyzes data patterns (trends, distributions, comparisons, outliers)
      - Agent selects optimal chart type based on data shape + query intent
      - Agent generates interactive Chart.js/Vega-Lite spec with annotations, tooltips, and styling
      - Agent writes human-readable description with statistical insights
    - Include deterministic fallback (rule-based) if LLM is unavailable
    - Fall back to table if agent cannot determine better chart type within 3 iterations
    - Return RenderedOutput with all required fields
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [x] 12.2 Create FastAPI app for Visualization Renderer on port 8004
    - Create `src/services/visualization_api.py` with FastAPI app
    - Implement `POST /internal/render` accepting validated response and intent
    - Return RenderedOutput on success, 500 with error on render failure
    - Apply observability decorator, propagate correlation ID
    - _Requirements: 8.5, 8.6, 11.4_

  - [ ]* 12.3 Write property tests for visualization data type detection
    - **Property 11: Visualization Data Type Detection** — for any validated response, the renderer classifies it as graphical if and only if it contains structured numeric or categorical data; otherwise plain text
    - **Validates: Requirements 8.1**

- [ ] 13. Wire end-to-end flow and integration
  - [x] 13.1 Wire NLP Translator to call Orchestrator Hub, Guardrail Layer, and Visualization Renderer
    - Update NLP API (`POST /query`) to orchestrate the full flow:
      1. Translate query → StructuredIntent
      2. Call Orchestrator Hub `/internal/process` with intent
      3. Call Guardrail Layer `/internal/validate` with response + intent
      4. Call Visualization Renderer `/internal/render` with validated response
      5. Return RenderedOutput to client
    - Use httpx async client for inter-service HTTP calls
    - Propagate X-Correlation-ID through the entire chain
    - Handle errors at each step and return appropriate error responses
    - _Requirements: 2.1, 4.1, 7.1, 8.6, 11.4_

  - [x] 13.2 Register demo spoke agents with Orchestrator Hub on startup
    - Create a startup script or initialization module that registers both demo agents with the Orchestrator Hub
    - Agent A (JSON): agent_id="spoke-agent-json", endpoint_url="http://localhost:8010", entity_refs mapped to ontology concepts (e.g., "ontology:sales_revenue", "ontology:quarterly_report")
    - Agent B (CSV): agent_id="spoke-agent-csv", endpoint_url="http://localhost:8011", entity_refs mapped to ontology concepts (e.g., "ontology:product_catalog", "ontology:employee_count")
    - _Requirements: 6.5, 6.6_

  - [x] 13.3 Create a launcher script to start all services
    - Create `run_all.py` or shell script that starts all 6 FastAPI processes on their designated ports
    - Include health check endpoints (`GET /health`) on each service
    - Print service URLs and status on startup
    - _Requirements: All (deployment convenience)_

  - [ ]* 13.4 Write integration tests for end-to-end query flow
    - Test full query flow: NLP → Orchestrator → Agent → Guardrail → Renderer
    - Test cache hit scenario (second identical query returns cached result)
    - Test partial agent timeout scenario
    - Test guardrail redaction in the flow
    - Mock Bedrock calls for deterministic testing
    - _Requirements: 2.1, 4.1, 4.2, 4.6, 7.5_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Phase 1 uses local processes only — no cloud infrastructure deployment required
- Amazon Bedrock access (Claude Sonnet for NLP, Titan Embeddings for history) requires AWS credentials configured locally
- All services communicate via HTTP on localhost with different ports
