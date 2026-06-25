/**
 * TypeScript types for the Scheduled Reports feature.
 *
 * These interfaces mirror the backend API contract for scheduled report
 * configurations, recurrence patterns, and execution history.
 */

// ---------------------------------------------------------------------------
// Recurrence Pattern Types
// ---------------------------------------------------------------------------

/** Recurrence schedule specification for a scheduled report */
export interface RecurrencePattern {
  type: 'daily' | 'weekday' | 'weekly' | 'monthly' | 'custom';
  day_of_week?: number | null; // 0=Sunday, 6=Saturday
  day_of_month?: number | null; // 1-31
  time_hour: number; // 0-23
  time_minute: number; // 0-59
  timezone: string; // IANA timezone, e.g. "America/New_York"
  custom_interval?: number | null; // every N days/weeks/months
  custom_unit?: 'days' | 'weeks' | 'months' | null;
}

// ---------------------------------------------------------------------------
// Scheduled Report Configuration
// ---------------------------------------------------------------------------

/** Status of a scheduled report */
export type ScheduledReportStatus = 'active' | 'paused' | 'failed';

/** Status of an execution */
export type ExecutionStatus = 'success' | 'failed' | 'retrying' | 'skipped';

/** Full scheduled report configuration (detail view) */
export interface ScheduledReportDetail {
  report_id: string;
  user_id: string;
  title: string;
  description: string;
  original_chat_id: string;
  pinned_visualization_ids: string[];
  structured_intents: Record<string, Record<string, unknown>>;
  query_texts: Record<string, string>;
  recurrence_pattern: RecurrencePattern;
  is_active: boolean;
  schedule_arn: string | null;
  next_execution_time: string | null; // ISO8601
  last_run_timestamp: string | null; // ISO8601
  last_run_status: ScheduledReportStatus | null;
  created_at: string; // ISO8601
  updated_at: string; // ISO8601
  deleted_at: string | null; // ISO8601
}

/** Scheduled report list item (summary for list view) */
export interface ScheduledReportListItem {
  report_id: string;
  title: string;
  next_execution_time: string | null; // ISO8601
  last_run_timestamp: string | null; // ISO8601
  recurrence_display: string; // e.g., "Every Monday at 5:00 PM EST"
  status: ScheduledReportStatus;
}

// ---------------------------------------------------------------------------
// Execution History
// ---------------------------------------------------------------------------

/** A single execution record for a scheduled report */
export interface ExecutionHistoryItem {
  execution_id: string;
  report_id: string;
  execution_timestamp: string; // ISO8601
  actual_start_timestamp: string; // ISO8601
  actual_end_timestamp: string | null; // ISO8601
  status: ExecutionStatus;
  query_latency_ms: number | null;
  rendered_output?: Record<string, unknown> | null; // Full RenderedOutput JSON (chart/text)
  rendered_output_s3_key: string | null;
  error_message: string | null;
  retry_count: number;
  step_functions_execution_arn: string | null;
}

/** Paginated execution history response */
export interface ExecutionHistoryResponse {
  executions: ExecutionHistoryItem[];
  total_count: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// API Request/Response Types
// ---------------------------------------------------------------------------

/** Request body for creating a new scheduled report */
export interface CreateReportRequest {
  title: string;
  description?: string;
  original_chat_id: string;
  pinned_visualization_ids: string[];
  recurrence_pattern: RecurrencePattern;
  /** Real StructuredIntents captured from the cards (viz_id -> intent) */
  structured_intents?: Record<string, Record<string, unknown>>;
  /** Original query text per visualization for replay */
  query_texts?: Record<string, string>;
}

/** Request body for updating a scheduled report */
export interface UpdateReportRequest {
  title?: string;
  description?: string;
  recurrence_pattern?: RecurrencePattern;
}

/** Response from create report endpoint */
export interface CreateReportResponse {
  report_id: string;
  title: string;
  next_execution_time: string | null; // ISO8601
  status: ScheduledReportStatus;
  created_at: string; // ISO8601
}

/** Response from list reports endpoint */
export interface ListReportsResponse {
  reports: ScheduledReportListItem[];
  total_count: number;
}

// ---------------------------------------------------------------------------
// Store State Types
// ---------------------------------------------------------------------------

/** Zustand store state for scheduled reports */
export interface ScheduledReportsState {
  // State
  reports: ScheduledReportListItem[];
  currentReport: ScheduledReportDetail | null;
  executionHistory: ExecutionHistoryItem[];
  loading: boolean;
  error: string | null;
  currentPage: number;
  pageSize?: number;
  totalExecutions?: number;

  // Actions
  fetchReports: () => Promise<void>;
  fetchReportDetail: (reportId: string) => Promise<void>;
  createReport: (config: CreateReportRequest) => Promise<string>;
  updateReport: (reportId: string, updates: UpdateReportRequest) => Promise<void>;
  deleteReport: (reportId: string) => Promise<void>;
  pauseReport: (reportId: string) => Promise<void>;
  resumeReport: (reportId: string) => Promise<void>;
  retryReport: (reportId: string) => Promise<void>;
  fetchExecutionHistory: (reportId: string, page?: number, pageSize?: number) => Promise<void>;
  clearError: () => void;
  clearCurrentReport: () => void;
  setCurrentPage: (page: number) => void;
  reset: () => void;
}
