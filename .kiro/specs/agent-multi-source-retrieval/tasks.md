# Implementation Plan: Agent Multi-Source Retrieval

## Overview

This plan replaces the NLP Translator + Orchestrator Hub two-service architecture with a single Query_Planner_Agent (Strands SDK), implements modular Data_Source_Connectors, extends the ontology with source_mapping, and adds a Result_Assembler for cross-source queries. Implementation proceeds in four incremental phases with stabilization checkpoints after each.

All data sources are AWS-hosted (RDS PostgreSQL, DynamoDB, S3 CSV, S3/CloudWatch logs). The user provisions these manually via AWS CLI or Console before the connectors are wired up. The ontology is updated with source_mappings only after all data sources are provisioned and registered.

## Tasks

- [ ] 1. Phase 1: Query Planner + Backend Agent API
  - [x] 1.1 Create data models for Execution Plan, Source Config, and Connector Result
    - Create `src/models/execution_plan.py` with `SubTask`, `MergeStrategy`, `ExecutionPlan` Pydantic models
    - Create `src/models/source_config.py` with `ColumnDescriptor`, `SchemaDescriptor`, `SourceConfig` Pydantic models
    - Create `src/models/connector_result.py` with `ConnectorResult` dataclass (status, columns, rows, row_count, data_source, error_type, error_description, metadata)
    - Create `src/models/session_context.py` with `SessionContext` Pydantic model for conversational state
    - _Requirements: 5.1, 5.6, 3.1, 3.2_

  - [ ]* 1.2 Write property tests for Execution Plan and Source Config models
    - **Property 10: Execution Plan Structural Invariants** — generate random DAGs of sub-tasks and verify: (a) at least one sub-task, (b) valid merge_strategy, (c) all depends_on reference existing task_ids, (d) dependency graph is acyclic
    - **Validates: Requirements 5.1**
    - **Property 11: Execution Plan Serialization Round-Trip** — serialize random valid ExecutionPlans to JSON and deserialize back, confirm equality
    - **Validates: Requirements 5.6**
    - **Property 5: Source Registry Config Round-Trip** — generate random SourceConfig objects, serialize/deserialize via Pydantic, confirm equality
    - **Validates: Requirements 3.1, 3.2**

  - [-] 1.3 Implement the Query Planner Agent
    - Create `src/agents/query_planner_agent.py` with a `QueryPlannerAgent` class using the Strands SDK `Agent`
    - Define tools: `lookup_ontology`, `search_sources`, `query_rds_source`, `query_dynamodb_source`, `query_s3_csv_source`, `query_log_source`, `query_s3_json_source`
    - Implement `plan_and_execute(query_text, session_context) -> OrchestratorResponse` method
    - Implement the system prompt (QUERY_PLANNER_SYSTEM_PROMPT) with ontology and schema context
    - Implement fallback deterministic routing (keyword extraction → entity resolution → direct source query) when agent fails
    - _Requirements: 1.1, 1.2, 1.4, 1.5, 7.1, 7.2, 7.3, 7.5, 9.4_

  - [ ] 1.4 Implement the Backend Agent API (FastAPI gateway)
    - Create `src/services/backend_agent_api.py` with FastAPI app on port 8001
    - Implement `POST /query` endpoint accepting `{"query_text": str}` and returning `{"rendered_output": ..., "latency": ..., "query_id": ..., "correlation_id": ...}`
    - Implement `GET /health` endpoint
    - Implement `GET /v1/sources`, `POST /v1/sources`, `DELETE /v1/sources/{id}` stubs (populated in Phase 2)
    - Implement in-memory session context store (dict keyed by session_id header)
    - Configure CORS identically to current NLP API
    - Wire query flow: receive query → invoke QueryPlannerAgent → forward OrchestratorResponse to Guardrail (port 8003) → forward to Viz Renderer (port 8004) → return RenderedOutput
    - Propagate correlation IDs through all downstream calls
    - _Requirements: 6.1, 6.2, 6.4, 6.5, 7.1, 8.4, 9.3_

  - [ ] 1.5 Implement legacy S3 JSON connector (bridge for existing queries)
    - Create `src/connectors/s3_json_connector.py` implementing the DataSourceConnector interface
    - Port the existing `query_financial_data` and `query_product_catalog` logic from `src/agents/spoke_agent.py` into the connector format (returns `ConnectorResult`)
    - Support connection_params: `{"bucket": str, "key": str, "format": "json"|"csv"}`
    - _Requirements: 8.1, 8.2_

  - [ ] 1.6 Update `run_all.py` service topology
    - Replace the NLP Translator (port 8001) entry with Backend_Agent_API (port 8001)
    - Remove Orchestrator Hub (port 8002) and Spoke Agent (port 8010) service entries
    - Keep Guardrail Layer (port 8003) and Visualization Renderer (port 8004) unchanged
    - Remove agent registration step (no longer needed — connectors are in-process tools)
    - _Requirements: 8.3, 8.4_

  - [ ]* 1.7 Write unit tests for Backend Agent API and Query Planner
    - Test POST /query endpoint returns correct response structure with mocked QueryPlannerAgent
    - Test fallback path: mock agent to raise exception, verify deterministic routing produces valid OrchestratorResponse
    - Test clarification response for vague queries
    - Test CORS headers are present
    - Test health endpoint responds 200
    - Test backward compatibility: existing financial/product queries produce same payload structure
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 9.4_

  - [ ] 1.8 Phase 1 Stabilization Checkpoint
    - Ensure all tests pass, ask the user if questions arise.
    - Verify existing queries ("show me quarterly sales revenue", "list product catalog") still return valid rendered output through the new Backend_Agent_API → Guardrail → Viz pipeline
    - Confirm the old NLP API, Orchestrator Hub, and Spoke Agent are no longer started

- [ ] 2. Phase 2: AWS Data Source Provisioning + Source Registry + Data Source Connectors
  - [ ] 2.1 Provision AWS data sources (manual — user-driven)
    - **RDS PostgreSQL**: Create an RDS PostgreSQL instance (e.g., `db.t3.micro` free-tier eligible). Create a database and seed with a sample table (e.g., `orders` with columns: order_id, product, region, amount, order_date). Note the endpoint, port, credentials.
    - **DynamoDB**: Create a DynamoDB table via AWS CLI/Console (e.g., `user_events` with partition key `user_id`, sort key `event_timestamp`). Seed with sample items.
    - **S3 CSV**: Upload sample CSV files to the existing S3 bucket under a new prefix (e.g., `s3://visualization-poc-bucket/csv-sources/metrics.csv`). Include columns like metric_name, value, timestamp, category.
    - **S3 Log files**: Upload sample structured log files (JSON-lines format) to S3 under a prefix (e.g., `s3://visualization-poc-bucket/logs/app.jsonl`). Include entries with timestamp, level, message, service, request_id.
    - Document all connection details (endpoints, table names, S3 paths, credentials approach) in `data/aws_sources.md`
    - _Requirements: 2.1, 2.2, 2.3, 2.4_
    - _Note: This is a manual step — the user provisions resources via AWS CLI or Console_

  - [ ] 2.2 Implement the Data Source Connector base interface
    - Create `src/connectors/__init__.py`
    - Create `src/connectors/base.py` with abstract `DataSourceConnector` class (execute, health_check, source_type)
    - Define the `ConnectorResult` import from `src/models/connector_result.py`
    - _Requirements: 2.5_

  - [ ] 2.3 Implement RDS PostgreSQL Connector
    - Create `src/connectors/rds_connector.py` implementing `DataSourceConnector`
    - Use SQLAlchemy with `postgresql+psycopg2://` connection string for RDS access
    - Implement `execute(query_params)` with parameterized SQL execution (never raw string interpolation)
    - Implement `health_check()` with a lightweight `SELECT 1` query
    - Support connection_params: `{"connection_string": str, "pool_size": int}` — connection string sourced from environment variables or AWS Secrets Manager
    - Implement connection pooling with configurable max pool size (default 5)
    - Handle timeouts (configurable, default 30s) and return structured errors
    - _Requirements: 2.1, 2.5, 2.6, 9.2_

  - [ ]* 2.4 Write property test for RDS Connector
    - **Property 1: SQL Connector Data Round-Trip** — generate random tabular data (string/integer/float columns), insert into the RDS PostgreSQL test table via connector, query back, verify columns and row data match (accounting for type coercion). Requires live RDS instance.
    - **Validates: Requirements 2.1**
    - _Note: Requires the provisioned RDS instance from task 2.1 to be accessible_

  - [ ] 2.5 Implement DynamoDB Connector
    - Create `src/connectors/dynamodb_connector.py` implementing `DataSourceConnector`
    - Use boto3 with the standard AWS SDK credential chain (profile, env vars, or IAM role)
    - Implement `execute(query_params)` supporting scan and query operations with filter expressions and key conditions
    - Implement `health_check()` with a `describe_table` call
    - Support connection_params: `{"table_name": str, "region": str, "endpoint_url": str | None}` — endpoint_url is optional (only set for local testing if ever needed)
    - Handle timeouts and return structured errors
    - _Requirements: 2.2, 2.5, 9.2_

  - [ ]* 2.6 Write property test for DynamoDB Connector
    - **Property 2: DynamoDB Connector Data Round-Trip** — generate random DynamoDB items (string, number, boolean, list, map types), put via connector, scan/query back, verify equivalence. Requires live DynamoDB table.
    - **Validates: Requirements 2.2**
    - _Note: Requires the provisioned DynamoDB table from task 2.1 to be accessible_

  - [ ] 2.7 Implement S3 CSV Connector
    - Create `src/connectors/s3_csv_connector.py` implementing `DataSourceConnector`
    - Use boto3 to read CSV files from S3 paths
    - Implement `execute(query_params)` with column filtering, row filtering, and type coercion based on SchemaDescriptor
    - Implement `health_check()` by performing a HEAD request on the S3 object
    - Support connection_params: `{"bucket": str, "key": str, "delimiter": str, "has_header": bool}`
    - _Requirements: 2.3, 2.5_

  - [ ]* 2.8 Write property test for S3 CSV Connector
    - **Property 3: CSV Connector Parse Round-Trip** — generate random tabular data, upload as CSV to the test S3 bucket, read via connector, verify type-coerced rows match originals
    - **Validates: Requirements 2.3**
    - _Note: Requires the CSV files from task 2.1 to be uploaded to S3_

  - [ ] 2.9 Implement Log Connector
    - Create `src/connectors/log_connector.py` implementing `DataSourceConnector`
    - Read structured log files from S3 (JSON-lines format primarily, with support for common log format)
    - Implement `execute(query_params)` with time-range filtering, log level filtering, and keyword search
    - Implement `health_check()` by performing a HEAD request on the S3 log object
    - Support connection_params: `{"bucket": str, "key": str, "format": "jsonl"|"clf"}`
    - _Requirements: 2.4, 2.5_

  - [ ]* 2.10 Write property test for Log Connector
    - **Property 4: Log Connector Parse Round-Trip** — generate random JSON-line log entries (timestamp, level, message, arbitrary fields), upload to S3, parse via connector, verify all entries recovered with original structure
    - **Validates: Requirements 2.4**
    - _Note: Requires the log files from task 2.1 to be uploaded to S3_

  - [ ] 2.11 Implement Source Registry
    - Create `src/services/source_registry.py` with `SourceRegistry` class
    - Load/save configuration from `data/source_registry.json`
    - Implement `register(config: SourceConfig)` with health check validation on registration
    - Implement `deregister(source_id: str)` removing from routing within 5 seconds
    - Implement `find_by_concepts(concept_ids: list[str]) -> list[SourceConfig]` returning sources whose ontology_concepts intersect with query
    - Implement `get_schema(source_id: str) -> SchemaDescriptor | None`
    - Implement `health_check(source_id: str) -> bool`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 2.12 Write property tests for Source Registry
    - **Property 5: Source Registry Config Round-Trip** — generate random SourceConfig, register, retrieve, verify equality
    - **Validates: Requirements 3.1, 3.2**
    - **Property 6: Source Registry Concept Lookup Correctness** — register multiple sources with known concept mappings, query with random concept sets, verify find_by_concepts returns exactly the intersection
    - **Validates: Requirements 3.4, 3.5**

  - [ ] 2.13 Create source registry configuration for all AWS data sources
    - Create `data/source_registry.json` with entries for all provisioned AWS sources:
      - Existing S3 financial data (s3_json connector)
      - Existing S3 product catalog (s3_json connector)
      - RDS PostgreSQL instance (rds connector — connection string from env var)
      - DynamoDB table (dynamodb connector — table name + region)
      - S3 CSV files (s3_csv connector — bucket + key)
      - S3 log files (log connector — bucket + key)
    - Each entry includes: source_id, source_name, connector_type, connection_params, schema (columns/types), ontology_concepts
    - Connection secrets (RDS password) referenced via environment variables, NOT hardcoded
    - _Requirements: 3.1, 3.2_

  - [ ] 2.14 Wire connectors into Query Planner Agent as tools
    - Update `src/agents/query_planner_agent.py` to instantiate connectors from Source Registry configs
    - Register each connector type's execute method as a Strands tool
    - Update the `search_sources` tool to query Source Registry's `find_by_concepts`
    - _Requirements: 7.2, 7.4_

  - [ ] 2.15 Wire Source Registry CRUD into Backend Agent API
    - Implement `GET /v1/sources` to list registered sources
    - Implement `POST /v1/sources` to register a new source (with health check)
    - Implement `DELETE /v1/sources/{id}` to deregister a source
    - _Requirements: 3.3, 3.6, 6.1_

  - [ ] 2.16 Phase 2 Stabilization Checkpoint
    - Ensure all tests pass, ask the user if questions arise.
    - Verify each connector can execute a simple query against its provisioned AWS data source
    - Verify Source Registry CRUD endpoints work end-to-end
    - Verify existing S3-backed queries still work via the S3 JSON connector

- [ ] 3. Phase 3: Ontology Extensions (after data sources are provisioned and registered)
  - [ ] 3.1 Extend ontology model with SourceMapping
    - Add `SourceMapping` class to `src/models/ontology.py` with fields: `source_id: str`, `access_path: str`, `field_mappings: dict[str, str]`
    - Add optional `source_mapping: SourceMapping | None = None` field to `OntologyConcept`
    - Ensure backward compatibility: existing ontology JSON files without source_mapping still deserialize
    - _Requirements: 4.1_

  - [ ] 3.2 Build in-memory Knowledge Graph index from ontology data
    - Create `src/services/knowledge_graph.py` with `KnowledgeGraph` class backed by `networkx.DiGraph`
    - Add `networkx` to project dependencies (lightweight, pure-Python graph library)
    - Implement `build_from_ontology(definitions: dict[str, OntologyDefinition])` that populates the DiGraph with concept nodes (attributes: label, properties, source_mapping) and relationship edges (attributes: relation_type, properties)
    - Implement `rebuild()` method to reconstruct the graph when ontology definitions change (hot reload without restart)
    - Implement `get_neighbors(concept_id, direction="outgoing"|"incoming"|"both") -> list[str]` — O(1) adjacency lookup replacing the current O(n) linear scan
    - Implement `shortest_path(source_id, target_id) -> list[str] | None` — finds the shortest concept path between two nodes
    - Implement `find_all_reachable(concept_id, max_hops: int | None = None) -> set[str]` — BFS from a concept, optionally bounded by hop count
    - Implement `find_connecting_dimensions(concept_a, concept_b) -> list[str]` — returns shared dimension concepts (e.g., `region`, `product_category`) that connect two source-mapped concepts, enabling join key discovery for cross-source queries
    - Implement `subgraph_for_concepts(concept_ids: list[str]) -> networkx.DiGraph` — extracts a minimal subgraph spanning the given concepts (used for Execution Plan reasoning context)
    - Initialize the KnowledgeGraph inside `OntologyStore.__init__` after `_load_all()` completes, keeping it in-sync with loaded definitions
    - _Requirements: 4.1, 4.2, 4.3_
    - _Rationale: Replaces O(concepts × relationships) linear scans with O(1) neighbor lookups and built-in BFS/Dijkstra. The ontology fits entirely in memory (~10-50 concepts), so this adds zero network latency and reduces traversal time._

  - [ ]* 3.3 Write property tests for Knowledge Graph
    - **Property 14: Knowledge Graph Construction Completeness** — generate random ontology definitions (concepts + relationships), build the graph, verify every concept is a node and every relationship is an edge with correct direction and attributes
    - **Validates: Requirements 4.1**
    - **Property 15: Knowledge Graph Shortest Path Correctness** — generate random connected graphs with known distances, verify `shortest_path` returns a path of minimum length
    - **Validates: Requirements 4.2**
    - **Property 16: Knowledge Graph Join Key Discovery** — generate graphs where two concepts are connected via shared dimension nodes, verify `find_connecting_dimensions` returns exactly those shared dimensions
    - **Validates: Requirements 4.3, 1.5**

  - [ ] 3.4 Update Ontology Store with source-aware methods (backed by Knowledge Graph)
    - Add `find_concepts_with_sources(self) -> list[OntologyConcept]` method to `OntologyStore` that returns all concepts having a non-None source_mapping
    - Add `resolve_sources_for_concept(self, concept_id: str) -> list[SourceMapping]` method that uses `KnowledgeGraph.find_all_reachable()` + filters for source_mapping presence (replaces manual BFS)
    - Add `rank_sources_by_proximity(self, concept_id: str) -> list[tuple[SourceMapping, int]]` method that uses `KnowledgeGraph.shortest_path()` to compute hop distances and returns source_mappings ordered by ascending distance
    - _Requirements: 4.1, 4.2_

  - [ ]* 3.5 Write property tests for ontology traversal and source ranking
    - **Property 7: Ontology Traversal Completeness** — generate random concept graphs with source_mappings on leaf nodes, verify traversal finds all reachable source_mappings
    - **Validates: Requirements 4.1**
    - **Property 8: Source Ranking Respects Graph Proximity** — generate graphs with known distances, verify ranking orders by ascending hop count
    - **Validates: Requirements 4.2**

  - [ ] 3.6 Implement schema field validation
    - Add a `validate_fields(requested_fields: list[str]) -> bool` method to `SchemaDescriptor` in `src/models/source_config.py`
    - Returns True if and only if all requested fields exist in the schema's column names
    - _Requirements: 4.4_

  - [ ]* 3.7 Write property test for schema field validation
    - **Property 9: Schema Field Validation Correctness** — generate random schemas and random field requests, verify validation returns True iff all requested fields are in schema columns
    - **Validates: Requirements 4.4**

  - [ ] 3.8 Update Query Planner to use source-aware ontology reasoning
    - Update the `lookup_ontology` tool to include source_mapping information in its response
    - Update the system prompt to instruct the agent to use ontology source_mappings for source selection
    - Implement ontology-based source ranking as a helper used by the fallback deterministic path
    - Use `KnowledgeGraph.find_connecting_dimensions()` in the multi-source decomposition logic to automatically discover join keys between sources
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 3.9 Update ontology data files with source_mappings for all provisioned AWS data sources
    - Update the ontology JSON files in `data/ontology/` to add source_mapping entries linking concepts to registered AWS sources
    - Map existing financial concepts (sales_revenue, quarterly_report, order_volume, return_rate, region) → existing S3 financial data source
    - Map existing product concepts (product_catalog, inventory_stock, product_pricing, supplier_info, product_category) → existing S3 product catalog source
    - Add NEW ontology concepts for RDS data (e.g., `ontology:order_details`, `ontology:customer_orders`) → RDS PostgreSQL source, with access_path = table name and field_mappings for columns
    - Add NEW ontology concepts for DynamoDB data (e.g., `ontology:user_events`, `ontology:user_activity`) → DynamoDB source, with access_path = table name and field_mappings for attributes
    - Add NEW ontology concepts for S3 CSV data (e.g., `ontology:operational_metrics`, `ontology:performance_kpis`) → S3 CSV source, with access_path = S3 key
    - Add NEW ontology concepts for log data (e.g., `ontology:application_logs`, `ontology:error_logs`) → S3 log source, with access_path = S3 key
    - Each source_mapping must reference a valid source_id from `data/source_registry.json`
    - _Requirements: 4.1_
    - _Note: This task is done AFTER data sources are provisioned (task 2.1) and registered (task 2.13) so that source_ids and access_paths are known_

  - [ ] 3.10 Phase 3 Stabilization Checkpoint
    - Ensure all tests pass, ask the user if questions arise.
    - Verify ontology deserialization still works with and without source_mapping fields
    - Verify existing queries still route correctly through the source-aware ontology
    - Verify new ontology concepts (for RDS, DynamoDB, CSV, logs) are discoverable via keyword search and ontology traversal

- [ ] 4. Phase 4: Result Assembly + Multi-Source Queries
  - [ ] 4.1 Implement Result Assembler
    - Create `src/services/result_assembler.py` with `ResultAssembler` class
    - Implement `assemble(results: list[ConnectorResult], strategy: MergeStrategy) -> AgentResult`
    - Implement `_union(results)`: stack rows from all sources (same schema assumed), sum row_counts
    - Implement `_join(results, join_key)`: inner join on specified key column
    - Implement `_aggregate(results)`: combine aggregated metrics from different sources
    - Handle partial failure: include all successful data, list failed sources in response metadata
    - Ensure output conforms to `AgentResult` schema so Guardrail/Viz pipeline accepts it
    - _Requirements: 5.4, 5.5, 8.3_

  - [ ]* 4.2 Write property tests for Result Assembler
    - **Property 12: Result Assembly Correctness and OrchestratorResponse Conformance** — generate random ConnectorResults (mix of success/error), test union (row_count = sum), join (all rows contain join key present in all sources), partial failure (successful data included, failed source_ids in unavailable_agents), and OrchestratorResponse schema validation
    - **Validates: Requirements 5.4, 5.5, 8.3**

  - [ ] 4.3 Wire Result Assembler into Query Planner execution flow
    - Update `QueryPlannerAgent.plan_and_execute()` to pass connector results + merge strategy to Result_Assembler
    - Ensure multi-source queries produce a single merged AgentResult
    - Handle the "single" merge strategy (pass-through for single-source queries)
    - _Requirements: 5.2, 5.3, 5.4_

  - [ ] 4.4 Implement multi-source query decomposition logic
    - Add decomposition logic in QueryPlannerAgent that: resolves concepts → looks up Source Registry → creates sub-tasks per source → determines merge strategy
    - For queries spanning 2+ sources: create one SubTask per source, set merge_strategy to union/join/aggregate based on query type
    - Support concurrent execution of independent sub-tasks and sequential execution of dependent sub-tasks
    - _Requirements: 1.5, 5.1, 5.2, 5.3_

  - [ ]* 4.5 Write property test for multi-source query decomposition
    - **Property 13: Multi-Source Query Decomposition** — generate concept sets mapping to N≥2 distinct sources, verify decomposition produces ≥N sub-tasks and merge_strategy.method ≠ "single"
    - **Validates: Requirements 1.5**

  - [ ] 4.6 Implement per-query observability and metrics logging
    - Log ExecutionPlan as JSON for every query (source selection reasoning included)
    - Track and log per-query metrics: total latency, per-source latency, number of sources consulted, LLM token usage
    - Ensure correlation_id propagates through all connector calls
    - _Requirements: 9.1, 9.3, 9.5_

  - [ ]* 4.7 Write integration tests for end-to-end multi-source flows
    - Test a cross-source query (e.g., "compare order amounts from RDS with product prices from S3") that spans RDS + S3 sources
    - Test partial failure: one source returns error, verify partial results returned with failed source listed
    - Test existing S3 queries still produce same rendered output
    - Test the Guardrail → Viz pipeline receives valid OrchestratorResponse from multi-source results
    - _Requirements: 1.5, 5.4, 5.5, 8.1, 8.2, 8.3_

  - [ ] 4.8 Final Stabilization Checkpoint
    - Ensure all tests pass, ask the user if questions arise.
    - Run full regression: all existing single-source queries still work
    - Verify multi-source join and union queries produce correct merged results
    - Verify the system falls back gracefully when the LLM is unavailable (deterministic routing)

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation after each phase
- Property tests validate universal correctness properties defined in the design document (13 original + 3 knowledge graph = 16 total)
- Unit tests validate specific scenarios, integration points, and edge cases
- **All data sources are on AWS** — RDS PostgreSQL, DynamoDB, S3 CSV, S3 log files. No local substitutes (no SQLite, no DynamoDB Local)
- AWS resource provisioning (task 2.1) is a manual user-driven step — credentials managed via AWS SSO / env vars
- The ontology is updated with source_mappings (task 3.9) ONLY AFTER all data sources are provisioned and registered
- **Knowledge Graph** (task 3.2): Uses `networkx.DiGraph` as an in-memory indexed graph over ontology concepts. Replaces O(n) linear scans with O(1) adjacency lookups and built-in BFS/shortest-path algorithms. Zero network latency added — the graph is in-process. Enables automatic join key discovery for cross-source queries.
- The visualization renderer is NOT modified — it stays as-is
- Frontend containerization (Req 6.3) and ECS deployment (Req 6.6) are excluded per user constraints
- The old `src/services/nlp_api.py`, `src/services/orchestrator_api.py`, and `src/agents/spoke_agent.py` files are superseded but not deleted until Phase 1 stabilization confirms the new architecture works
