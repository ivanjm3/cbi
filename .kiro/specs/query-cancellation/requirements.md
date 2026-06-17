# Requirements Document

## Introduction

This feature allows users to cancel an in-flight query from the frontend UI. Cancellation propagates through the entire backend service chain (NLP Translator → Orchestrator Hub → Spoke Agents) to terminate ongoing processing and free resources. The system uses a correlation-ID-based cancellation token pattern: the frontend signals cancellation via an AbortController, the NLP API detects the disconnection and marks the query as cancelled in a shared cancellation registry, and downstream services check this registry before continuing work.

## Glossary

- **Frontend**: The Vite/React single-page application served on port 5173 that provides the chat-based query interface.
- **NLP_API**: The FastAPI service on port 8001 that translates natural language queries into structured intents and orchestrates the full query flow.
- **Orchestrator_Hub**: The FastAPI service on port 8002 that dispatches structured intents to spoke agents based on ontology entity references.
- **Spoke_Agent**: A downstream data-retrieval agent (port 8010 for CSV/JSON, port 8011 for Redshift) invoked by the Orchestrator Hub.
- **Cancellation_Registry**: An in-memory store (per service) that tracks query IDs whose processing has been cancelled.
- **Correlation_ID**: A unique identifier propagated through all services for a single query request, used to identify which query to cancel.
- **Cancel_Button**: A UI control displayed while a query is in flight that allows the user to abort the current request.
- **AbortController**: The browser-native API used to abort an in-flight fetch request from the frontend.

## Requirements

### Requirement 1: Frontend Cancel Button Visibility

**User Story:** As a user, I want to see a cancel button while my query is being processed, so that I can abort a query I no longer need.

#### Acceptance Criteria

1. WHILE a query is in flight, THE Frontend SHALL display the Cancel_Button in place of the submit button.
2. WHEN the query completes or fails, THE Frontend SHALL hide the Cancel_Button and restore the submit button.
3. WHILE no query is in flight, THE Frontend SHALL NOT display the Cancel_Button.

### Requirement 2: Frontend Cancellation Trigger

**User Story:** As a user, I want to click the cancel button to immediately stop my query, so that I do not have to wait for a long-running request to finish.

#### Acceptance Criteria

1. WHEN the user activates the Cancel_Button, THE Frontend SHALL abort the in-flight HTTP request using the AbortController.
2. WHEN the user activates the Cancel_Button, THE Frontend SHALL set the loading state to false within 100 milliseconds.
3. WHEN the user activates the Cancel_Button, THE Frontend SHALL append a system message to the chat thread indicating the query was cancelled.
4. WHEN the user activates the Cancel_Button, THE Frontend SHALL re-enable the query input field for new submissions.

### Requirement 3: NLP API Cancellation Detection

**User Story:** As a system operator, I want the NLP API to detect when a client disconnects, so that downstream processing is terminated promptly.

#### Acceptance Criteria

1. WHEN the client disconnects during query processing, THE NLP_API SHALL mark the Correlation_ID as cancelled in the Cancellation_Registry.
2. WHEN the Correlation_ID is marked as cancelled, THE NLP_API SHALL terminate any in-progress calls to downstream services for that Correlation_ID.
3. WHEN the NLP_API detects a cancellation during the orchestrator call, THE NLP_API SHALL send a cancellation request to the Orchestrator_Hub cancel endpoint with the Correlation_ID.

### Requirement 4: NLP API Cancel Endpoint

**User Story:** As a frontend developer, I want a dedicated cancel endpoint, so that explicit cancellation requests can be sent when the AbortController alone is insufficient.

#### Acceptance Criteria

1. THE NLP_API SHALL expose a POST /cancel endpoint that accepts a Correlation_ID in the request body.
2. WHEN a valid cancellation request is received, THE NLP_API SHALL mark the Correlation_ID as cancelled in the Cancellation_Registry.
3. WHEN a valid cancellation request is received, THE NLP_API SHALL return HTTP 200 with a confirmation payload within 50 milliseconds.
4. IF the Correlation_ID does not correspond to an active query, THEN THE NLP_API SHALL return HTTP 200 with a no-op acknowledgment.

### Requirement 5: Orchestrator Hub Cancellation

**User Story:** As a system operator, I want the Orchestrator Hub to stop dispatching to agents when a query is cancelled, so that compute resources are not wasted.

#### Acceptance Criteria

1. THE Orchestrator_Hub SHALL expose a POST /internal/cancel endpoint that accepts a Correlation_ID.
2. WHEN a cancellation request is received, THE Orchestrator_Hub SHALL mark the Correlation_ID as cancelled in its local Cancellation_Registry.
3. WHILE processing a multi-agent dispatch, WHEN the Correlation_ID is marked as cancelled, THE Orchestrator_Hub SHALL skip dispatching to any remaining agents that have not yet been called.
4. WHEN the Correlation_ID is marked as cancelled during an active spoke agent call, THE Orchestrator_Hub SHALL attempt to cancel the in-flight HTTP request to the Spoke_Agent.
5. WHEN a cancellation is processed, THE Orchestrator_Hub SHALL return an OrchestratorError with error_type "QUERY_CANCELLED" for the original request.

### Requirement 6: Spoke Agent Cancellation

**User Story:** As a system operator, I want spoke agents to terminate work when notified of cancellation, so that expensive operations like database queries are stopped early.

#### Acceptance Criteria

1. THE Spoke_Agent SHALL check the cancellation status of the Correlation_ID before executing expensive operations such as database queries or LLM calls.
2. WHEN the upstream HTTP connection is closed, THE Spoke_Agent SHALL treat the request as cancelled and halt processing.
3. IF a cancellation is detected mid-processing, THEN THE Spoke_Agent SHALL return an error response with status "CANCELLED" and release any held resources.

### Requirement 7: Cancellation Propagation Latency

**User Story:** As a user, I want cancellation to take effect quickly across the system, so that I experience near-immediate feedback after pressing cancel.

#### Acceptance Criteria

1. WHEN the user activates the Cancel_Button, THE Frontend SHALL abort the HTTP request within 50 milliseconds.
2. WHEN a cancellation is registered at the NLP_API, THE NLP_API SHALL propagate the cancellation to the Orchestrator_Hub within 200 milliseconds.
3. WHEN a cancellation is registered at the Orchestrator_Hub, THE Orchestrator_Hub SHALL cease dispatching new agent calls within 100 milliseconds.

### Requirement 8: Cancellation State Cleanup

**User Story:** As a system operator, I want cancellation records to be cleaned up automatically, so that memory is not leaked over time.

#### Acceptance Criteria

1. THE Cancellation_Registry SHALL remove entries older than 300 seconds automatically.
2. WHEN a query completes normally, THE Cancellation_Registry SHALL remove the corresponding entry within 10 seconds.
3. THE Cancellation_Registry SHALL limit stored entries to a maximum of 1000 concurrent cancellation records.

### Requirement 9: Concurrent Query Isolation

**User Story:** As a user, I want cancelling one query to not affect other users or other queries, so that the system remains reliable under concurrent use.

#### Acceptance Criteria

1. WHEN a Correlation_ID is cancelled, THE Cancellation_Registry SHALL only affect processing associated with that specific Correlation_ID.
2. THE NLP_API SHALL continue processing other active queries unaffected when one query is cancelled.
3. THE Orchestrator_Hub SHALL continue processing other active intents unaffected when one intent is cancelled.

### Requirement 10: Frontend Cancellation with Explicit Request

**User Story:** As a frontend developer, I want the UI to send an explicit cancel request in addition to aborting the fetch, so that the backend is reliably notified even if the TCP connection lingers.

#### Acceptance Criteria

1. WHEN the user activates the Cancel_Button, THE Frontend SHALL send a POST request to the /cancel endpoint with the active Correlation_ID.
2. IF the /cancel request fails due to a network error, THEN THE Frontend SHALL log the failure and continue with the local cancellation flow without blocking the user.
3. THE Frontend SHALL generate and store a Correlation_ID for each query submission, included as a header in the original query request.
