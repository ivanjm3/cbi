# Implementation Plan: Scheduled Reports

## Overview

This plan implements the Scheduled Reports feature for the Conversational BI platform. The implementation is structured in phases: data models and types first, then backend services (Scheduling API on port 8005, Recurrence Calculator, Scheduler Manager, Step Functions definition), followed by frontend components (ScheduleButton, List Page, Detail Page, RecurrenceSelector, Zustand store), and finally integration wiring and testing. Python with FastAPI is used for backend; TypeScript with React/Zustand for frontend.

## Tasks

- [x] 1. Define data models and shared types
  - [x] 1.1 Create backend Pydantic models for scheduled reports
    - Create `src/models/scheduled_reports.py` with `RecurrencePattern`, `ScheduledReportConfig`, `CreateReportRequest`, `UpdateReportRequest`, and `ExecutionRecord` Pydantic models
    - Include field validators for `day_of_week` (0-6), `day_of_month` (1-31), `time_hour` (0-23), `time_minute` (0-59)
    - Include `title` max_length=255 min_length=1, `description` max_length=1000
    - Define `Literal` types for status fields: `"active" | "paused" | "failed"` and execution status: `"success" | "failed" | "retrying"`
    - _Requirements: 8.1, 8.2, 10.1, 10.2_

  - [ ]* 1.2 Write property tests for Pydantic model validation (Property 7)
    - **Property 7: Report title and description validation**
    - Use `hypothesis` to generate arbitrary strings and verify title accepts only `1 <= len <= 255`, description accepts only `len <= 1000`
    - Verify empty title always rejected, empty description always accepted
    - **Validates: Requirements 10.1, 10.2**

  - [x] 1.3 Create frontend TypeScript types for scheduled reports
    - Create `frontend/src/types/scheduledReports.ts` with interfaces: `RecurrencePattern`, `ScheduledReportListItem`, `ScheduledReportDetail`, `ExecutionHistoryItem`, `CreateReportRequest`, `UpdateReportRequest`
    - Match the backend API contract shapes from the design document
    - _Requirements: 8.1, 8.2, 3.2_

- [ ] 2. Implement Recurrence Calculator module
  - [x] 2.1 Implement `compute_next_execution` function
    - Create `src/services/recurrence_calculator.py`
    - Implement timezone-aware next execution computation using `zoneinfo` and `datetime`
    - Handle all pattern types: daily, weekday, weekly, monthly, custom
    - Validate that next execution is no more than 30 days in the future for non-custom patterns
    - _Requirements: 5.1, 5.3, 5.4, 5.5_

  - [x] 2.2 Implement `serialize_recurrence` and `deserialize_recurrence` functions
    - Convert `RecurrencePattern` to EventBridge cron/rate expression strings
    - Convert EventBridge expressions back to `RecurrencePattern` objects
    - _Requirements: 5.1, 5.6_

  - [x] 2.3 Implement `format_recurrence_display` function
    - Convert `RecurrencePattern` to human-readable strings (e.g., "Every Monday at 5:00 PM EST")
    - Handle all pattern types with proper timezone display
    - _Requirements: 3.2_

  - [ ]* 2.4 Write property tests for recurrence computation (Property 2)
    - **Property 2: Recurrence pattern computation**
    - Use `hypothesis` to generate valid RecurrencePatterns and reference timestamps
    - Verify: result is strictly future, within 30 days (non-custom), matches specified timezone hour/minute, falls on correct day_of_week/day_of_month
    - **Validates: Requirements 4.3, 5.3, 5.4, 5.5, 11.3**

- [ ] 3. Implement S3-backed data access layer
  - [x] 3.1 Create S3 repository for scheduled reports
    - Create `src/services/scheduled_reports_repository.py`
    - Implement CRUD operations: `create_report`, `get_report`, `get_reports_by_user`, `update_report`, `soft_delete_report`
    - Store report configs in S3: `s3://bucket/scheduled-reports/{user_id}/{report_id}.json`
    - Maintain an S3 index file: `s3://bucket/scheduled-reports-index.json` mapping user_id → list of report IDs
    - Handle serialization/deserialization between Pydantic models and JSON
    - _Requirements: 8.1, 8.3, 9.3_

  - [x] 3.2 Create S3 repository for execution records
    - Create `src/services/execution_records_repository.py`
    - Implement: `create_execution`, `get_executions_by_report` (in-memory sorting, paginated), `get_execution_by_id`
    - Store execution records in S3: `s3://bucket/scheduled-reports/executions/{report_id}/{execution_timestamp}.json`
    - Support page_size parameter and cursor-based pagination (via sorted in-memory results)
    - _Requirements: 8.2, 8.3, 6.5, 6.6_

  - [ ]* 3.3 Write property tests for config persistence round-trip (Property 3)
    - **Property 3: Scheduled report configuration round-trip**
    - Use `hypothesis` to generate valid `ScheduledReportConfig` objects
    - Serialize to JSON → persist to S3 → retrieve → deserialize back → assert equality
    - **Validates: Requirements 8.1**

  - [ ]* 3.4 Write property tests for execution record round-trip (Property 4)
    - **Property 4: Execution record persistence round-trip**
    - Use `hypothesis` to generate valid `ExecutionRecord` objects
    - Serialize to JSON → persist to S3 → retrieve → deserialize back → assert equality
    - **Validates: Requirements 6.5, 8.2**

  - [ ]* 3.5 Write property tests for execution history ordering (Property 9)
    - **Property 9: Execution history ordering and pagination**
    - Use `hypothesis` to generate sets of execution records for a report
    - Retrieve from S3, sort by timestamp desc, apply pagination with page_size N
    - Verify: count <= N, pages non-overlapping, order correct
    - **Validates: Requirements 6.6, 8.3**

- [ ] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement EventBridge Scheduler Manager
  - [x] 5.1 Implement SchedulerManager class
    - Create `src/services/scheduler_manager.py`
    - Implement `create_schedule`, `update_schedule`, `disable_schedule`, `enable_schedule`, `delete_schedule` methods
    - Use boto3 EventBridge Scheduler client to manage schedule rules
    - Each schedule targets the shared Step Functions state machine ARN with report_id as input
    - Use serialized recurrence pattern as the schedule expression
    - _Requirements: 6.1, 11.2, 11.3, 12.3_

  - [ ]* 5.2 Write property tests for pause/resume state transitions (Property 10)
    - **Property 10: Pause/resume state transitions**
    - Use `hypothesis` to generate active/paused reports
    - Verify: pause sets is_active=false, resume sets is_active=true with valid next_execution_time, transitions are idempotent
    - **Validates: Requirements 11.2, 11.3**

- [ ] 6. Implement Scheduling API service
  - [x] 6.1 Create FastAPI application skeleton for Scheduling API (port 8005)
    - Create `src/services/scheduling_api.py` with FastAPI app, CORS configuration, health endpoint
    - Set up dependency injection for S3 repositories and SchedulerManager
    - Add authentication middleware (extract user_id from session token)
    - _Requirements: 9.1, 9.2_

  - [x] 6.2 Implement POST /scheduled-reports endpoint
    - Validate request body (CreateReportRequest)
    - Verify referenced chat_id and pinned_visualization_ids exist (call internal APIs)
    - Fetch and store StructuredIntents for each pinned visualization
    - Compute next_execution_time using RecurrenceCalculator
    - Persist report config to S3 and update index
    - Create EventBridge schedule via SchedulerManager
    - Return 201 with report summary
    - _Requirements: 8.1, 2.1, 2.3, 5.3, 6.1, 10.1_

  - [x] 6.3 Implement GET /scheduled-reports and GET /scheduled-reports/{report_id} endpoints
    - List endpoint: read from S3 index, filter by user_id, return list of report summaries with recurrence_display
    - Detail endpoint: read from S3, verify ownership (403 if mismatch), return full config + execution summary
    - _Requirements: 3.1, 3.2, 4.1, 9.3, 9.4_

  - [x] 6.4 Implement PATCH /scheduled-reports/{report_id} endpoint
    - Support partial updates: title, description, recurrence_pattern
    - If recurrence changes: update EventBridge schedule, recompute next_execution_time
    - Apply debounce-friendly (idempotent) update semantics
    - Enforce ownership check
    - _Requirements: 4.2, 4.3, 9.5, 10.3_

  - [x] 6.5 Implement DELETE /scheduled-reports/{report_id} endpoint
    - Soft-delete report config (set deleted_at timestamp)
    - Disable and delete EventBridge schedule
    - Preserve execution records (do not cascade delete)
    - Enforce ownership check
    - _Requirements: 12.3, 8.4, 9.5_

  - [x] 6.6 Implement pause, resume, and retry endpoints
    - POST /scheduled-reports/{report_id}/pause: set is_active=false, disable EventBridge
    - POST /scheduled-reports/{report_id}/resume: set is_active=true, enable EventBridge, recompute next_execution_time
    - POST /scheduled-reports/{report_id}/retry: immediately trigger Step Functions execution
    - _Requirements: 11.1, 11.2, 11.3, 4.4, 4.5_

  - [x] 6.7 Implement GET /scheduled-reports/{report_id}/executions endpoint
    - Return paginated execution history (page, page_size params)
    - Sort by execution_timestamp descending
    - Include status, latency, error_message for each record
    - _Requirements: 4.6, 6.6, 8.3_

  - [ ]* 6.8 Write property tests for ownership enforcement (Property 6)
    - **Property 6: Ownership enforcement**
    - Use `hypothesis` to generate pairs of (requesting_user_id, report_owner_id)
    - Verify: operations succeed iff requesting_user_id == report_owner_id, otherwise 403
    - **Validates: Requirements 9.3, 9.5**

  - [ ]* 6.9 Write property tests for deletion preserving history (Property 11)
    - **Property 11: Deletion preserves execution history**
    - Use `hypothesis` to generate reports with N execution records
    - After deletion: verify execution records remain queryable with count == N
    - **Validates: Requirements 12.3**

- [ ] 7. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Define Step Functions state machine
  - [x] 8.1 Create Step Functions state machine definition (ASL JSON)
    - Create `src/services/step_functions_definition.json` with the state machine ASL
    - Define states: ValidateConfig, FetchIntent, ExecuteQuery (with retry 2x, backoff 1s/5s), StoreResults, UpdateMetadata, MarkFailed
    - Configure Catch blocks to route all errors to MarkFailed state
    - _Requirements: 6.2, 6.3, 6.4_

  - [x] 8.2 Implement Lambda handlers for Step Functions steps
    - Create `src/services/step_functions_handlers.py` with handler functions:
      - `validate_report_config`: check report exists in S3, is_active, user valid
      - `fetch_structured_intent`: retrieve stored StructuredIntent from S3
      - `execute_query`: POST to Orchestrator Hub with StructuredIntent (bypass NLP)
      - `store_execution_results`: write RenderedOutput to S3
      - `update_report_metadata`: write execution record to S3, update report's last_run fields in S3
      - `mark_execution_failed`: write failed execution record with error details to S3
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4_

  - [ ]* 8.3 Write property tests for StructuredIntent replay fidelity (Property 5)
    - **Property 5: Execution replays stored StructuredIntent**
    - Use `hypothesis` to generate StructuredIntent dicts
    - Verify: the intent passed to Orchestrator is byte-for-byte identical to stored intent
    - **Validates: Requirements 7.1, 2.4**

- [ ] 9. Implement frontend API client layer
  - [x] 9.1 Create scheduled reports API client
    - Create `frontend/src/api/scheduledReportsApi.ts`
    - Implement functions: `createReport`, `listReports`, `getReport`, `updateReport`, `deleteReport`, `pauseReport`, `resumeReport`, `retryReport`, `getExecutionHistory`
    - Base URL: configurable (default `http://localhost:8005`)
    - Include session token in Authorization header
    - _Requirements: 3.1, 4.1, 9.1_

- [ ] 10. Implement frontend Zustand store
  - [x] 10.1 Create scheduledReportsStore
    - Create `frontend/src/store/scheduledReportsStore.ts`
    - Implement state: `reports`, `currentReport`, `executionHistory`, `loading`, `error`
    - Implement actions: `fetchReports`, `fetchReportDetail`, `createReport`, `updateReport`, `deleteReport`, `pauseReport`, `resumeReport`, `retryReport`, `fetchExecutionHistory`
    - Wire actions to API client functions
    - _Requirements: 3.1, 4.1, 11.1, 12.1_

- [ ] 11. Implement frontend components
  - [x] 11.1 Add ScheduleButton to CardToolbar
    - Modify `frontend/src/components/CardToolbar.tsx` to add clock icon button
    - Button visible only when card is pinned (`card.pinned === true`)
    - Clicking navigates to `/scheduled-reports/new?chat_id={chatId}&viz_id={vizId}`
    - Add "Schedule" option to three-dot menu (alongside existing "Rename" and "Delete")
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2_

  - [ ]* 11.2 Write property tests for pinned card filtering (Property 1)
    - **Property 1: Pinned card filtering**
    - Use `fast-check` to generate arrays of CardState with mixed pinned values
    - Verify: scheduling eligibility filter returns only pinned===true cards, never unpinned
    - **Validates: Requirements 2.1**

  - [x] 11.3 Implement RecurrencePatternSelector component
    - Create `frontend/src/components/RecurrencePatternSelector.tsx`
    - Render predefined options: Daily, Every weekday, Every Saturday, Every Sunday, Mon-Fri, 1st of month, 15th of month, Custom
    - Include time selector (hour + minute in 24h format) and timezone selector
    - Custom mode: interval input (N), unit selector (days/weeks/months), day constraints
    - Emit `RecurrencePattern` object on change
    - _Requirements: 5.1, 5.2, 5.6_

  - [x] 11.4 Implement ScheduledReportsListPage component
    - Create `frontend/src/components/ScheduledReportsListPage.tsx`
    - Route: `/scheduled-reports`
    - Display list with: title, next_execution_time, last_run_timestamp (with info icon hover), recurrence_display, status badge
    - "Never run" indicator for reports without executions
    - "Create New Scheduled Report" button
    - Click row to navigate to detail page
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 11.5 Implement ScheduledReportDetailPage component
    - Create `frontend/src/components/ScheduledReportDetailPage.tsx`
    - Route: `/scheduled-reports/:reportId`
    - Display: editable title (debounced 500ms save), RecurrencePatternSelector, pinned viz list, status, next run time
    - Execution history table with pagination (10 per page)
    - Pause/Resume toggle, Delete button with confirmation dialog, Retry Now button (on failed reports)
    - Error display for failed executions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 11.1, 12.1, 12.2_

  - [ ]* 11.6 Write property tests for text truncation (Property 8)
    - **Property 8: Text truncation with ellipsis**
    - Use `fast-check` to generate arbitrary strings and max lengths
    - Verify: returns original if len <= max, returns exactly maxLength chars ending with "…" if longer, never exceeds maxLength
    - **Validates: Requirements 10.5**

- [ ] 12. Implement frontend routing and navigation
  - [x] 12.1 Add routes for scheduled reports pages
    - Update `frontend/src/App.tsx` to add routes: `/scheduled-reports` and `/scheduled-reports/:reportId`
    - Add navigation link in sidebar for "Scheduled Reports"
    - Handle auth redirect (unauthenticated → login page)
    - _Requirements: 3.1, 9.1, 9.2_

- [ ] 13. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Integration wiring and end-to-end flow
  - [x] 14.1 Wire CardToolbar schedule action to create report flow
    - Connect ScheduleButton click → navigate to detail page in create mode
    - Pre-populate chat_id and pinned_visualization_ids from current context
    - Handle case where no pinned cards exist (show message per Requirement 2.2)
    - _Requirements: 1.2, 1.4, 2.1, 2.2_

  - [x] 14.2 Wire Scheduling API to existing Orchestrator Hub
    - Ensure Step Functions execute_query handler calls Orchestrator Hub's internal endpoint with StructuredIntent
    - Bypass NLP Translator (use stored intent directly)
    - Verify same caching layers (result cache, guardrail cache, render cache) are used
    - _Requirements: 7.1, 7.2, 7.3_

  - [x] 14.3 Wire frontend store to API and update components
    - Connect all component actions to Zustand store methods
    - Implement loading states (skeleton shimmer) and error handling (inline errors, retry buttons)
    - Implement delete confirmation dialog with report title
    - _Requirements: 3.4, 4.4, 12.2, 12.3, 12.4_

  - [ ]* 14.4 Write integration tests for full create/execute/list flow
    - Test: create report → verify DynamoDB record + EventBridge schedule created
    - Test: trigger execution → verify execution record written + S3 output stored
    - Test: list reports → verify correct reports returned for user
    - Test: auth enforcement → 401 for unauthenticated, 403 for wrong user
    - _Requirements: 6.1, 8.1, 8.2, 9.1, 9.3_

  - [ ]* 14.5 Write integration tests for pause/resume/delete flows
    - Test: pause → verify EventBridge disabled, is_active=false
    - Test: resume → verify EventBridge re-enabled, next_execution_time computed
    - Test: delete → verify soft-delete, schedule removed, execution history preserved
    - _Requirements: 11.2, 11.3, 12.3_

- [ ] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document (11 properties total)
- Backend uses Python (FastAPI, Pydantic, boto3, hypothesis); Frontend uses TypeScript (React, Zustand, fast-check, vitest)
- The Scheduling API runs on port 8005, consistent with the existing multi-service architecture (NLP: 8001, Orchestrator: 8002, Guardrail: 8003, Viz Renderer: 8004)
- Step Functions use a shared state machine with per-report EventBridge Scheduler rules
- S3 storage: `s3://bucket/scheduled-reports/{user_id}/{report_id}.json` for configs, `s3://bucket/scheduled-reports/executions/{report_id}/{execution_timestamp}.json` for execution records
- S3 index file: `s3://bucket/scheduled-reports-index.json` maintains user → report mappings for fast list operations

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.3"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["3.1", "3.2"] },
    { "id": 4, "tasks": ["3.3", "3.4", "3.5", "5.1"] },
    { "id": 5, "tasks": ["5.2", "6.1"] },
    { "id": 6, "tasks": ["6.2", "6.3", "8.1", "9.1"] },
    { "id": 7, "tasks": ["6.4", "6.5", "6.6", "6.7", "8.2"] },
    { "id": 8, "tasks": ["6.8", "6.9", "8.3", "10.1"] },
    { "id": 9, "tasks": ["11.1", "11.3", "11.4"] },
    { "id": 10, "tasks": ["11.2", "11.5", "11.6", "12.1"] },
    { "id": 11, "tasks": ["14.1", "14.2"] },
    { "id": 12, "tasks": ["14.3", "14.4"] },
    { "id": 13, "tasks": ["14.5"] }
  ]
}
```
