# Requirements Document

## Introduction

Refactor the Conversational BI platform to use Model Context Protocol (MCP) servers as the primary data access mechanism. The existing spoke agents (S3 Spoke Agent on port 8010 and Redshift Spoke Agent on port 8011) currently access data sources directly via boto3 S3 `get_object` and the Redshift Data API respectively. This feature introduces an MCP Adapter Layer that routes all data access through the production-ready `mcp-redshift` (9 tools) and `mcp-s3` (8 tools) servers in `mcps/`, transforming the application from a datasource consumer into an MCP consumer.

The migration is gradual: existing functionality continues working throughout the transition via a feature-flag-based routing strategy, and no new datasource access layers, Redshift clients, S3 clients, SQL generators, or dataset readers are created.

## Glossary

- **MCP_Adapter_Layer**: A new module that acts as an MCP client, translating StructuredIntent payloads into MCP tool calls and converting MCP tool responses back into AgentResult format compatible with the existing visualization pipeline.
- **MCP_Client**: A client component within the MCP_Adapter_Layer that communicates with MCP servers using the stdio or streamable-http transport protocol defined by the Model Context Protocol.
- **MCP_Redshift_Server**: The production-ready MCP server at `mcps/mcp-redshift` providing 9 read-only tools for Amazon Redshift access (list_schemas, list_tables, describe_table, execute_query, execute_parameterized_query, explain_query, get_table_statistics, get_relationships, get_semantic_metadata).
- **MCP_S3_Server**: The production-ready MCP server at `mcps/mcp-s3` providing 8 tools for S3 dataset access (list_datasets, describe_dataset, get_schema, sample_dataset, read_dataset, read_partition, get_dataset_statistics, get_semantic_metadata).
- **Orchestrator_Hub**: The central routing agent (port 8002) that resolves spoke agents from entity_refs and dispatches structured intents.
- **Spoke_Agent**: A data retrieval service that receives StructuredIntent payloads and returns AgentResult responses. Currently implemented as the S3 Spoke Agent (port 8010) and Redshift Spoke Agent (port 8011).
- **StructuredIntent**: The canonical intermediate format containing query_id, query_type, entity_refs, routing_metadata, and timestamp, used as the contract between NLP translation and data retrieval.
- **AgentResult**: The standard response format containing status, payload, agent_id, data_source, and optional error fields, consumed by the Guardrail Layer and Visualization Renderer.
- **Feature_Flag**: A configuration-driven toggle that controls whether data access routes through the legacy spoke agents or the new MCP_Adapter_Layer.
- **FastMCP**: The Python MCP framework used by both MCP servers, supporting stdio and streamable-http transports.

## Requirements

### Requirement 1: MCP Client Connection Management

**User Story:** As a platform operator, I want the system to establish and manage connections to MCP servers, so that data access requests can be routed through the MCP protocol.

#### Acceptance Criteria

1. WHEN the MCP_Adapter_Layer starts, THE MCP_Client SHALL establish a connection to the MCP_Redshift_Server using the configured transport (stdio or streamable-http) within a connection timeout of 10 seconds.
2. WHEN the MCP_Adapter_Layer starts, THE MCP_Client SHALL establish a connection to the MCP_S3_Server using the configured transport (stdio or streamable-http) within a connection timeout of 10 seconds.
3. IF the MCP_Client fails to connect to an MCP server, THEN THE MCP_Adapter_Layer SHALL log the connection failure including the server name, transport mode, and error reason, and mark that server as unavailable.
4. WHILE an MCP server connection is unavailable, THE MCP_Adapter_Layer SHALL route requests for that data source through the legacy spoke agent.
5. THE MCP_Client SHALL support both stdio and streamable-http transport modes as configured per server.
6. WHEN the MCP_Adapter_Layer shuts down, THE MCP_Client SHALL close all active MCP server connections within 5 seconds, cancelling any in-flight tool calls that do not complete within that period.
7. WHILE an MCP server connection is marked unavailable, THE MCP_Adapter_Layer SHALL attempt to re-establish the connection at intervals of 30 seconds, up to a maximum of 10 consecutive attempts, and restore the server to available status upon a successful reconnection.

### Requirement 2: StructuredIntent to MCP Tool Call Translation

**User Story:** As the orchestrator, I want the MCP Adapter Layer to translate StructuredIntent payloads into appropriate MCP tool calls, so that data can be retrieved without creating new datasource access layers.

#### Acceptance Criteria

1. WHEN a StructuredIntent with query_type "lookup" targeting Redshift entities is received, THE MCP_Adapter_Layer SHALL invoke the execute_query tool on the MCP_Redshift_Server with a SELECT statement that retrieves rows matching the entity_refs filter values, limited to a maximum of 1000 returned rows.
2. WHEN a StructuredIntent with query_type "aggregation" targeting Redshift entities is received, THE MCP_Adapter_Layer SHALL invoke the execute_query tool on the MCP_Redshift_Server with a SELECT statement applying the aggregate function specified in routing_metadata (one of SUM, AVG, COUNT, MIN, MAX, defaulting to SUM if unspecified) to numeric columns with GROUP BY on all categorical columns.
3. WHEN a StructuredIntent with query_type "comparison" targeting Redshift entities is received, THE MCP_Adapter_Layer SHALL invoke the execute_query tool on the MCP_Redshift_Server with a SELECT statement containing GROUP BY on the first categorical column from entity_refs (the comparison dimension) and SUM applied to numeric columns.
4. WHEN a StructuredIntent targeting S3 financial entities is received, THE MCP_Adapter_Layer SHALL invoke the read_dataset tool on the MCP_S3_Server with the dataset name matching the resolved financial dataset identifier from the entity_refs.
5. WHEN a StructuredIntent targeting S3 product entities is received, THE MCP_Adapter_Layer SHALL invoke the read_dataset tool on the MCP_S3_Server with the dataset name matching the resolved product catalog dataset identifier from the entity_refs.
6. WHEN a StructuredIntent contains entity_refs spanning both Redshift and S3 data sources, THE MCP_Adapter_Layer SHALL invoke tools on both MCP servers concurrently, wait for both responses within the configured timeout, and merge the results by combining column arrays and aligning rows on the first shared column name present in both result sets.
7. WHEN generating SQL for a Redshift query and the target table's column definitions are not present in the local cache, THE MCP_Adapter_Layer SHALL invoke the describe_table tool on the MCP_Redshift_Server to retrieve column definitions before constructing the SQL statement.
8. WHEN reading an S3 dataset and the dataset's column definitions are not present in the local cache, THE MCP_Adapter_Layer SHALL invoke the get_schema tool on the MCP_S3_Server to retrieve column definitions before reading the data.
9. IF an MCP tool invocation returns an error response or fails to respond within the configured timeout, THEN THE MCP_Adapter_Layer SHALL return an error result with the originating MCP server identifier, the tool name that failed, and the error description from the MCP response.
10. THE MCP_Adapter_Layer SHALL determine whether an entity_ref targets Redshift or S3 by resolving the entity_ref against the Ontology_Store and reading the data_source property of the matched concept ("redshift" routes to MCP_Redshift_Server, "s3" routes to MCP_S3_Server).
11. IF a StructuredIntent contains entity_refs that cannot be resolved to any configured MCP server via the Ontology_Store, THEN THE MCP_Adapter_Layer SHALL return an error result with error_type "UNROUTABLE_ENTITY" and include the unresolved entity_ref identifiers.

### Requirement 3: MCP Response to AgentResult Transformation

**User Story:** As the visualization pipeline, I want MCP tool responses transformed into the standard AgentResult format, so that downstream services (Guardrail Layer, Visualization Renderer) continue functioning without modification.

#### Acceptance Criteria

1. WHEN the MCP_Redshift_Server returns a QueryResult via execute_query, THE MCP_Adapter_Layer SHALL transform the response into an AgentResult with status "success", payload containing data_type "tabular", a columns array derived from the QueryResult columns field, a rows array containing the QueryResult row data, and row_count set to the QueryResult pagination.total_count value.
2. WHEN the MCP_S3_Server returns a ReadDatasetOutput via read_dataset, THE MCP_Adapter_Layer SHALL transform the response into an AgentResult with status "success" and data_type set to "tabular" when the original query_type is "lookup", "aggregation" when the original query_type is "aggregation", or "comparison" when the original query_type is "comparison".
3. THE MCP_Adapter_Layer SHALL set the row_count field in all transformed AgentResult payloads to the pagination.total_count value for Redshift responses and to the number of rows in the returned rows array for S3 responses.
4. IF an MCP server tool call returns an error response (isError flag set to true in the MCP protocol response), THEN THE MCP_Adapter_Layer SHALL produce an AgentResult with status "error", error_type set to "MCP_TOOL_ERROR", and error_description set to the text content of the MCP error response.
5. THE MCP_Adapter_Layer SHALL set the agent_id field to "mcp-redshift-adapter" for Redshift responses and "mcp-s3-adapter" for S3 responses.
6. THE MCP_Adapter_Layer SHALL set the data_source field to "mcp-redshift" for responses originating from the MCP_Redshift_Server and "mcp-s3" for responses originating from the MCP_S3_Server.
7. THE MCP_Adapter_Layer SHALL complete the transformation from a valid MCP tool response to an AgentResult within 500 milliseconds.
8. IF the MCP_Redshift_Server returns a QueryResult with an empty rows array, THEN THE MCP_Adapter_Layer SHALL produce an AgentResult with status "success", data_type "tabular", an empty rows array, the columns metadata preserved, and row_count set to 0.

### Requirement 4: Feature Flag Routing

**User Story:** As a platform operator, I want a feature flag to control whether data access routes through MCP servers or legacy spoke agents, so that the migration can proceed gradually without disrupting existing functionality.

#### Acceptance Criteria

1. THE Orchestrator_Hub SHALL support a configuration flag named "use_mcp_adapter" that defaults to false and is readable from the environment variable USE_MCP_ADAPTER or a configuration file entry.
2. WHILE the use_mcp_adapter flag is set to true, THE Orchestrator_Hub SHALL route data requests to the MCP_Adapter_Layer endpoint instead of dispatching to legacy spoke agents via the existing dispatch mechanism.
3. WHILE the use_mcp_adapter flag is set to false, THE Orchestrator_Hub SHALL route data requests to the legacy spoke agents using the existing dispatch mechanism.
4. WHEN the use_mcp_adapter flag value changes in the configuration source, THE Orchestrator_Hub SHALL apply the new routing behavior on the next incoming request without requiring a restart, while requests already in progress continue using the flag value that was active when they started processing.
5. WHERE per-datasource flags are configured (use_mcp_redshift, use_mcp_s3), THE Orchestrator_Hub SHALL route only requests matching that data source's entity_refs to the MCP_Adapter_Layer while routing all other data source requests according to their own per-datasource flag or the global use_mcp_adapter flag.
6. IF both a per-datasource flag and the global use_mcp_adapter flag are configured for the same data source, THEN THE Orchestrator_Hub SHALL use the per-datasource flag value as the effective routing decision for that data source, overriding the global flag.
7. IF the use_mcp_adapter flag is set to true and the MCP_Adapter_Layer is unreachable due to a connection error or timeout, THEN THE Orchestrator_Hub SHALL return an error with error_type "MCP_ADAPTER_UNAVAILABLE" and include the target endpoint in the error description.

### Requirement 5: SQL Generation Reuse via MCP

**User Story:** As a developer, I want SQL generation for Redshift queries to reuse the existing SQL generation logic without creating a new SQL generator, so that the MCP migration does not duplicate functionality.

#### Acceptance Criteria

1. WHEN a StructuredIntent contains entity_refs that resolve to a table in the SchemaRegistry, THE MCP_Adapter_Layer SHALL invoke the existing SQLGenerator.generate() method with that StructuredIntent to produce a GeneratedQuery containing parameterized SQL.
2. WHEN the SQLGenerator produces a GeneratedQuery, THE MCP_Adapter_Layer SHALL invoke the MCP_Redshift_Server execute_parameterized_query tool with the generated SQL string and the parameters list, instead of passing the query to the RedshiftConnector.
3. THE MCP_Adapter_Layer SHALL NOT create a new SQL generation module or Redshift client.
4. THE MCP_Adapter_Layer SHALL NOT create a new S3 client or dataset reader for accessing data.
5. WHEN the MCP_Redshift_Server rejects a query as invalid SQL, THE MCP_Adapter_Layer SHALL return an AgentResult with status "error", error_type "QUERY_EXECUTION_ERROR", and error_description containing the rejection reason returned by the MCP_Redshift_Server.
6. IF the SQLGenerator returns a SQLGeneratorError (such as UNRESOLVED_ENTITY or INVALID_QUERY_TYPE), THEN THE MCP_Adapter_Layer SHALL return an AgentResult with status "error", error_type matching the SQLGeneratorError error_type, and error_description from the SQLGeneratorError description, without invoking the MCP_Redshift_Server.

### Requirement 6: S3 Data Access via MCP

**User Story:** As a developer, I want S3 data access to flow through the mcp-s3 server tools instead of direct boto3 get_object calls, so that all data access is unified through the MCP protocol.

#### Acceptance Criteria

1. WHEN a StructuredIntent contains entity_refs matching financial domain entities (sales_revenue, quarterly_report, order_volume, return_rate, region), THE MCP_Adapter_Layer SHALL invoke read_dataset on the MCP_S3_Server with the dataset parameter set to "financial_data" as registered in the dataset registry.
2. WHEN a StructuredIntent contains entity_refs matching product domain entities (product_catalog, inventory_stock, product_pricing, supplier_info, product_category), THE MCP_Adapter_Layer SHALL invoke read_dataset on the MCP_S3_Server with the dataset parameter set to "product_catalog" as registered in the dataset registry.
3. IF the read_dataset response indicates has_more is true, THEN THE MCP_Adapter_Layer SHALL issue additional read_dataset calls with incremented offset until all rows are retrieved or the configured max_row_limit (10000) is reached.
4. WHEN the query_type is "aggregation", THE MCP_Adapter_Layer SHALL compute sum, avg, min, max, and count for each numeric column in the data returned by the MCP_S3_Server and return an AgentResult with data_type "aggregation".
5. WHEN the query_type is "comparison", THE MCP_Adapter_Layer SHALL identify the grouping column by selecting "category" if present, otherwise the first string-typed column excluding identifier columns (product_id, name, id), then group rows by that column and compute sum and avg for each numeric column per group.
6. WHEN the MCP_Adapter_Layer requires column type information before performing aggregation or comparison and the dataset schema is not already cached, THE MCP_Adapter_Layer SHALL invoke sample_dataset on the MCP_S3_Server with the default sample size to infer column types from the returned rows.
7. IF the MCP_S3_Server supports get_semantic_metadata for the target dataset (returns a response with at least one dimension or measure), THEN THE MCP_Adapter_Layer SHALL use the returned dimensions and measures to select the grouping column and numeric aggregation columns instead of inferring from data types.

### Requirement 7: Error Handling and Fallback

**User Story:** As a platform operator, I want the system to gracefully handle MCP server failures by falling back to legacy spoke agents, so that service availability is maintained during the migration.

#### Acceptance Criteria

1. IF the MCP_Redshift_Server is unavailable (connection refused, health check returns non-200 status, or no response within 5 seconds), THEN THE MCP_Adapter_Layer SHALL fall back to dispatching to the legacy Redshift Spoke Agent for that request.
2. IF the MCP_S3_Server is unavailable (connection refused, health check returns non-200 status, or no response within 5 seconds), THEN THE MCP_Adapter_Layer SHALL fall back to dispatching to the legacy S3 Spoke Agent for that request.
3. IF an MCP tool call does not return a response within the configured timeout period (default: 30 seconds), THEN THE MCP_Adapter_Layer SHALL cancel the pending tool call, log the timeout with the tool name and elapsed duration, and fall back to the legacy spoke agent for that request.
4. WHEN a fallback to a legacy spoke agent occurs, THE MCP_Adapter_Layer SHALL log a warning with the failure reason, the MCP server name, and the correlation_id.
5. THE MCP_Adapter_Layer SHALL propagate the X-Correlation-ID header through all MCP tool calls for observability.
6. IF the MCP_Adapter_Layer encounters a connection reset during a tool call, THEN THE MCP_Adapter_Layer SHALL attempt one reconnection within 3 seconds; IF the reconnection attempt fails or exceeds 3 seconds, THEN THE MCP_Adapter_Layer SHALL fall back to the legacy spoke agent for that request.
7. IF the legacy spoke agent also fails after a fallback dispatch (connection error, timeout, or non-200 response), THEN THE MCP_Adapter_Layer SHALL return an error response to the caller with the correlation_id, the MCP server name, and the legacy agent name, indicating both paths failed.

### Requirement 8: Orchestrator Integration

**User Story:** As the orchestrator, I want to dispatch to the MCP Adapter Layer using the same interface as spoke agents, so that the routing logic remains consistent.

#### Acceptance Criteria

1. THE MCP_Adapter_Layer SHALL register with the Orchestrator_Hub using the same AgentRegistration interface as legacy spoke agents, providing agent_id, agent_name, data_source, endpoint_url, and at least one entity_refs entry.
2. THE MCP_Adapter_Layer SHALL accept StructuredIntent payloads via a POST endpoint at `/agents/{agent_id}/invoke` in the same request format as legacy spoke agents.
3. THE MCP_Adapter_Layer SHALL return AgentResult responses conforming to the same schema as legacy spoke agents, including status, payload, agent_id, and data_source fields.
4. WHEN the MCP_Adapter_Layer is registered, THE Orchestrator_Hub SHALL resolve the MCP_Adapter_Layer based on entity_refs overlap matching identical to legacy agent resolution.
5. WHILE processing an MCP tool call, THE MCP_Adapter_Layer SHALL check the request disconnection state via the cancellation registry before each outbound MCP server invocation.
6. IF the MCP_Adapter_Layer detects that the request has been cancelled, THEN THE MCP_Adapter_Layer SHALL stop processing and return an AgentResult with status "error" and error_type "QUERY_CANCELLED" without invoking further MCP tools.
7. THE MCP_Adapter_Layer SHALL respond to dispatched intents within the same per-agent timeout window (default 30 seconds, configurable 1–300 seconds) enforced by the Orchestrator_Hub for legacy spoke agents.

### Requirement 9: Configuration and Transport

**User Story:** As a platform operator, I want to configure MCP server connection details via environment variables, so that the deployment is flexible across environments.

#### Acceptance Criteria

1. THE MCP_Adapter_Layer SHALL read MCP_Redshift_Server connection settings from environment variables with the prefix MCP_ADAPTER_REDSHIFT_, including at minimum TRANSPORT (value "stdio" or "streamable-http"), HOST, PORT, and COMMAND (the executable path for stdio mode).
2. THE MCP_Adapter_Layer SHALL read MCP_S3_Server connection settings from environment variables with the prefix MCP_ADAPTER_S3_, including at minimum TRANSPORT (value "stdio" or "streamable-http"), HOST, PORT, and COMMAND (the executable path for stdio mode).
3. THE MCP_Adapter_Layer SHALL support configuring the transport mode per MCP server via the TRANSPORT environment variable suffix, accepting exactly one of two values: "stdio" or "streamable-http", defaulting to "stdio" when the variable is not set or is empty.
4. THE MCP_Adapter_Layer SHALL support configuring a per-server timeout value via the TIMEOUT environment variable suffix (e.g., MCP_ADAPTER_REDSHIFT_TIMEOUT), accepting an integer between 1 and 300 seconds inclusive, defaulting to 30 seconds when the variable is not set or is empty.
5. WHEN streamable-http transport is configured for an MCP server, THE MCP_Adapter_Layer SHALL connect to that MCP server using the host from the HOST variable and the port from the PORT variable (integer between 1024 and 65535 inclusive).
6. WHEN stdio transport is configured for an MCP server, THE MCP_Adapter_Layer SHALL launch the MCP server process specified by the COMMAND variable and communicate via stdin/stdout.
7. IF a required environment variable for the configured transport is missing or empty (HOST or PORT for streamable-http, COMMAND for stdio), THEN THE MCP_Adapter_Layer SHALL log an error identifying the missing variable name and mark that MCP server as unavailable at startup.
8. IF the TRANSPORT variable contains a value other than "stdio" or "streamable-http", THEN THE MCP_Adapter_Layer SHALL log an error indicating the invalid transport value and mark that MCP server as unavailable at startup.

### Requirement 10: Documentation Update

**User Story:** As a developer joining the project, I want the system documentation to reflect the new MCP-based architecture, so that the data flow is clear and accurate.

#### Acceptance Criteria

1. THE documentation in docs/SYSTEM_OVERVIEW.md SHALL include an architecture diagram showing both the MCP data flow path (User Query → NLP Translator → Orchestrator → MCP Adapter Layer → MCP_Redshift_Server or MCP_S3_Server → Visualization) and the legacy spoke agent path, with the feature flag as the routing decision point between them.
2. THE documentation SHALL describe the feature flag mechanism by listing all flag names (use_mcp_adapter, use_mcp_redshift, use_mcp_s3), their default values, the configuration method (environment variable or configuration file), and the steps to toggle routing between MCP and legacy spoke agents without requiring a service restart.
3. THE documentation SHALL list each MCP server tool invoked by the MCP_Adapter_Layer (execute_query, execute_parameterized_query, describe_table, get_schema, read_dataset, sample_dataset, get_semantic_metadata) and specify which StructuredIntent query_type values (lookup, aggregation, comparison) each tool serves.
4. THE documentation SHALL describe the fallback behavior when an MCP server is unavailable, including the conditions that trigger fallback to legacy spoke agents and the reconnection attempt before fallback.
5. THE documentation in docs/SYSTEM_OVERVIEW.md SHALL add the MCP_Adapter_Layer to the service ports table, the project structure file reference section, and the query lifecycle data flow section.
