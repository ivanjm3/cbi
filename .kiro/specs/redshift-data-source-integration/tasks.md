# Implementation Plan: Redshift Data Source Integration

## Overview

This plan implements Amazon Redshift as a new data source in the Conversational BI application. The implementation follows the hub-and-spoke architecture, creating a new Redshift Spoke Agent (FastAPI on port 8011) with supporting components: a Redshift Connector (boto3 redshift-data), Schema Registry (concept→table mapping), SQL Generator (intent→parameterized SQL), ontology extension, and agent registration. The approach builds incrementally — config first, then internal services, then the agent, then integration points.

## Tasks

- [x] 1. Set up configuration and data models
  - [x] 1.1 Add Redshift configuration to src/config.py
    - Add `REDSHIFT_AGENT_PORT = 8011` and `REDSHIFT_AGENT_URL = f"http://localhost:{REDSHIFT_AGENT_PORT}"` constants
    - Add `RedshiftConfig` Pydantic model with fields: cluster_id, database, db_user, region (all with env var loading and defaults as specified in design)
    - Add `get_redshift_data_client()` helper that returns a boto3 `redshift-data` client using `get_boto3_session()`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6_

  - [x] 1.2 Create Redshift data models in src/models/redshift_models.py
    - Define `RedshiftResult` model: columns (list[dict[str, str]]), rows (list[list[Any]]), row_count (int), statement_id (str)
    - Define `RedshiftError` model: error_type (Literal["TIMEOUT", "AUTH_FAILURE", "QUERY_FAILURE", "CONNECTION_ERROR"]), description (str), elapsed_seconds (float | None)
    - Define `ColumnClassification` enum (categorical, numeric, identifier)
    - Define `ColumnDef`, `FilterMapping`, `TableMapping`, `GeneratedQuery`, `SQLGeneratorError` models as specified in design
    - _Requirements: 2.7, 3.6, 8.1, 8.2, 8.3_

- [x] 2. Implement Schema Registry
  - [x] 2.1 Create src/services/schema_registry.py
    - Implement `SchemaRegistry` class with `SCHEMA_MAPPINGS` list containing all 3 table mappings (sales_transactions, customer_segments, employee_performance) with full column definitions and filter mappings as specified in design
    - Implement `resolve(entity_ref: str) -> TableMapping | None` method
    - Implement `get_numeric_columns(table_name: str) -> list[ColumnDef]` method
    - Implement `get_categorical_columns(table_name: str) -> list[ColumnDef]` method
    - Implement `validate_against_redshift(connector) -> list[str]` method that queries Redshift information_schema to verify tables exist
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 2.2 Write property test for Schema Registry structural completeness (Property 11)
    - **Property 11: Schema Registry structural completeness**
    - Verify every column has exactly one classification, every filter mapping references an existing column, and every filter mapping has a valid operator
    - **Validates: Requirements 8.1, 8.2, 8.3**

- [x] 3. Implement SQL Generator
  - [x] 3.1 Create src/services/sql_generator.py
    - Implement `SQLGenerator` class with `__init__(self, schema_registry: SchemaRegistry)`
    - Implement `generate(intent: StructuredIntent) -> GeneratedQuery | SQLGeneratorError` method that resolves entity_refs via schema registry, selects query strategy by query_type, handles unresolved entities and multi-table cases
    - Implement `_generate_lookup` producing `SELECT ... WHERE ... LIMIT 1000`
    - Implement `_generate_aggregation` producing `SELECT aggregate(numeric_cols) ... GROUP BY categorical_cols` (default to SUM when routing_metadata lacks aggregate function)
    - Implement `_generate_comparison` producing `SELECT first_categorical, SUM(numeric_cols) ... GROUP BY first_categorical`
    - All filter values MUST use parameterized queries (never string interpolation)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9_

  - [ ]* 3.2 Write property test for SQL syntactic validity (Property 1)
    - **Property 1: Generated SQL is syntactically valid**
    - For any valid StructuredIntent with resolvable entity_refs, verify the generated SQL parses without error
    - **Validates: Requirements 3.9**

  - [ ]* 3.3 Write property test for SQL structure matching query type (Property 2)
    - **Property 2: SQL structure matches query type**
    - Verify lookup produces SELECT+WHERE+LIMIT, aggregation produces aggregate function+GROUP BY, comparison produces GROUP BY first categorical + SUM
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [ ]* 3.4 Write property test for SQL injection prevention (Property 3)
    - **Property 3: Parameterized queries prevent SQL injection**
    - For any string filter value (including SQL keywords, quotes, semicolons, comment sequences), verify it never appears interpolated in the SQL string and only appears in the parameters list
    - **Validates: Requirements 3.4**

  - [ ]* 3.5 Write property test for unresolved entity_ref error handling (Property 4)
    - **Property 4: Unresolved entity_refs produce errors**
    - For any entity_ref not in the Schema Registry, verify SQLGeneratorError with error_type "UNRESOLVED_ENTITY" is returned
    - **Validates: Requirements 3.6**

  - [ ]* 3.6 Write property test for multi-table entity_ref resolution (Property 5)
    - **Property 5: Multi-table entity_refs resolve to first table only**
    - For intents with entity_refs spanning multiple tables, verify SQL references only the first resolved table
    - **Validates: Requirements 3.7**

- [x] 4. Implement Redshift Connector
  - [x] 4.1 Create src/services/redshift_connector.py
    - Implement `RedshiftConnector` class with `__init__(self, config: RedshiftConfig)`
    - Implement `async execute_statement(sql, parameters) -> RedshiftResult | RedshiftError` using boto3 redshift-data `execute_statement` API
    - Implement `_poll_statement(statement_id) -> str` with intervals between 500ms-2s, max 30s timeout; cancel statement on timeout
    - Implement `_get_result_set(statement_id) -> RedshiftResult` to retrieve column metadata and row data
    - Implement `async validate_connectivity() -> bool` that runs a simple test query
    - Handle error classification: TIMEOUT (>30s), AUTH_FAILURE (credential errors), QUERY_FAILURE (execution errors), CONNECTION_ERROR (network failures)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_

  - [ ]* 4.2 Write property test for result parsing (Property 6)
    - **Property 6: Result parsing preserves column metadata and rows**
    - For any valid Redshift Data API response, verify RedshiftResult has matching column count and each row has exactly as many values as columns
    - **Validates: Requirements 2.7**

  - [ ]* 4.3 Write property test for polling constraints (Property 7)
    - **Property 7: Polling respects interval and timeout constraints**
    - Verify polling waits between 500ms-2s between polls, does not exceed 30s total, and returns TIMEOUT error when exceeded
    - Use mocked time for deterministic testing
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 4.4 Write unit tests for Redshift Connector error classification
    - Test AUTH_FAILURE error when credentials are invalid
    - Test QUERY_FAILURE error for SQL execution failures
    - Test CONNECTION_ERROR for network issues
    - Test TIMEOUT error when statement exceeds 30s
    - _Requirements: 2.4, 2.5, 2.8_

- [ ] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Redshift Spoke Agent
  - [x] 6.1 Create src/agents/redshift_spoke_agent.py
    - Implement FastAPI application with `AGENT_ID = "redshift-spoke-agent"`
    - Implement `POST /agents/redshift-spoke-agent/invoke` endpoint that: validates StructuredIntent, generates SQL via SQLGenerator, executes via RedshiftConnector, formats AgentResult with correct data_type mapping (lookup→tabular, aggregation→aggregation, comparison→comparison)
    - Implement `GET /health` endpoint returning status, service name, port, connected database
    - On startup: validate Redshift connectivity, validate Schema Registry against Redshift, start in degraded state if connectivity fails, fail hard if no tables are available
    - Return INVALID_INTENT error for malformed request bodies
    - Propagate connector errors as AgentResult with appropriate error_type
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ]* 6.2 Write property test for query type to data_type mapping (Property 8)
    - **Property 8: Query type maps to correct data_type in response**
    - For any valid StructuredIntent that executes successfully, verify payload.data_type matches the expected value for each query_type
    - **Validates: Requirements 4.4**

  - [ ]* 6.3 Write property test for invalid intent error handling (Property 9)
    - **Property 9: Invalid request bodies produce INVALID_INTENT errors**
    - For any request body that doesn't conform to StructuredIntent schema, verify AgentResult has status "error" and error_type "INVALID_INTENT"
    - **Validates: Requirements 4.8**

  - [ ]* 6.4 Write unit tests for Redshift Spoke Agent
    - Test health endpoint response structure
    - Test startup connectivity validation (success and failure paths)
    - Test degraded state behavior when Redshift is unavailable
    - Test successful query flow end-to-end (mocked connector)
    - _Requirements: 4.6, 4.7_

- [ ] 7. Extend ontology and register agent
  - [x] 7.1 Add Redshift concepts to data/ontology/enterprise_ontology.json
    - Add `ontology:sales_transactions` concept: domain "finance", data_source "redshift", agent_id "redshift-spoke-agent", aggregatable numeric properties (quantity, total_amount), relationships grouped_by to ontology:region and ontology:product_category
    - Add `ontology:customer_segments` concept: domain "customers", data_source "redshift", agent_id "redshift-spoke-agent", aggregatable numeric properties (lifetime_value, total_orders), relationship grouped_by to ontology:region
    - Add `ontology:employee_performance` concept: domain "hr", data_source "redshift", agent_id "redshift-spoke-agent", aggregatable numeric properties (quarterly_target, quarterly_actual, deals_closed, customer_satisfaction_score), relationship grouped_by to ontology:region
    - Add relationships with relation_type "grouped_by" and join_key properties
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 7.2 Update src/services/register_agents.py to include Redshift agent registration
    - Add Redshift agent entry to `AGENT_REGISTRATIONS` list with agent_id "redshift-spoke-agent", agent_name "Redshift Spoke Agent", data_source "redshift", endpoint_url using REDSHIFT_AGENT_URL from config, entity_refs ["ontology:sales_transactions", "ontology:customer_segments", "ontology:employee_performance"]
    - Import REDSHIFT_AGENT_URL from src.config
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 7.3 Write property test for orchestrator routing (Property 10)
    - **Property 10: Orchestrator resolves Redshift agent for Redshift entity_refs**
    - For any StructuredIntent containing at least one Redshift entity_ref, verify the orchestrator's agent resolution includes "redshift-spoke-agent"
    - **Validates: Requirements 6.2**

  - [ ]* 7.4 Write unit tests for ontology and registration
    - Verify ontology JSON contains exactly 3 Redshift concepts with correct structure
    - Verify each concept has data_source "redshift" and agent_id "redshift-spoke-agent"
    - Verify agent registration payload has correct format
    - _Requirements: 5.1, 6.1_

- [ ] 8. Create provisioning script
  - [x] 8.1 Create scripts/provision_redshift.py
    - Implement script that connects to Redshift cluster "talktodata" using RedshiftConnector
    - Create database "analytics" (skip if exists)
    - Create tables: sales_transactions, customer_segments, employee_performance with correct column definitions and types
    - Skip table creation if table already exists (idempotent)
    - Populate each table with 50-200 rows of realistic business data covering all categorical values
    - Output confirmation summary with table count and row counts
    - Handle connection failures gracefully (report error and terminate without partial resources)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

- [ ] 9. Update run_all.py to start Redshift Spoke Agent
  - [x] 9.1 Add Redshift Spoke Agent to application startup
    - Import REDSHIFT_AGENT_PORT from src.config
    - Add entry to start the redshift_spoke_agent process on port 8011
    - Ensure it starts after the orchestrator hub
    - _Requirements: 4.1, 7.6_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 11 universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation uses Python with FastAPI, Pydantic, boto3, and Hypothesis (for property tests) — all already in project dependencies
- boto3 >=1.35.0 is already declared in pyproject.toml

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "4.1", "8.1"] },
    { "id": 2, "tasks": ["2.2", "3.1", "4.2", "4.3", "4.4"] },
    { "id": 3, "tasks": ["3.2", "3.3", "3.4", "3.5", "3.6"] },
    { "id": 4, "tasks": ["6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "7.1", "7.2"] },
    { "id": 6, "tasks": ["7.3", "7.4", "9.1"] }
  ]
}
```
