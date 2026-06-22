# Requirements Document: Scheduled Reports

## Introduction

The Scheduled Reports feature enables users to automate the execution of saved conversational queries on a recurring schedule using AWS Step Functions for orchestration. Users can schedule their most valuable chat queries to run automatically at specified intervals (daily, weekly, monthly, etc.) and view updated results without manual re-execution. The feature integrates scheduling controls into the chat interface, adds a dedicated Scheduled Reports management page, and leverages the existing pinned visualization boxes as the unit of scheduling.

---

## Glossary

- **Chat Query**: A conversational query and its complete result set, including natural language question, visualization cards, and analytical insights
- **Pinned Visualization Box**: A visualization card within a chat that has been explicitly marked as important or saved by the user (persisted in the UI state)
- **Scheduled Report**: A chat query or pinned visualization that has been configured to re-execute on a recurring schedule
- **Recurrence Pattern**: A temporal schedule specification (e.g., "every Monday at 5 PM", "every 1st of month at 8 PM", "daily at 9 AM")
- **Schedule Execution**: A single automated run of a scheduled report at a scheduled time
- **Last Run Timestamp**: The date and time when a scheduled report was most recently executed
- **Step Functions State Machine**: An AWS service workflow engine that orchestrates the query re-execution and result persistence
- **Report Title/Summary**: A user-written descriptive name or summary for a scheduled report
- **Scheduled Reports Page**: A dedicated frontend route displaying all scheduled reports as a list with metadata and management controls
- **Report Detail View**: A full-page view of a specific scheduled report showing execution history, current results, and recurrence configuration
- **System**: Conversational BI Platform

---

## Requirements

### Requirement 1: Scheduling UI Elements in Chat Interface

**User Story:** As a user, I want quick access to scheduling controls while viewing chat results, so that I can easily create a scheduled report without leaving the chat interface.

#### Acceptance Criteria

1. WHEN a user is viewing a completed chat query with results, THE System SHALL display a clock icon in the card toolbar (adjacent to the bookmark/pin icon)
2. WHEN a user clicks the clock icon in the card toolbar, THE System SHALL navigate to the Scheduled Reports detail page with the current chat pre-populated for scheduling configuration
3. WHEN a user opens the three-dot menu in a visualization card toolbar, THE System SHALL display a "Schedule" option (in addition to existing "Rename" and "Delete" options)
4. WHEN a user clicks "Schedule" from the three-dot menu, THE System SHALL navigate to the Scheduled Reports detail page with the current chat pre-populated for scheduling configuration
5. WHEN the System displays the three-dot menu with scheduling options, THE System SHALL ensure the menu remains consistent with existing UI patterns and styling

### Requirement 2: Pinned Visualizations as Scheduling Unit

**User Story:** As a user, I want to ensure only my most important visualization results are eligible for automated re-execution, so that scheduled reports execute with predictable and relevant content.

#### Acceptance Criteria

1. WHEN a user attempts to schedule a chat query, THE System SHALL identify and display only the pinned/saved visualization boxes within that chat as eligible for scheduling
2. WHEN no pinned visualization boxes exist in a chat query, THE System SHALL display a message indicating that the query cannot be scheduled without first pinning a visualization box
3. WHEN a user selects a pinned visualization for scheduling, THE System SHALL capture the visualization's query parameters, chart type, and data aggregation settings
4. WHEN updating scheduled report execution results, THE System SHALL re-run only the pinned visualization boxes, not the entire chat conversation

### Requirement 3: Scheduled Reports List Page

**User Story:** As a user, I want to see an organized list of all my scheduled reports with key metadata, so that I can easily find and manage my automation workflows.

#### Acceptance Criteria

1. THE System SHALL provide a dedicated page (route: `/scheduled-reports`) that displays all scheduled reports for the authenticated user
2. WHEN the Scheduled Reports page loads, THE System SHALL display a list of scheduled reports with the following information for each report:
   - Report title/summary (user-provided name)
   - Next scheduled execution time
   - Last run timestamp (displayed with an info icon that shows full datetime on hover)
   - Recurrence pattern (e.g., "Every Monday at 5 PM")
   - Current status (active/paused/failed)
3. WHEN a scheduled report has never been executed, THE System SHALL display "Never run" or a similar indicator in the Last Run Timestamp field
4. WHEN a user clicks on a scheduled report in the list, THE System SHALL navigate to that report's detail view
5. WHEN the Scheduled Reports page is displayed, THE System SHALL include a "Create New Scheduled Report" button that navigates to the scheduling workflow entry point

### Requirement 4: Scheduled Report Detail View

**User Story:** As a user, I want to manage a specific scheduled report's configuration and view its execution history, so that I can adjust schedules and monitor report performance.

#### Acceptance Criteria

1. WHEN a user opens a scheduled report detail view, THE System SHALL display:
   - Report title/summary (editable text field)
   - Recurrence pattern selector (dropdown or custom form)
   - Selected pinned visualization boxes (read-only list)
   - Last run timestamp and status
   - Next scheduled execution time
   - Execution history list (most recent 10 runs showing timestamp, status, error messages if failed)
   - Current results (most recent execution data visualized)
2. WHEN a user modifies the report title in the detail view, THE System SHALL save the change to the backend after 500ms of inactivity (debouncing)
3. WHEN a user selects a recurrence pattern from the dropdown, THE Scheduler SHALL update the scheduled execution time and persist the new pattern to the backend
4. WHERE a scheduled report has failed in recent executions, THE System SHALL display error details and a "Retry Now" button
5. WHEN a user clicks "Retry Now", THE System SHALL immediately trigger a Step Functions execution for that report
6. WHEN the System displays execution history, THE System SHALL include pagination or infinite scroll for reports with more than 10 historical executions
7. WHERE a report is paused, THE System SHALL display "Paused" in the status field and provide a "Resume" button

### Requirement 5: Recurrence Pattern Selection

**User Story:** As a user, I want to specify flexible recurring schedules for my automated reports, so that I can align execution with my business cycles.

#### Acceptance Criteria

1. WHEN a user creates or edits a scheduled report, THE System SHALL present a recurrence pattern selector with predefined options:
   - Daily (default time: 9 AM)
   - Every weekday (default time: 9 AM)
   - Every Saturday (default time: 9 AM)
   - Every Sunday (default time: 9 AM)
   - Every Monday through Friday (with custom time selection)
   - Every 1st of the month (default time: 8 AM)
   - Every 15th of the month (default time: 8 AM)
   - Custom: every N days / every Nth day-of-week / every Nth day-of-month
2. WHEN a user selects a predefined pattern, THE System SHALL display a time selector (hour + minute, 24-hour format, timezone selector based on user's locale)
3. WHEN a user saves a recurrence pattern, THE System SHALL calculate the next execution time and validate that it is no more than 30 days in the future
4. IF the next execution time is more than 30 days in the future, THEN THE System SHALL return a validation error and require the user to adjust the pattern
5. WHEN the System calculates next execution times, THE System SHALL respect the user's configured timezone from their session/profile
6. WHERE a user selects "Custom" recurrence, THE System SHALL provide a form to specify interval (days/weeks/months), day-of-week/day-of-month constraints, and time

### Requirement 6: Step Functions Integration

**User Story:** As the system, I want to reliably orchestrate scheduled report executions using AWS Step Functions, so that retry logic, error handling, and audit trails are handled by a managed service.

#### Acceptance Criteria

1. WHEN a user creates a scheduled report, THE System SHALL create an AWS Step Functions state machine definition specific to that report
2. THE Step Functions state machine SHALL contain the following steps:
   - Validate report configuration (chat/visualization exists, user is authenticated)
   - Fetch the original chat query and pinned visualization parameters
   - Execute the query via the NLP API (same /query endpoint as interactive chat)
   - Capture the RenderedOutput with updated results
   - Store execution metadata (timestamp, status, query_id, latency)
   - Update the scheduled report record with the latest execution details
3. WHEN a query execution fails during scheduled run, THE Step Functions state machine SHALL automatically retry up to 2 times with exponential backoff (1s, 5s)
4. IF all retries are exhausted, THE Step Functions state machine SHALL:
   - Mark the report execution as "failed"
   - Store the error message and stack trace
   - Send an optional email notification to the user (if feature flag enabled)
5. WHEN a scheduled report execution completes successfully, THE System SHALL persist the RenderedOutput in a time-series store (S3 or DynamoDB) for historical comparison
6. WHEN retrieving scheduled report execution history, THE System SHALL query the execution metadata store and display the 10 most recent executions

### Requirement 7: Query Execution During Schedule Runs

**User Story:** As the system, I want to re-execute the user's saved query exactly as originally configured, so that scheduled results are consistent and comparable to original executions.

#### Acceptance Criteria

1. WHEN Step Functions triggers a query re-execution, THE System SHALL use the original StructuredIntent (entity_refs, query_type) from the saved chat, NOT re-parse the natural language query text
2. WHEN re-executing a pinned visualization query, THE System SHALL:
   - Bypass the NLP translation layer (use stored StructuredIntent directly)
   - Execute against the same data sources as the original query
   - Preserve the original chart type selection (or allow user override in scheduled report config)
3. WHEN the System executes a scheduled query, THE System SHALL capture latency and use the same caching layers (result cache, guardrail cache, render cache) as interactive queries
4. WHERE a data source has become unavailable, THE System SHALL mark the execution as "failed" and store the error message (not fall back to a different agent/source)

### Requirement 8: Scheduled Reports Persistence and Storage

**User Story:** As the system, I want to durably store all scheduled report configurations and execution history, so that data is never lost and audit trails are maintained.

#### Acceptance Criteria

1. WHEN a user creates a scheduled report, THE System SHALL persist the configuration to a database or S3-backed store with the following fields:
   - report_id (UUID)
   - user_id (authenticated user)
   - original_chat_id
   - pinned_visualization_ids (list)
   - recurrence_pattern (JSON: interval, day_of_week, day_of_month, time, timezone)
   - report_title/summary
   - is_active (boolean)
   - created_timestamp
   - last_modified_timestamp
2. WHEN a scheduled report execution completes, THE System SHALL create an execution record with:
   - execution_id (UUID)
   - report_id (reference to the scheduled report)
   - execution_timestamp (when it was scheduled to run)
   - actual_start_timestamp
   - status (success/failed/retrying)
   - query_latency_ms
   - rendered_output (full RenderedOutput JSON)
   - error_message (if applicable)
3. WHEN retrieving scheduled report history, THE System SHALL query efficiently by report_id and support filtering by date range or status
4. WHERE a user deletes a scheduled report, THE System SHALL:
   - Deactivate the Step Functions state machine execution schedule
   - Retain historical execution records for audit purposes (soft delete on the config, cascade delete only on explicit user action)

### Requirement 9: Authentication and Authorization

**User Story:** As the system, I want to ensure users can only view and manage their own scheduled reports, so that data is properly isolated.

#### Acceptance Criteria

1. WHEN a user accesses the `/scheduled-reports` page, THE System SHALL verify authentication (existing user session)
2. IF a user is not authenticated, THE System SHALL redirect to the login page
3. WHEN a user requests a scheduled report detail, THE System SHALL verify that the report's user_id matches the authenticated user_id
4. IF the user_id does not match, THE System SHALL return an HTTP 403 Forbidden response
5. WHEN updating or deleting a scheduled report, THE System SHALL enforce the same ownership check

### Requirement 10: Scheduled Report Naming and Management

**User Story:** As a user, I want to name and describe my scheduled reports in a way that helps me remember their purpose, so that I can quickly identify which reports matter most.

#### Acceptance Criteria

1. WHEN a user creates a scheduled report, THE System SHALL require a report title (non-empty string, max 255 characters)
2. WHEN a user creates a scheduled report, THE System SHALL optionally allow a description/summary field (max 1000 characters)
3. WHEN a user edits the report title or description, THE System SHALL persist the change with a debounce of 500ms
4. WHEN the System displays a scheduled report in the list or detail view, THE System SHALL show the title and description prominently
5. WHERE the title or description is too long to fit in the list view, THE System SHALL truncate with an ellipsis and show full text on hover

### Requirement 11: Schedule Activation and Deactivation

**User Story:** As a user, I want to temporarily pause scheduled reports without deleting them, so that I can stop automation without losing the configuration.

#### Acceptance Criteria

1. WHEN viewing a scheduled report detail, THE System SHALL display a toggle or button to pause/resume the report
2. WHEN a user pauses a scheduled report, THE System SHALL:
   - Set is_active = false in the configuration
   - Disable the Step Functions schedule rule
   - Display "Paused" in the status field
3. WHEN a user resumes a paused report, THE System SHALL:
   - Set is_active = true
   - Re-enable the Step Functions schedule rule
   - Calculate the next execution time (if in the past, execute immediately)
4. WHERE a report is paused for more than 30 days, THE System MAY display a suggestion to delete it (optional UX enhancement)

### Requirement 12: Deletion of Scheduled Reports

**User Story:** As a user, I want to permanently remove scheduled reports that I no longer need, so that I can keep my list clean.

#### Acceptance Criteria

1. WHEN viewing a scheduled report detail or list, THE System SHALL display a "Delete" button
2. WHEN a user clicks "Delete", THE System SHALL display a confirmation dialog with the report title and ask the user to confirm
3. WHEN a user confirms deletion, THE System SHALL:
   - Remove the report configuration from storage
   - Disable the Step Functions schedule rule
   - Preserve execution history for audit purposes (do not delete execution records)
4. AFTER deletion completes, THE System SHALL redirect to the Scheduled Reports list page

---

## Acceptance Criteria Testing Strategy

### Property-Based Testing Guidance

For the following requirements, **property-based testing is RECOMMENDED** to catch edge cases:

- **Requirement 5 (Recurrence Patterns)**: Properties such as "next execution time is always in the future" and "recurrence pattern round-trip (serialize → deserialize) preserves semantics"
- **Requirement 6 (Step Functions Retry Logic)**: Property: "failed executions are retried exactly N times with exponential backoff"
- **Requirement 8 (Persistence)**: Property: "scheduling config → persistence → retrieval produces identical object" (round-trip)

### Integration Testing

For the following requirements, **integration testing with 1-3 representative examples** is more appropriate:

- **Requirement 1 (UI Elements)**: Verify UI buttons navigate correctly (integration test with mocked backend)
- **Requirement 3 (List Page)**: Verify page loads and displays sample reports (integration test with mock data)
- **Requirement 6 (Step Functions)**: Verify state machine is created and scheduled (integration test against AWS Step Functions test harness)
- **Requirement 9 (Authorization)**: Verify 403 response for unauthorized user (integration test with mock auth)

### Unit Testing

For the following requirements, **unit testing** suffices:

- **Requirement 2 (Pinned Visualizations)**: Filter and validate logic
- **Requirement 5 (Time Calculation)**: Timezone-aware time math
- **Requirement 8 (Data Schema)**: Pydantic model validation
- **Requirement 10 (Title Truncation)**: String truncation logic
