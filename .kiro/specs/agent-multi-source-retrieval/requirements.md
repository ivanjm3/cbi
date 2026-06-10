# Requirements Document

## Introduction

This feature upgrades the existing Conversational BI system from deterministic ontology-driven data retrieval (S3-only) to an intelligent agent-powered multi-source data retrieval architecture. An orchestrating agent will interpret vague or ambiguous user prompts, reason about the ontology, and intelligently route queries to the appropriate data source connectors (RDS PostgreSQL/MySQL, DynamoDB, S3 CSV files, and log files). The architecture introduces a clean separation between a containerized frontend (ECS-deployable) and a backend composed of specialized intelligent agents.

## Glossary

- **Query_Planner_Agent**: The central intelligent agent that interprets user prompts, reasons about the ontology and available data sources, decomposes queries into sub-tasks, and produces an execution plan for data retrieval.
- **Data_Source_Connector**: A modular component that executes queries against a specific data source type (RDS, DynamoDB, S3 CSV, or log files) and returns structured results.
- **Source_Registry**: A configuration store that maintains metadata about all registered data sources including connection parameters, schemas, and the ontology concepts each source provides.
- **Execution_Plan**: A structured specification produced by the Query_Planner_Agent describing which data sources to query, in what order, and how to combine results.
- **Schema_Descriptor**: Metadata describing the structure (columns, types, relationships) of a registered data source, used by the Query_Planner_Agent for informed routing.
- **Result_Assembler**: A component that merges, joins, or aggregates results from multiple data source queries into a unified response.
- **Frontend_Container**: The React application packaged as a Docker container, deployable on ECS with a well-defined API contract to the backend.
- **Backend_Agent_API**: The unified FastAPI gateway that exposes the agent-based backend to the frontend, handling session management and request routing to agents.
- **Ontology_Reasoner**: The subsystem within the Query_Planner_Agent that uses ontology graph relationships to infer which data sources contain relevant information for a given query, even when the query is vague.

## Requirements

### Requirement 1: Intelligent Query Understanding

**User Story:** As a business user, I want to ask vague or imprecise questions in natural language, so that the system intelligently interprets my intent and retrieves relevant data without requiring me to know the underlying data structure.

#### Acceptance Criteria

1. WHEN a user submits a natural language query, THE Query_Planner_Agent SHALL parse the query and produce a structured Execution_Plan within 5 seconds.
2. WHEN a query contains ambiguous terms that map to multiple ontology concepts, THE Query_Planner_Agent SHALL use ontology relationships and source metadata to select the most relevant interpretation.
3. WHEN a query is too vague to resolve to any data source, THE Query_Planner_Agent SHALL return a clarification request listing the possible interpretations and relevant data domains.
4. THE Query_Planner_Agent SHALL support all three existing query types (lookup, aggregation, comparison) and additionally support cross-source join queries.
5. WHEN a query references concepts spanning multiple data sources, THE Query_Planner_Agent SHALL decompose the query into sub-tasks targeting each relevant source and define a merge strategy in the Execution_Plan.

### Requirement 2: Multi-Source Data Retrieval

**User Story:** As a data analyst, I want the system to pull data from RDS databases, DynamoDB tables, S3 CSV files, and log files, so that I can get a unified view across all my organization's data stores.

#### Acceptance Criteria

1. THE Data_Source_Connector for RDS SHALL execute parameterized SQL queries against PostgreSQL and MySQL databases and return tabular results.
2. THE Data_Source_Connector for DynamoDB SHALL execute scan and query operations with filter expressions and return item collections.
3. THE Data_Source_Connector for S3 SHALL parse CSV files from configured S3 paths and return tabular results with type coercion.
4. THE Data_Source_Connector for log files SHALL parse structured log entries (JSON lines, common log format) from S3 or local paths and return filtered results.
5. WHEN a Data_Source_Connector encounters a connection failure, THE Data_Source_Connector SHALL return a structured error with the source identifier, error type, and a human-readable description within 10 seconds.
6. THE Data_Source_Connector for RDS SHALL use connection pooling with a configurable maximum pool size per database.

### Requirement 3: Source Registry and Schema Discovery

**User Story:** As a system administrator, I want to register and configure data sources with their schemas, so that the agent can discover and reason about available data without hardcoded source knowledge.

#### Acceptance Criteria

1. THE Source_Registry SHALL store data source configurations including connection parameters, source type, and associated ontology concept mappings.
2. THE Source_Registry SHALL store a Schema_Descriptor for each registered source describing columns, data types, and relationships.
3. WHEN a new data source is registered, THE Source_Registry SHALL validate connectivity by performing a lightweight health check against the source.
4. WHEN a data source is deregistered, THE Source_Registry SHALL remove the source from routing consideration within 5 seconds.
5. THE Source_Registry SHALL expose a query interface that returns all sources matching a given set of ontology concept identifiers.
6. THE Source_Registry SHALL support runtime addition and removal of data sources without requiring a system restart.

### Requirement 4: Ontology-Aware Routing

**User Story:** As a business user, I want the system to use its knowledge of business concepts and data relationships to automatically find the right data source, so that I do not need to know where data is physically stored.

#### Acceptance Criteria

1. THE Ontology_Reasoner SHALL traverse ontology relationships to infer which data sources contain information relevant to resolved entity references.
2. WHEN entity references from a query map to multiple registered sources, THE Ontology_Reasoner SHALL rank sources by relevance using relationship proximity in the ontology graph.
3. WHEN a query contains domain terms not directly in the ontology, THE Ontology_Reasoner SHALL use semantic similarity against concept labels and synonyms to find the closest matching concepts.
4. THE Ontology_Reasoner SHALL use Schema_Descriptors from the Source_Registry to validate that a candidate source can actually provide the requested data fields.

### Requirement 5: Execution Plan Generation and Execution

**User Story:** As a data analyst, I want the system to intelligently plan and execute multi-source queries, so that I get combined results from different databases in a single response.

#### Acceptance Criteria

1. THE Query_Planner_Agent SHALL generate an Execution_Plan specifying: target sources, query parameters per source, execution order, and merge strategy.
2. WHEN an Execution_Plan targets multiple independent sources, THE Query_Planner_Agent SHALL dispatch queries to those sources concurrently.
3. WHEN an Execution_Plan contains dependent sub-tasks (one source's result feeds another), THE Query_Planner_Agent SHALL execute them sequentially in dependency order.
4. THE Result_Assembler SHALL merge results from multiple sources using the merge strategy defined in the Execution_Plan (union, join, or aggregate).
5. IF a source query within an Execution_Plan fails, THEN THE Result_Assembler SHALL return partial results from successful sources with a clear indication of which sources failed and why.
6. THE Execution_Plan SHALL be serializable to JSON for logging, debugging, and replay purposes.

### Requirement 6: Frontend-Backend Separation

**User Story:** As a DevOps engineer, I want a clean API contract between the frontend and backend, so that the frontend can be independently deployed on ECS and the backend can evolve its agent architecture without breaking the UI.

#### Acceptance Criteria

1. THE Backend_Agent_API SHALL expose a versioned REST API (v1) that the Frontend_Container communicates with exclusively.
2. THE Backend_Agent_API SHALL accept natural language queries via POST and return unified response objects containing data payloads, visualization hints, and metadata.
3. THE Frontend_Container SHALL be packaged as a Docker image with a multi-stage build (build + nginx serve) suitable for ECS deployment.
4. THE Backend_Agent_API SHALL support CORS configuration for cross-origin requests from the Frontend_Container.
5. WHEN the backend agents are processing a query, THE Backend_Agent_API SHALL provide a streaming or polling mechanism so the frontend can display progress to the user.
6. THE Frontend_Container SHALL use environment variables for the backend API URL, enabling deployment to different environments without rebuilding.

### Requirement 7: Agent Architecture

**User Story:** As a platform architect, I want the backend to be structured as a set of cooperating intelligent agents, so that the system is modular, extensible, and each agent can be evolved independently.

#### Acceptance Criteria

1. THE Backend_Agent_API SHALL route incoming queries to the Query_Planner_Agent as the entry point for all data retrieval requests.
2. THE Query_Planner_Agent SHALL use the Strands SDK agent framework with tool-calling to invoke Data_Source_Connectors as tools.
3. THE Query_Planner_Agent SHALL maintain conversational context within a session to handle follow-up queries that reference prior results.
4. WHEN a new Data_Source_Connector type is added, THE system SHALL require only registering the connector as a Strands tool and adding its Schema_Descriptor to the Source_Registry.
5. THE Query_Planner_Agent SHALL include the ontology context and Schema_Descriptors in its system prompt so the LLM can reason about data source selection.
6. THE Backend_Agent_API SHALL implement health check endpoints for each agent and connector, enabling container orchestration liveness and readiness probes.

### Requirement 8: Backward Compatibility

**User Story:** As an existing user, I want my current queries that work with the S3-based system to continue working after the upgrade, so that there is no regression in functionality.

#### Acceptance Criteria

1. THE system SHALL support all existing ontology concepts and entity references from the current S3-based data sources without modification.
2. WHEN a query resolves to the existing S3 financial data or product catalog, THE system SHALL return results in the same payload structure as the current spoke agent.
3. THE system SHALL preserve the existing visualization pipeline (guardrail validation and Chart.js rendering) for all query results regardless of source.
4. THE Backend_Agent_API SHALL accept the same query request format as the current NLP API (POST with query_text field) to maintain frontend compatibility during migration.

### Requirement 9: Observability and Error Handling

**User Story:** As an operations engineer, I want full visibility into the agent's decision-making process and data retrieval operations, so that I can diagnose issues and optimize performance.

#### Acceptance Criteria

1. THE Query_Planner_Agent SHALL log the generated Execution_Plan (as JSON) for every query, including source selection reasoning.
2. WHEN a Data_Source_Connector query exceeds a configurable timeout (default 30 seconds), THE connector SHALL terminate the query and return a timeout error.
3. THE Backend_Agent_API SHALL propagate correlation IDs from incoming requests through all agent invocations and connector calls.
4. IF the Query_Planner_Agent fails to generate an Execution_Plan, THEN THE system SHALL fall back to the existing deterministic ontology-based routing as a degraded mode.
5. THE system SHALL track and log per-query metrics including: total latency, per-source latency, number of sources consulted, and LLM token usage.
