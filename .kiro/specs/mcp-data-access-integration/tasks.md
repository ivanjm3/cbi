# Implementation Plan: MCP Data Access Integration

## Overview

Implement the MCP Adapter Layer as a FastAPI service (port 8012) that bridges the Orchestrator Hub with the production-ready `mcp-redshift` and `mcp-s3` servers. The adapter registers as spoke agents (`mcp-redshift-adapter`, `mcp-s3-adapter`), translates StructuredIntent payloads into MCP tool calls, and transforms responses back into AgentResult format. Feature flags control gradual migration from legacy spoke agents to MCP-based data access.

## Tasks

- [ ] 1. Set up MCP Adapter module structure, configuration, and data models
  - [ ] 1.1 Create the MCP Adapter module directory and configuration models
    - Create `src/agents/mcp_adapter/` directory with `__init__.py`
    - Create `src/agents/mcp_adapter/config.py` with `MCPServerConfig` and `MCPAdapterConfig` Pydantic models
    - Implement environment variable parsing with `MCP_ADAPTER_REDSHIFT_` and `MCP_ADAPTER_S3_` prefixes
    - Validate TRANSPORT (must be "stdio" or "streamable-http", default "stdio"), TIMEOUT (1-300, default 30), PORT (1024-65535 for streamable-http), HOST, and COMMAND
    - Mark server as unavailable when required env vars are missing or transport is invalid
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8_

  - [ ]* 1.2 Write property test for configuration parsing (Property 12)
    - **Property 12: Configuration parsing validates and applies env vars correctly**
    - Generate random env var combinations with Hypothesis; verify TRANSPORT defaults to "stdio", TIMEOUT clamps to 1-300, missing required vars mark server unavailable, invalid TRANSPORT marks server unavailable
    - **Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.7, 9.8**

  - [ ] 1.3 Create routing and response data models
    - Create `src/agents/mcp_adapter/models.py` with `RoutingTarget`, `MCPToolResult` models
    - `RoutingTarget` includes server_id ("redshift" or "s3"), dataset_name, table_name, entity_refs
    - `MCPToolResult` includes success, content, error_message, tool_name, server_id, duration_ms
    - _Requirements: 2.10, 3.5, 3.6_

- [ ] 2. Implement MCPClientManager for server connections
  - [ ] 2.1 Implement MCPClientManager with connection lifecycle
    - Create `src/agents/mcp_adapter/client_manager.py`
    - Implement `connect()` using official `mcp` Python SDK — `StdioClientTransport` for stdio, `StreamableHTTPClientTransport` for streamable-http
    - Implement 10-second connection timeout, available/unavailable state tracking
    - Implement `call_tool(tool_name, arguments)` that invokes tools on the connected MCP server session
    - Implement `disconnect()` with 5-second graceful shutdown, cancelling in-flight tool calls
    - Implement `_reconnect_loop()` with 30-second intervals, max 10 attempts, restoring available status on success
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 1.6, 1.7_

  - [ ]* 2.2 Write unit tests for MCPClientManager
    - Test connection success/failure paths with mocked MCP SDK
    - Test reconnect loop timing and max attempts
    - Test graceful disconnect cancels in-flight calls
    - Test available/unavailable state transitions
    - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7_

- [ ] 3. Implement IntentRouter for entity_ref resolution
  - [ ] 3.1 Implement IntentRouter
    - Create `src/agents/mcp_adapter/intent_router.py`
    - Inject `OntologyStore` dependency, resolve each entity_ref by calling `ontology_store.lookup_concept()` and reading the `data_source` property
    - Map "s3" / financial data sources to mcp-s3 server with appropriate dataset_name ("financial_data" or "product_catalog")
    - Map "redshift" data sources to mcp-redshift server
    - Return `UNROUTABLE_ENTITY` error with unresolved entity_ref IDs when no entity resolves
    - _Requirements: 2.4, 2.5, 2.10, 2.11_

  - [ ]* 3.2 Write property test for entity-ref routing (Property 1)
    - **Property 1: Entity-ref routing resolves to correct MCP server and dataset**
    - Generate random valid entity_refs from a known set; verify routing to correct server_id and dataset_name
    - **Validates: Requirements 2.4, 2.5, 2.10, 6.1, 6.2**

  - [ ]* 3.3 Write property test for unresolvable entity_refs (Property 15)
    - **Property 15: Unresolvable entity_refs produce UNROUTABLE_ENTITY error**
    - Generate random entity_refs not in OntologyStore; verify AgentResult with error_type "UNROUTABLE_ENTITY"
    - **Validates: Requirements 2.11**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement RedshiftTranslator with SQL generation reuse
  - [ ] 5.1 Implement RedshiftTranslator
    - Create `src/agents/mcp_adapter/redshift_translator.py`
    - Inject `SQLGenerator` and `MCPClientManager` dependencies
    - Call `SQLGenerator.generate(intent)` to produce a `GeneratedQuery` or `SQLGeneratorError`
    - On `GeneratedQuery`: invoke MCP `execute_parameterized_query` tool with the SQL string and parameters list
    - On `SQLGeneratorError`: return error AgentResult directly without calling MCP
    - Implement `_schema_cache` for table column definitions; on cache miss, call `describe_table` tool before SQL generation
    - _Requirements: 2.1, 2.2, 2.3, 2.7, 5.1, 5.2, 5.3, 5.5, 5.6_

  - [ ]* 5.2 Write property test for SQL generation reuse (Property 2)
    - **Property 2: SQL generation reuse — adapter passes SQLGenerator output to MCP execute tool**
    - Generate random valid StructuredIntents targeting Redshift; verify SQLGenerator.generate() is called and its output is passed to execute_parameterized_query
    - **Validates: Requirements 2.1, 2.2, 2.3, 5.1, 5.2**

  - [ ]* 5.3 Write property test for SQLGeneratorError short-circuit (Property 3)
    - **Property 3: SQLGeneratorError short-circuits without MCP invocation**
    - Generate random intents producing SQLGeneratorError; verify error AgentResult returned and no MCP call made
    - **Validates: Requirements 5.6**

- [ ] 6. Implement S3Translator with pagination and local aggregation
  - [ ] 6.1 Implement S3Translator
    - Create `src/agents/mcp_adapter/s3_translator.py`
    - Inject `MCPClientManager` dependency
    - Implement `execute()` that calls `read_dataset` with the resolved dataset name
    - Implement pagination loop: continue calling `read_dataset` with incremented offset while `has_more` is true, up to `max_row_limit` (10000)
    - Implement schema cache: on cache miss, call `get_schema` or `sample_dataset` to infer column types
    - Optionally call `get_semantic_metadata` for dimension/measure selection when available
    - For query_type "aggregation": compute sum, avg, min, max, count for each numeric column
    - For query_type "comparison": group by "category" (or first string column excluding identifiers), compute sum and avg per numeric column per group
    - _Requirements: 2.4, 2.5, 2.8, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 6.2 Write property test for S3 pagination (Property 8)
    - **Property 8: S3 pagination retrieves all rows up to max_row_limit**
    - Generate datasets of varying sizes; verify pagination accumulates all rows up to 10000 limit
    - **Validates: Requirements 6.3**

  - [ ]* 6.3 Write property test for S3 aggregation (Property 9)
    - **Property 9: S3 aggregation computes correct numeric summaries**
    - Generate random numeric row data; verify sum, avg, min, max, count match expected math
    - **Validates: Requirements 6.4**

  - [ ]* 6.4 Write property test for S3 comparison (Property 10)
    - **Property 10: S3 comparison groups by correct column and computes per-group aggregates**
    - Generate random rows with a categorical column; verify grouping logic and per-group sum/avg correctness
    - **Validates: Requirements 6.5**

- [ ] 7. Implement ResponseTransformer
  - [ ] 7.1 Implement ResponseTransformer
    - Create `src/agents/mcp_adapter/response_transformer.py`
    - Implement `from_redshift_query()`: transform execute_query/execute_parameterized_query result into AgentResult with data_type "tabular", columns, rows, row_count from pagination.total_count
    - Implement `from_s3_read()`: transform accumulated rows into AgentResult with data_type based on query_type
    - Implement `error_result()`: produce error AgentResult from MCP failure with server_id, tool_name, error_description
    - Set agent_id to "mcp-redshift-adapter" or "mcp-s3-adapter", data_source to "mcp-redshift" or "mcp-s3"
    - Handle empty row arrays for Redshift (status "success", empty rows, columns preserved, row_count 0)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [ ]* 7.2 Write property test for MCP response transformation (Property 4)
    - **Property 4: MCP response to AgentResult transformation preserves data**
    - Generate random MCP tool responses; verify AgentResult fields match expected values
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.5, 3.6, 3.8**

  - [ ]* 7.3 Write property test for MCP error responses (Property 5)
    - **Property 5: MCP error responses produce correctly-structured error AgentResults**
    - Generate random error MCP responses; verify error AgentResult with "MCP_TOOL_ERROR" type
    - **Validates: Requirements 2.9, 3.4**

  - [ ]* 7.4 Write property test for AgentResult schema conformance (Property 14)
    - **Property 14: All adapter responses conform to AgentResult schema**
    - Generate random intents through the full adapter flow (mocked); verify every response is valid AgentResult
    - **Validates: Requirements 8.3**

- [ ] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement FallbackHandler and error handling
  - [ ] 9.1 Implement FallbackHandler
    - Create `src/agents/mcp_adapter/fallback_handler.py`
    - Inject legacy endpoint URLs (S3 spoke agent port 8010, Redshift spoke agent port 8011)
    - Implement `dispatch()` that POSTs StructuredIntent to legacy spoke agent's `/agents/{agent_id}/invoke` endpoint
    - Propagate X-Correlation-ID header to legacy agent
    - Handle connection reset: attempt one reconnect within 3 seconds before falling back
    - Return `DUAL_PATH_FAILURE` error when both MCP and legacy agent fail
    - Log warnings on all fallback events with correlation_id, server_name, failure reason
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [ ]* 9.2 Write property test for unavailable MCP server fallback (Property 7)
    - **Property 7: Unavailable MCP server routes all requests to legacy spoke agent**
    - Mark MCP server unavailable; generate random intents; verify legacy agent is called without MCP attempts
    - **Validates: Requirements 1.4, 7.1, 7.2**

- [ ] 10. Implement MCPAdapterService FastAPI application
  - [ ] 10.1 Implement MCPAdapterService FastAPI app
    - Create `src/agents/mcp_adapter/service.py` with FastAPI app on port 8012
    - Implement lifespan: initialize MCPClientManagers for both servers, IntentRouter, RedshiftTranslator, S3Translator, ResponseTransformer, FallbackHandler
    - Implement `POST /agents/mcp-redshift-adapter/invoke` endpoint
    - Implement `POST /agents/mcp-s3-adapter/invoke` endpoint
    - Implement `GET /health` endpoint with MCP server availability status
    - Check cancellation registry before each outbound MCP invocation
    - Return `QUERY_CANCELLED` AgentResult when cancellation detected
    - Propagate X-Correlation-ID through all MCP tool calls
    - _Requirements: 8.1, 8.2, 8.3, 8.5, 8.6, 8.7, 7.5_

  - [ ]* 10.2 Write property test for cancellation handling (Property 11)
    - **Property 11: Cancelled requests produce QUERY_CANCELLED without further MCP calls**
    - Generate random intents with cancelled correlation_id; verify QUERY_CANCELLED returned and no MCP calls
    - **Validates: Requirements 8.5, 8.6**

  - [ ]* 10.3 Write property test for correlation-ID propagation (Property 13)
    - **Property 13: Correlation-ID propagation through MCP tool calls**
    - Generate random requests with correlation_id; verify all outbound MCP calls include it
    - **Validates: Requirements 7.5**

- [ ] 11. Implement FeatureFlagRouter and Orchestrator integration
  - [ ] 11.1 Implement FeatureFlagRouter in orchestrator
    - Create `src/services/feature_flag_router.py`
    - Implement `should_use_mcp(data_source)` that reads env vars per-request: `USE_MCP_REDSHIFT`, `USE_MCP_S3`, `USE_MCP_ADAPTER`
    - Per-datasource flag overrides global flag; global flag defaults to `false`
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ] 11.2 Integrate FeatureFlagRouter into OrchestratorHub
    - Modify `src/services/orchestrator_hub.py` to check `FeatureFlagRouter.should_use_mcp()` before agent resolution
    - When MCP is enabled for a data_source, route to the MCP Adapter endpoint instead of legacy spoke agents
    - Return `MCP_ADAPTER_UNAVAILABLE` error if MCP Adapter is unreachable when flag is true
    - _Requirements: 4.2, 4.3, 4.7_

  - [ ]* 11.3 Write property test for feature flag routing (Property 6)
    - **Property 6: Feature flag routing decision follows precedence rules**
    - Generate random flag combinations (USE_MCP_ADAPTER, USE_MCP_REDSHIFT, USE_MCP_S3); verify per-datasource overrides global, default is legacy
    - **Validates: Requirements 4.2, 4.3, 4.5, 4.6**

- [ ] 12. Implement agent registration with Orchestrator
  - [ ] 12.1 Register MCP adapter agents with the Orchestrator Hub
    - Modify `src/services/register_agents.py` to conditionally register `mcp-redshift-adapter` and `mcp-s3-adapter` with the Orchestrator Hub
    - Use the same `AgentRegistration` interface: agent_id, agent_name, data_source, endpoint_url (port 8012), entity_refs
    - Assign Redshift entity_refs (workforce_metrics, support_tickets, marketing_campaigns) to `mcp-redshift-adapter`
    - Assign S3 entity_refs (financial + product entities) to `mcp-s3-adapter`
    - Registration only occurs when USE_MCP_ADAPTER or per-datasource flags are enabled
    - _Requirements: 8.1, 8.4_

- [ ] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Update system documentation
  - [ ] 14.1 Update docs/SYSTEM_OVERVIEW.md with MCP architecture
    - Add MCP data flow architecture diagram showing both MCP and legacy paths with feature flag as decision point
    - Add MCP Adapter Layer to service ports table (port 8012)
    - Add MCP Adapter to project structure file reference section
    - Update query lifecycle data flow section to include MCP path
    - Document feature flag mechanism: flag names, default values, configuration method, toggle steps
    - Document MCP tools invoked by the adapter with their StructuredIntent query_type mappings
    - Document fallback behavior including conditions and reconnection attempts
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Unit tests validate specific examples and edge cases
- The adapter reuses existing `SQLGenerator` and `OntologyStore` — no new SQL generators or data clients are created
- All MCP communication uses the official Python `mcp` SDK package
- The adapter runs on port 8012, same network as existing spoke agents (8010, 8011)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "3.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "5.1"] },
    { "id": 4, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 5, "tasks": ["6.2", "6.3", "6.4", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3", "7.4", "9.1"] },
    { "id": 7, "tasks": ["9.2", "10.1"] },
    { "id": 8, "tasks": ["10.2", "10.3", "11.1"] },
    { "id": 9, "tasks": ["11.2", "11.3", "12.1"] },
    { "id": 10, "tasks": ["14.1"] }
  ]
}
```
