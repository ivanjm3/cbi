# Requirements Document

## Introduction

This feature integrates Amazon Redshift as a new data source for the Conversational BI application. It covers two main areas: (1) provisioning databases and tables in the existing Redshift cluster ("talktodata" in us-east-1) with meaningful business data, and (2) building a new Redshift Spoke Agent that queries Redshift tables and participates in the existing hub-and-spoke orchestration via ontology-based routing. The integration follows the established patterns — a new FastAPI spoke agent registers with the Orchestrator Hub, handles entity_refs for Redshift-backed ontology concepts, and returns AgentResult payloads compatible with the visualization pipeline.

## Glossary

- **Redshift_Cluster**: The Amazon Redshift cluster named "talktodata" in us-east-1 used as the relational data warehouse
- **Redshift_Spoke_Agent**: A new FastAPI microservice that queries Redshift tables and returns AgentResult responses to the Orchestrator Hub
- **Redshift_Connector**: The module responsible for establishing connections and executing SQL queries against the Redshift cluster using the boto3 Redshift Data API
- **Orchestrator_Hub**: The central routing agent that resolves spoke agents from the registry based on entity_ref overlap and dispatches structured intents
- **Ontology_Store**: The service managing ontology concepts with data_source and agent_id properties used for semantic routing
- **Structured_Intent**: The machine-readable representation of a user query containing query_type, entity_refs, and routing_metadata
- **Agent_Result**: The structured response from a spoke agent containing status, payload, agent_id, and data_source fields
- **Redshift_Data_API**: The AWS boto3 service (redshift-data) that executes SQL statements against Redshift without requiring a persistent JDBC connection
- **Schema_Registry**: A configuration mapping that defines available Redshift tables, their columns, and their relationships to ontology concepts
- **SQL_Generator**: The component that translates a Structured_Intent into a valid SQL query based on the Schema_Registry

## Requirements

### Requirement 1: Redshift Database and Schema Provisioning

**User Story:** As a system administrator, I want to create databases and tables in the Redshift cluster with meaningful business data, so that the Conversational BI application has relational data to query.

#### Acceptance Criteria

1. WHEN the provisioning script is executed, THE Redshift_Connector SHALL create a database named "analytics" in the Redshift_Cluster, or proceed without error if the database already exists
2. WHEN the analytics database is created, THE Redshift_Connector SHALL create a "sales_transactions" table with columns: transaction_id, transaction_date, customer_id, product_name, category, region, quantity, unit_price, total_amount, payment_method
3. WHEN the analytics database is created, THE Redshift_Connector SHALL create a "customer_segments" table with columns: customer_id, customer_name, segment, lifetime_value, signup_date, region, total_orders, last_order_date
4. WHEN the analytics database is created, THE Redshift_Connector SHALL create an "employee_performance" table with columns: employee_id, employee_name, department, role, hire_date, region, quarterly_target, quarterly_actual, deals_closed, customer_satisfaction_score
5. WHEN the tables are created, THE Redshift_Connector SHALL populate each table with 50 to 200 rows of business data that covers all distinct values of each categorical column (category, region, segment, department, payment_method) at least once
6. IF the provisioning script encounters a connection failure, THEN THE Redshift_Connector SHALL report the error with the cluster endpoint and error details and terminate without creating partial resources
7. IF a table already exists when the provisioning script is executed, THEN THE Redshift_Connector SHALL skip creation of that table and proceed to the next table without error
8. WHEN all tables are created and populated successfully, THE Redshift_Connector SHALL output a confirmation summary indicating the number of tables created and the row count inserted per table

### Requirement 2: Redshift Connection Management

**User Story:** As a developer, I want the application to connect to Redshift using the AWS Redshift Data API, so that queries execute without managing persistent database connections.

#### Acceptance Criteria

1. THE Redshift_Connector SHALL use the boto3 redshift-data client to execute SQL statements against the Redshift_Cluster
2. THE Redshift_Connector SHALL authenticate using the cluster credentials configured in the application settings (cluster identifier: "talktodata", database user: "admin")
3. WHEN a SQL statement is submitted, THE Redshift_Connector SHALL poll for statement completion at intervals between 500 milliseconds and 2 seconds, with a maximum wait time of 30 seconds
4. IF a statement execution exceeds the 30-second timeout, THEN THE Redshift_Connector SHALL cancel the statement and return an error with error_type "TIMEOUT" and the elapsed wait duration
5. IF the Redshift_Data_API returns an authentication error, THEN THE Redshift_Connector SHALL return an error with error_type "AUTH_FAILURE" and the cluster identifier
6. THE Redshift_Connector SHALL configure the connection using environment variables or application config for cluster identifier, database name, and database user
7. WHEN a SQL statement completes successfully, THE Redshift_Connector SHALL retrieve the result set using the statement identifier and return the column metadata and row data
8. IF the Redshift_Data_API returns a statement execution error that is not an authentication error, THEN THE Redshift_Connector SHALL return an error with error_type "QUERY_FAILURE" and the error description provided by the API

### Requirement 3: SQL Query Generation from Structured Intents

**User Story:** As a developer, I want structured intents to be translated into safe SQL queries, so that the Redshift Spoke Agent can retrieve the correct data for user questions.

#### Acceptance Criteria

1. WHEN a Structured_Intent with query_type "lookup" is received, THE SQL_Generator SHALL produce a SELECT statement that retrieves rows from the table resolved via Schema_Registry where column values match the entity_refs filter values, limited to a maximum of 1000 returned rows
2. WHEN a Structured_Intent with query_type "aggregation" is received, THE SQL_Generator SHALL produce a SELECT statement applying the aggregate function specified in routing_metadata (one of SUM, AVG, COUNT, MIN, MAX) to numeric columns and GROUP BY all categorical columns as defined in the Schema_Registry
3. WHEN a Structured_Intent with query_type "comparison" is received, THE SQL_Generator SHALL produce a SELECT statement with GROUP BY on the first categorical column from entity_refs (the comparison dimension) and SUM applied to all numeric columns as defined in the Schema_Registry
4. THE SQL_Generator SHALL use parameterized queries to prevent SQL injection for all filter values derived from entity_refs or routing_metadata
5. THE SQL_Generator SHALL resolve entity_refs to table and column names using the Schema_Registry configuration
6. IF an entity_ref cannot be mapped to any table in the Schema_Registry, THEN THE SQL_Generator SHALL return an error with error_type "UNRESOLVED_ENTITY" and include the unresolved entity_ref identifier in the error description
7. IF entity_refs in a single Structured_Intent resolve to more than one table in the Schema_Registry, THEN THE SQL_Generator SHALL generate a query against the first resolved table only and include only entity_refs belonging to that table
8. IF the routing_metadata for an aggregation query does not specify an aggregate function, THEN THE SQL_Generator SHALL default to SUM for all numeric columns
9. WHEN a valid Structured_Intent is received, THE SQL_Generator SHALL produce a syntactically valid SQL statement that can be parsed without error by a standard SQL parser

### Requirement 4: Redshift Spoke Agent Service

**User Story:** As a developer, I want a dedicated spoke agent for Redshift queries, so that the Orchestrator Hub can route Redshift-related intents to the correct data source.

#### Acceptance Criteria

1. THE Redshift_Spoke_Agent SHALL run as a FastAPI application on a configurable port (default 8011)
2. THE Redshift_Spoke_Agent SHALL expose a POST endpoint at /agents/redshift-spoke-agent/invoke that accepts a request body containing a structured_intent field conforming to the Structured_Intent schema
3. WHEN the Redshift_Spoke_Agent receives a valid Structured_Intent, THE Redshift_Spoke_Agent SHALL generate SQL using the SQL_Generator, execute the query via the Redshift_Connector, and return an Agent_Result with status "success" and agent_id "redshift-spoke-agent" and data_source "redshift"
4. THE Redshift_Spoke_Agent SHALL return Agent_Result payloads with data_type "tabular" for lookup queries (columns and rows arrays), "aggregation" for aggregation queries (aggregations dictionary), and "comparison" for comparison queries (groups dictionary)
5. IF the SQL query execution fails, THEN THE Redshift_Spoke_Agent SHALL return an Agent_Result with status "error", error_type set to one of "QUERY_EXECUTION_ERROR", "TIMEOUT_ERROR", or "CONNECTION_ERROR", and error_description containing the failure details
6. THE Redshift_Spoke_Agent SHALL expose a GET /health endpoint returning a JSON object with status ("healthy" or "unhealthy"), service name, port, and connected database name
7. WHEN the Redshift_Spoke_Agent starts, THE Redshift_Spoke_Agent SHALL validate connectivity to the Redshift_Cluster and log the connection status; IF connectivity validation fails, THEN THE Redshift_Spoke_Agent SHALL start in a degraded state and report status "unhealthy" on the /health endpoint until connectivity is restored
8. IF the POST /agents/redshift-spoke-agent/invoke endpoint receives a request body that does not conform to the Structured_Intent schema, THEN THE Redshift_Spoke_Agent SHALL return an Agent_Result with status "error", error_type "INVALID_INTENT", and error_description indicating the validation failure

### Requirement 5: Ontology Extension for Redshift Concepts

**User Story:** As a developer, I want Redshift-backed data represented in the enterprise ontology, so that user queries about Redshift data are routed to the Redshift Spoke Agent.

#### Acceptance Criteria

1. THE Ontology_Store SHALL contain exactly 3 concepts corresponding to the Redshift tables (sales_transactions, customer_segments, employee_performance), each with data_source set to "redshift", agent_id set to "redshift-spoke-agent", and a concept_id following the "ontology:" prefix convention
2. WHEN the ontology is loaded, THE Ontology_Store SHALL include a "sales_transactions" concept with domain "finance", aggregatable numeric properties (quantity, total_amount), and relationships of type "grouped_by" to ontology:region and ontology:product_category
3. WHEN the ontology is loaded, THE Ontology_Store SHALL include a "customer_segments" concept with domain "customers", aggregatable numeric properties (lifetime_value, total_orders), and a relationship of type "grouped_by" to ontology:region
4. WHEN the ontology is loaded, THE Ontology_Store SHALL include an "employee_performance" concept with domain "hr", aggregatable numeric properties (quarterly_target, quarterly_actual, deals_closed, customer_satisfaction_score), and a relationship of type "grouped_by" to ontology:region
5. THE Ontology_Store SHALL define each relationship between a Redshift concept and a shared dimension concept with a relation_type of "grouped_by" and a join_key property identifying the linking column name
6. IF the ontology file contains a Redshift concept that references a shared dimension concept_id not present in the Ontology_Store, THEN THE Ontology_Store SHALL log a warning identifying the missing target concept_id and skip that relationship

### Requirement 6: Agent Registration and Orchestrator Integration

**User Story:** As a developer, I want the Redshift Spoke Agent registered with the Orchestrator Hub, so that Redshift queries are automatically routed to it.

#### Acceptance Criteria

1. WHEN the application starts, THE Redshift_Spoke_Agent SHALL register with the Orchestrator_Hub using agent_id "redshift-spoke-agent", agent_name "Redshift Spoke Agent", data_source "redshift", endpoint_url pointing to the Redshift_Spoke_Agent service URL, and entity_refs ["ontology:sales_transactions", "ontology:customer_segments", "ontology:employee_performance"]
2. WHEN the Orchestrator_Hub receives a Structured_Intent with at least one entity_ref present in the Redshift_Spoke_Agent's registered entity_refs list, THE Orchestrator_Hub SHALL include the Redshift_Spoke_Agent in the resolved candidates for dispatch
3. WHEN the Orchestrator_Hub dispatches to the Redshift_Spoke_Agent, THE Redshift_Spoke_Agent SHALL return an Agent_Result containing status, payload with a data_type field (one of "tabular", "aggregation", or "comparison"), agent_id set to "redshift-spoke-agent", and data_source set to "redshift"
4. IF the Redshift_Spoke_Agent is unavailable during dispatch due to a connection error, timeout, or non-200 HTTP response, THEN THE Orchestrator_Hub SHALL include "redshift-spoke-agent" in the unavailable_agents list of the Orchestrator_Response
5. IF the Orchestrator_Hub is unreachable when the Redshift_Spoke_Agent attempts registration at startup, THEN THE Redshift_Spoke_Agent SHALL log an error indicating the Orchestrator_Hub endpoint and connection failure reason

### Requirement 7: Configuration and Dependency Management

**User Story:** As a developer, I want Redshift connection settings externalized and the required AWS SDK dependency declared, so that the integration is deployable across environments.

#### Acceptance Criteria

1. THE Redshift_Connector SHALL read the cluster identifier from the REDSHIFT_CLUSTER_ID environment variable, defaulting to "talktodata" when the variable is not set or is empty
2. THE Redshift_Connector SHALL read the database name from the REDSHIFT_DATABASE environment variable, defaulting to "analytics" when the variable is not set or is empty
3. THE Redshift_Connector SHALL read the database user from the REDSHIFT_DB_USER environment variable, defaulting to "admin" when the variable is not set or is empty
4. THE Redshift_Connector SHALL read the AWS region from the REDSHIFT_REGION environment variable, defaulting to "us-east-1" when the variable is not set or is empty
5. THE pyproject.toml SHALL declare boto3 with a minimum version of 1.35.0 in the project dependencies list
6. THE application configuration SHALL assign port 8011 to the Redshift_Spoke_Agent and define a service URL constant with value "http://localhost:8011" used by the Orchestrator_Hub for dispatch
7. IF any configured environment variable value results in a connection failure at startup, THEN THE Redshift_Connector SHALL report an error message indicating which configuration parameter is invalid and its current value

### Requirement 8: Schema Registry Configuration

**User Story:** As a developer, I want a schema registry that maps Redshift tables and columns to ontology concepts, so that the SQL Generator can resolve entity_refs to valid SQL.

#### Acceptance Criteria

1. THE Schema_Registry SHALL define a mapping from each ontology concept_id with agent_id "redshift-spoke-agent" to its corresponding Redshift table name and the complete list of columns available for query generation
2. THE Schema_Registry SHALL classify every mapped column as one of: categorical (usable in GROUP BY and WHERE equality filters), numeric (usable in aggregate functions SUM, AVG, COUNT, MIN, MAX), or identifier (usable only in SELECT and WHERE equality filters, not in aggregations or GROUP BY)
3. THE Schema_Registry SHALL specify filter mappings that associate each filterable entity_ref keyword with a target column name and a comparison operator (one of: equals, in, greater_than, less_than, between, like)
4. WHEN the Schema_Registry is loaded, THE Redshift_Spoke_Agent SHALL validate that all referenced tables and their declared columns exist in the configured Redshift database within the connection timeout defined for the Redshift_Connector
5. IF a referenced table does not exist in Redshift, THEN THE Redshift_Spoke_Agent SHALL log a warning indicating the missing table name, exclude that concept from available entity_refs, and continue startup with the remaining valid concepts
6. IF no referenced tables exist in Redshift during Schema_Registry validation, THEN THE Redshift_Spoke_Agent SHALL fail to start and log an error indicating that no valid schema mappings are available
