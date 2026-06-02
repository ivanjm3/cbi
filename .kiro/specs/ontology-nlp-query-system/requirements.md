# Requirements Document

## Introduction

This document defines the requirements for an ontology-based, NLP-driven query system. The system accepts natural language queries from users, interprets them through an ontology layer, routes them to specialized data-source agents via an orchestration hub, applies guardrails to the responses, and renders results as visualizations or plain text back to the user. The architecture follows a hub-and-spoke model with cross-cutting observability and a shared ontology store.

The end-to-end data flow is:

**UI → Auth Gateway → NLP Translator → Orchestrator Hub → Spoke Agents → Guardrail Layer → Visualization Renderer → UI**

---

## Glossary

- **System**: The complete ontology-based NLP query system described in this document.
- **UI**: The web-based user interface through which end users submit queries and view results.
- **Auth_Gateway**: The authentication and authorization component that sits between the UI and the NLP Translator. All requests pass through it.
- **NLP_Translator**: The component that applies ontology concepts to parse, classify, and enrich natural language queries into structured intents.
- **Ontology_Store**: The shared repository of domain ontology definitions, accessible by both the NLP_Translator and the Orchestrator_Hub. Supports graph DB, flat file, and RDBMS backends.
- **Orchestrator_Hub**: The central routing component that reads structured intents from the NLP_Translator, checks the Result_Cache, and dispatches work to one or more Spoke_Agents.
- **Result_Cache**: A cache layer within the Orchestrator_Hub that stores previous query results, keyed by structured intent, to avoid redundant agent invocations.
- **Event_Broker**: An optional message-passing component conditionally activated by the Orchestrator_Hub for streaming or event-driven query types.
- **Spoke_Agent**: A specialized agent responsible for querying a single designated data source and returning structured results to the Orchestrator_Hub.
- **Guardrail_Layer**: The post-processing component applied to all agent responses before visualization, responsible for safety, policy, and schema validation.
- **Visualization_Renderer**: The component that transforms validated agent responses into graphs or plain text for display in the UI.
- **Observability_Bus**: A cross-cutting decorator applied at every service entry point to emit structured telemetry (logs, metrics, traces).
- **Query_History_Store**: A persistent store of past queries and their resolved intents, used to bias future NLP_Translator routing toward historically successful paths.
- **Structured_Intent**: The machine-readable representation of a user query produced by the NLP_Translator, containing at minimum: query_id (UUID), query_type (one of: lookup, aggregation, comparison, streaming), entity_refs (list of canonical ontology concept identifiers), routing_metadata (agent path hints), and timestamp.
- **User**: An authenticated human end user interacting with the UI.
- **Admin**: An operator with elevated privileges responsible for managing ontology definitions, agent registration, and system configuration.

---

## Requirements

---

### Requirement 1: User Authentication and Authorization

**User Story:** As a User, I want my identity verified before I can submit queries, so that only authorized users can access the system and its data.

#### Acceptance Criteria

1. WHEN a User submits a request to the System, THE Auth_Gateway SHALL authenticate the User's identity using a session token that is present, not expired, and was issued by the system before forwarding the request to the NLP_Translator.
2. IF a User submits a request with a missing, expired, or unrecognized session token, THEN THE Auth_Gateway SHALL reject the request with an HTTP 401 response and include an error body indicating the authentication failure reason.
3. IF a User submits a request for a resource or operation not permitted by the user's assigned role, THEN THE Auth_Gateway SHALL reject the request with an HTTP 403 response and include an error body indicating the authorization failure reason.
4. THE Auth_Gateway SHALL forward only authenticated and authorized requests to the NLP_Translator.

---

### Requirement 2: Natural Language Query Parsing

**User Story:** As a User, I want to type a question in plain English, so that I can query complex data without knowing query languages.

#### Acceptance Criteria

1. WHEN THE Auth_Gateway forwards an authenticated query, THE NLP_Translator SHALL parse the query text and produce a Structured_Intent containing: query_id (UUID), query_type (one of: lookup, aggregation, comparison, streaming), entity_refs (list of canonical ontology concept identifiers), routing_metadata, and timestamp.
2. WHEN THE Auth_Gateway forwards an authenticated query, THE NLP_Translator SHALL resolve entity references in the query against the Ontology_Store to populate the entity_refs field of the Structured_Intent with canonical ontology concept identifiers.
3. WHEN THE Auth_Gateway forwards an authenticated query, THE NLP_Translator SHALL classify the query type as exactly one of: lookup, aggregation, comparison, or streaming, and record it in the query_type field of the Structured_Intent.
4. WHEN the Query_History_Store returns one or more past Structured_Intents with a semantic similarity score of 0.85 or higher (on a 0–1 scale) to the current query, THE NLP_Translator SHALL set the routing_metadata field of the new Structured_Intent to the agent path recorded in the most recent matching past Structured_Intent.
5. IF THE NLP_Translator cannot produce a Structured_Intent for a query, THEN THE NLP_Translator SHALL return a structured error response containing: error_code (one of: UNPARSEABLE_QUERY, NO_ONTOLOGY_MATCH, AMBIGUOUS_INTENT), error_message (human-readable explanation), and query_id.

---

### Requirement 3: Ontology Store

**User Story:** As a developer deploying the system, I want to configure the ontology backend to match existing infrastructure, so that I can reuse data stores already available in my environment.

#### Acceptance Criteria

1. THE Ontology_Store SHALL expose a uniform query interface to both the NLP_Translator and the Orchestrator_Hub, regardless of the configured backend, supporting at minimum: concept lookup by identifier, hierarchical traversal of concept relationships, and keyword search over concept labels.
2. WHERE the Ontology_Store is configured to use a graph database backend, THE Ontology_Store SHALL store and retrieve ontology definitions using that graph database.
3. WHERE the Ontology_Store is configured to use a flat-file backend, THE Ontology_Store SHALL store and retrieve ontology definitions from structured files on disk serialized in the canonical format defined in Requirement 12.
4. WHERE the Ontology_Store is configured to use an RDBMS backend, THE Ontology_Store SHALL store and retrieve ontology definitions from a relational database.
5. WHEN an Admin submits a new ontology definition, THE Ontology_Store SHALL persist the definition and make it available to consumers within 5 seconds.
6. WHEN an Admin submits an update to an existing ontology definition, THE Ontology_Store SHALL replace the prior definition and make the updated definition available to consumers within 5 seconds without requiring a service restart.
7. WHEN an Admin deletes an ontology definition, THE Ontology_Store SHALL remove the definition and make the removal visible to consumers within 5 seconds.
8. IF an Admin submits an ontology definition that is malformed, fails schema validation, or duplicates the identifier of an existing definition, THEN THE Ontology_Store SHALL reject the submission, return a structured error indicating the failure reason, and leave the existing store state unchanged.
9. IF THE Ontology_Store cannot propagate an update to consumers within 5 seconds, THEN THE Ontology_Store SHALL log a structured error indicating the propagation failure and the affected definition identifier, and consumers SHALL continue to operate using the last successfully propagated state.

---

### Requirement 4: Orchestration and Agent Dispatch

**User Story:** As a User, I want my query routed to the right data sources automatically, so that I receive accurate results without knowing which systems hold the relevant data.

#### Acceptance Criteria

1. WHEN THE NLP_Translator delivers a Structured_Intent to the Orchestrator_Hub, THE Orchestrator_Hub SHALL inspect the Result_Cache before dispatching to any Spoke_Agent.
2. WHEN the Result_Cache contains an entry whose key exactly matches the Structured_Intent (same query_type, entity_refs, and routing_metadata), THE Orchestrator_Hub SHALL return the cached result directly without invoking any Spoke_Agent.
3. WHEN no matching cache entry exists, THE Orchestrator_Hub SHALL query the Ontology_Store to retrieve the list of Spoke_Agents responsible for each data source referenced in the entity_refs field of the Structured_Intent.
4. WHEN the Orchestrator_Hub has resolved the responsible Spoke_Agents, THE Orchestrator_Hub SHALL dispatch the Structured_Intent to all resolved Spoke_Agents concurrently.
5. WHEN the Structured_Intent query_type is streaming or event-driven, THE Orchestrator_Hub SHALL activate the Event_Broker and route the query through it instead of dispatching directly.
6. IF a Spoke_Agent does not return a response within a configurable timeout (default 30 seconds; configurable range 1–300 seconds), THEN THE Orchestrator_Hub SHALL mark that agent's result as unavailable and proceed with results received from other Spoke_Agents.
7. WHEN all Spoke_Agent results or timeouts have been received, THE Orchestrator_Hub SHALL merge the results into a single response that identifies each unavailable agent by name and forward it to the Guardrail_Layer.
8. IF all dispatched Spoke_Agents time out, THEN THE Orchestrator_Hub SHALL return a structured error response to the caller indicating that no agent results were available, without forwarding to the Guardrail_Layer.
9. IF the Ontology_Store returns no responsible Spoke_Agents for the entity_refs in the Structured_Intent, THEN THE Orchestrator_Hub SHALL return a structured error response indicating that no agents could be resolved for the query.

---

### Requirement 5: Event-Driven Query Streaming

**User Story:** As a User submitting a streaming query, I want to receive results incrementally as data arrives, so that I do not have to wait for all data to be ready before seeing initial output.

#### Acceptance Criteria

1. WHEN THE Orchestrator_Hub activates the Event_Broker, THE Event_Broker SHALL accept the Structured_Intent and open a streaming channel to the requesting UI session.
2. IF THE Event_Broker fails to open a streaming channel, THEN THE Event_Broker SHALL return a structured error to the Orchestrator_Hub indicating the failure reason, and the Orchestrator_Hub SHALL return that error to the caller.
3. WHILE a streaming channel is open, THE Event_Broker SHALL forward each incremental result from Spoke_Agents to the UI in the order it is received.
4. IF a streaming channel has been open for more than a configurable inactivity timeout (default 60 seconds; configurable range 1–600 seconds) without receiving a result from any Spoke_Agent, THEN THE Event_Broker SHALL close the channel, notify the Orchestrator_Hub with a timeout error, and release all associated resources.
5. WHEN all streaming results have been delivered, THE Event_Broker SHALL close the streaming channel and notify the Orchestrator_Hub that delivery is complete.
6. IF the UI session disconnects before all streaming results are delivered, THEN THE Event_Broker SHALL stop forwarding results, close the streaming channel, and release all memory and connection resources allocated for that channel within 5 seconds of detecting the disconnect.

---

### Requirement 6: Spoke Agent Data Retrieval

**User Story:** As a system operator, I want each spoke agent to be isolated to its own data source, so that data access is controlled, auditable, and independently scalable.

#### Acceptance Criteria

1. THE Spoke_Agent SHALL query only the single designated data source for which it is registered.
2. WHEN THE Orchestrator_Hub dispatches a Structured_Intent to a Spoke_Agent, THE Spoke_Agent SHALL translate the Structured_Intent into a query that is executable by its designated data source.
3. WHEN a Spoke_Agent receives results from its data source, THE Spoke_Agent SHALL return a structured response to the Orchestrator_Hub containing at minimum: a status indicator (success or error) and the query result payload.
4. IF a Spoke_Agent encounters an error querying its data source, THEN THE Spoke_Agent SHALL return a structured error response to the Orchestrator_Hub containing the error type and a description, without retrying the query.
5. THE Orchestrator_Hub SHALL support registering, deregistering, and updating Spoke_Agents at runtime without restarting the Orchestrator_Hub.
6. WHEN a Spoke_Agent is registered, deregistered, or updated, THE Orchestrator_Hub SHALL reflect the change in its active agent routing table within 5 seconds.

---

### Requirement 7: Guardrail Validation

**User Story:** As a system operator, I want all agent responses validated before they reach users, so that unsafe, malformed, or policy-violating content is never displayed.

#### Acceptance Criteria

1. THE Guardrail_Layer SHALL receive every merged response from the Orchestrator_Hub before it is forwarded to the Visualization_Renderer.
2. WHEN THE Guardrail_Layer receives a response, THE Guardrail_Layer SHALL validate that the response conforms to the output schema registered for the query type in the Structured_Intent.
3. WHEN THE Guardrail_Layer receives a response, THE Guardrail_Layer SHALL evaluate the response against the full set of configured safety and policy rules.
4. IF a response fails schema validation, THEN THE Guardrail_Layer SHALL reject the response and return a structured error to the Orchestrator_Hub containing the validation failure details, without forwarding the response.
5. IF a response contains content that violates a safety or policy rule but the response is not entirely composed of violating content, THEN THE Guardrail_Layer SHALL redact the specific violating content, annotate the response with the identifier of each applied rule, and forward the annotated response to the Visualization_Renderer.
6. IF a response is entirely composed of content that violates a safety or policy rule, THEN THE Guardrail_Layer SHALL reject the response and return a structured error to the Orchestrator_Hub containing the rule identifiers that were triggered, without forwarding the response.
7. WHEN a response passes all schema validation and policy rule checks, THE Guardrail_Layer SHALL forward the validated response to the Visualization_Renderer.
8. IF THE Guardrail_Layer encounters an internal failure while processing a response, THEN THE Guardrail_Layer SHALL return a structured error to the Orchestrator_Hub indicating the failure type, without forwarding any partial output.

---

### Requirement 8: Visualization Rendering

**User Story:** As a User, I want query results displayed as clear graphs or readable text, so that I can interpret complex data at a glance.

#### Acceptance Criteria

1. WHEN THE Guardrail_Layer forwards a validated response, THE Visualization_Renderer SHALL determine whether the response requires graphical rendering or plain text output based on the presence of structured numeric or categorical data fields in the response payload.
2. IF the response contains structured numeric or categorical data, THEN THE Visualization_Renderer SHALL use a ReAct reasoning loop to select a graph type from the supported set (bar chart, line chart, scatter plot, pie chart, table) based on the data structure and cardinality of the response payload.
3. IF the ReAct reasoning loop cannot select a graph type after 3 reasoning iterations, THEN THE Visualization_Renderer SHALL fall back to rendering the data as a table.
4. IF the response does not contain structured numeric or categorical data, THEN THE Visualization_Renderer SHALL format the response as plain text and return it to the UI without invoking the ReAct loop.
5. WHEN the Visualization_Renderer fails to render the output, THE Visualization_Renderer SHALL return a structured error to the Guardrail_Layer indicating the failure type rather than returning a partial or malformed visualization.
6. THE Visualization_Renderer SHALL return the rendered output to the UI.
7. THE Visualization_Renderer SHALL support rendering at least the following graph types: bar chart, line chart, scatter plot, pie chart, and table.

---

### Requirement 9: User Interface

**User Story:** As a User, I want a simple interface to submit queries, view visualizations, and manage my query history, so that I can work efficiently without cognitive overhead.

#### Acceptance Criteria

1. THE UI SHALL present a text input field that submits the entered query to the Auth_Gateway when the User activates the submit control (keyboard Enter or on-screen button).
2. THE UI SHALL display up to 6 graphs or visualizations simultaneously in a single view.
3. THE UI SHALL allow the User to reposition and resize graphs within the view by dragging and dropping.
4. THE UI SHALL provide a per-visualization download control that, when activated, exports the visualization's underlying data, its associated metadata (query_id, timestamp, data source names), and the original query text that produced it.
5. THE UI SHALL provide a control to bookmark a chat session that saves the session identifier and all associated queries and responses for later retrieval by the same User.
6. THE UI SHALL provide a control to share a chat session that generates a shareable link accessible by other authenticated Users, granting read-only access to the session's queries and responses.
7. THE UI SHALL render only controls, labels, and content necessary for the current task, maintaining a minimal visual design with no decorative elements.
8. WHILE a query is being processed, THE UI SHALL display a visible loading or progress indicator to the User.
9. WHEN THE Visualization_Renderer returns output to the UI, THE UI SHALL display the output within 500ms of receipt.

---

### Requirement 10: Query History and Routing Bias

**User Story:** As a User, I want the system to learn from my past queries, so that similar future queries are resolved faster and more accurately.

#### Acceptance Criteria

1. WHEN THE Guardrail_Layer forwards a validated response to the Visualization_Renderer, THE Guardrail_Layer SHALL also persist the original query text and its resolved Structured_Intent to the Query_History_Store.
2. THE Query_History_Store SHALL be queryable by the NLP_Translator to retrieve past Structured_Intents for semantic similarity comparison.
3. WHEN THE NLP_Translator queries the Query_History_Store for semantically similar past Structured_Intents, THE Query_History_Store SHALL return all matching records with a cosine similarity score of 0.85 or higher within 200ms.
4. WHEN an Admin configures the retention period (valid range: 1–365 days), THE Query_History_Store SHALL expire and remove query history records older than the configured retention period.
5. IF the Query_History_Store is unavailable when a write is attempted, THEN the system SHALL log a structured error and continue processing the query without persisting the history record.
6. IF the Query_History_Store is unavailable when a read is attempted by the NLP_Translator, THEN THE NLP_Translator SHALL skip the routing bias step and continue translation without history-based routing metadata.

---

### Requirement 11: Observability

**User Story:** As a system operator, I want structured telemetry emitted from every service, so that I can monitor health, diagnose failures, and trace requests across the system.

#### Acceptance Criteria

1. THE Observability_Bus SHALL be applied as a decorator to the entry point of every service in the System (Auth_Gateway, NLP_Translator, Orchestrator_Hub, Spoke_Agents, Guardrail_Layer, Visualization_Renderer, Event_Broker).
2. WHEN a service entry point is invoked, THE Observability_Bus SHALL emit a structured JSON log entry containing: service_name, operation_name, correlation_id, timestamp (ISO 8601), and request_duration_ms (integer milliseconds).
3. WHEN a request arrives at the first service entry point without a correlation ID, THE Observability_Bus SHALL generate a new UUID as the correlation_id for that request before emitting any log entry.
4. WHEN a service entry point makes a downstream service call, THE Observability_Bus SHALL include the current correlation_id in the downstream request so it is available at the next service entry point.
5. IF a service entry point raises an unhandled exception, THEN THE Observability_Bus SHALL emit a structured JSON error log entry containing the exception_type, exception_message, stack_trace, correlation_id, and service_name before allowing the exception to propagate.
6. THE Observability_Bus SHALL expose aggregated metrics (request count, error rate, p50/p95/p99 latency in milliseconds) per service entry point, computed over a rolling 60-second time window, queryable via a metrics endpoint.

---

### Requirement 12: Ontology Round-Trip Consistency

**User Story:** As a developer, I want ontology definitions to survive serialization and deserialization without data loss, so that loaded ontologies are always equivalent to the originals.

#### Acceptance Criteria

1. THE Ontology_Store SHALL serialize ontology definitions to a persistent format that preserves all concepts, all relationships between concepts, and all property values on both concepts and relationships.
2. WHEN THE Ontology_Store deserializes a previously serialized ontology definition, THE Ontology_Store SHALL reconstruct an in-memory representation containing the same set of concepts, the same relationships, and the same property values as the original.
3. WHEN an ontology definition object is serialized and then deserialized using the same Ontology_Store interface, the resulting object SHALL contain the same set of concepts, the same set of relationships, and the same property values as the original, regardless of ordering.
4. THE Ontology_Store SHALL expose a pretty-printer that formats an in-memory ontology definition into a human-readable text representation that preserves all concepts, relationships, and property values and is readable without additional tooling.
5. WHEN an ontology definition is formatted via the pretty-printer and then parsed back using the Ontology_Store's deserialization interface, the resulting in-memory object SHALL contain the same set of concepts, relationships, and property values as the original.
6. IF THE Ontology_Store receives serialized data that is malformed or does not conform to the expected serialization format, THEN THE Ontology_Store SHALL reject the data, return a structured error indicating the parse failure location and reason, and leave the in-memory state unchanged.
7. IF THE Ontology_Store encounters an error while serializing an ontology definition, THEN THE Ontology_Store SHALL return a structured error indicating the serialization failure reason and SHALL NOT write any partial data to the persistence store.
