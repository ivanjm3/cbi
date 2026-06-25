/**
 * API integration layer for the Scheduled Reports service.
 * Implements CRUD operations for scheduled reports and execution history.
 * Includes session token authentication and error handling.
 *
 * Base URL: Configurable via VITE_SCHEDULING_API_URL environment variable
 * Defaults to http://localhost:8005
 */

import type {
  CreateReportRequest,
  CreateReportResponse,
  ExecutionHistoryResponse,
  ListReportsResponse,
  ScheduledReportDetail,
  UpdateReportRequest,
} from '../types/scheduledReports';

export const API_BASE =
  import.meta.env.VITE_SCHEDULING_API_URL ??
  (import.meta.env.DEV ? 'http://localhost:8005' : '');

const TIMEOUT_MS = 30_000; // 30-second timeout for API calls
const RETRY_TIMEOUT_MS = 180_000; // 3-minute timeout for "Run Now" (executes full query pipeline)

/**
 * Custom error class for Scheduled Reports API errors.
 * Includes HTTP status code, message, and optional error details.
 */
export class ScheduledReportsApiError extends Error {
  status: number;
  details?: Record<string, unknown>;

  constructor(
    status: number,
    message: string,
    details?: Record<string, unknown>,
  ) {
    super(message);
    this.name = 'ScheduledReportsApiError';
    this.status = status;
    this.details = details;
  }
}

/**
 * Extract session token from browser storage or session context.
 * For MVP, can use a default token or fetch from session management.
 *
 * @returns Session token string
 */
function getSessionToken(): string {
  // Try to get from sessionStorage
  const token = sessionStorage.getItem('session_token');
  if (token) {
    return token;
  }

  // Try to get from localStorage as fallback
  const storedToken = localStorage.getItem('session_token');
  if (storedToken) {
    return storedToken;
  }

  // For MVP, return a mock token if none available
  // In production, this should redirect to login
  return '';
}

/**
 * Resolve a stable user identifier for the current browser session.
 *
 * The scheduling API requires either an Authorization bearer token or an
 * X-User-ID header. Until full auth is wired up, we use a persistent
 * per-browser id so requests are authorized and reports are scoped
 * consistently to the same user.
 *
 * @returns User ID string
 */
function getUserId(): string {
  // Prefer an explicitly provisioned user id if present.
  const explicit =
    sessionStorage.getItem('user_id') ?? localStorage.getItem('user_id');
  if (explicit) {
    return explicit;
  }

  // Otherwise generate and persist a stable anonymous id for this browser.
  let generated = localStorage.getItem('cbi_user_id');
  if (!generated) {
    const rand =
      typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : Math.random().toString(36).slice(2);
    generated = `user-${rand}`;
    try {
      localStorage.setItem('cbi_user_id', generated);
    } catch {
      // localStorage may be unavailable; fall back to the in-memory value.
    }
  }
  return generated;
}

/**
 * Build Authorization headers with session token.
 * Includes Bearer token in Authorization header.
 *
 * @returns Headers object with Authorization header
 */
function buildHeaders(): HeadersInit {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  };

  const token = getSessionToken();
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  // Always send a user identifier so the scheduling API can authorize the
  // request. The backend accepts X-User-ID when no bearer token is present.
  headers['X-User-ID'] = getUserId();

  return headers;
}

/**
 * Handle API response errors and throw ScheduledReportsApiError.
 * Extracts error message from response body or HTTP status.
 * For 422 validation errors, formats detailed field-level errors.
 *
 * @param response Fetch response object
 * @param responseBody Parsed JSON response body
 * @throws ScheduledReportsApiError with appropriate status and message
 */
async function handleErrorResponse(
  response: Response,
  responseBody: unknown,
): Promise<never> {
  let message = '';
  let details: Record<string, unknown> | undefined;

  // Extract error message from response body
  if (
    responseBody &&
    typeof responseBody === 'object' &&
    'error_message' in responseBody
  ) {
    message = String(responseBody.error_message);
    details = responseBody as Record<string, unknown>;
  } else if (
    responseBody &&
    typeof responseBody === 'object' &&
    'detail' in responseBody
  ) {
    const detail = (responseBody as Record<string, unknown>).detail;
    
    // Handle Pydantic validation errors (422)
    if (response.status === 422 && Array.isArray(detail)) {
      // detail is an array of validation error objects
      const errors = (detail as Array<Record<string, unknown>>).map((err) => {
        const loc = (err.loc as Array<string | number>)?.join('.');
        const msg = String(err.msg ?? 'validation error');
        return `${loc}: ${msg}`;
      });
      message = `Validation error: ${errors.join('; ')}`;
    } else if (typeof detail === 'string') {
      message = detail;
    } else {
      message = 'Unknown error';
    }
    details = responseBody as Record<string, unknown>;
  }

  // Map HTTP status codes to user-friendly messages
  switch (response.status) {
    case 401:
      message = message || 'Unauthorized. Please log in.';
      break;
    case 403:
      message = message || 'Forbidden. You do not have permission to access this resource.';
      break;
    case 404:
      message = message || 'Report not found.';
      break;
    case 422:
      message = message || 'Validation error. Please check your input.';
      break;
    case 503:
      message = message || 'Service unavailable. Please try again later.';
      break;
    default:
      if (!message) {
        message = `HTTP ${response.status}: ${response.statusText}`;
      }
  }

  throw new ScheduledReportsApiError(response.status, message, details);
}

/**
 * Create a new scheduled report.
 *
 * @param request CreateReportRequest with title, description, chat_id, visualizations, and recurrence
 * @returns Promise resolving to report summary with report_id and next_execution_time
 * @throws ScheduledReportsApiError on failure
 *
 * @example
 * ```typescript
 * const report = await createReport({
 *   title: 'Weekly Sales Report',
 *   description: 'Revenue breakdown every Monday',
 *   original_chat_id: 'chat-123',
 *   pinned_visualization_ids: ['viz-456'],
 *   recurrence_pattern: {
 *     type: 'weekly',
 *     day_of_week: 1,
 *     time_hour: 17,
 *     time_minute: 0,
 *     timezone: 'America/New_York'
 *   }
 * });
 * ```
 */
export async function createReport(
  request: CreateReportRequest,
): Promise<CreateReportResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/scheduled-reports`, {
      method: 'POST',
      headers: buildHeaders(),
      body: JSON.stringify(request),
      signal: controller.signal,
    });

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as CreateReportResponse;
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * List all scheduled reports for the authenticated user.
 *
 * @returns Promise resolving to object with reports array and total_count
 * @throws ScheduledReportsApiError on failure
 *
 * @example
 * ```typescript
 * const { reports, total_count } = await listReports();
 * reports.forEach(report => {
 *   console.log(`${report.title}: ${report.recurrence_display}`);
 * });
 * ```
 */
export async function listReports(): Promise<ListReportsResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/scheduled-reports`, {
      method: 'GET',
      headers: buildHeaders(),
      signal: controller.signal,
    });

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as ListReportsResponse;
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Get detailed information about a specific scheduled report.
 *
 * @param reportId UUID of the scheduled report to retrieve
 * @returns Promise resolving to full ScheduledReportDetail with configuration and metadata
 * @throws ScheduledReportsApiError on failure (404 if not found, 403 if not owned by user)
 *
 * @example
 * ```typescript
 * const report = await getReport('rpt-uuid-789');
 * console.log(`Report: ${report.title}`);
 * console.log(`Next run: ${report.next_execution_time}`);
 * ```
 */
export async function getReport(reportId: string): Promise<ScheduledReportDetail> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}`,
      {
        method: 'GET',
        headers: buildHeaders(),
        signal: controller.signal,
      },
    );

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as ScheduledReportDetail;
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Update a scheduled report with partial changes.
 * Only provided fields are updated; omitted fields are left unchanged.
 *
 * @param reportId UUID of the scheduled report to update
 * @param updates Partial UpdateReportRequest with title, description, and/or recurrence_pattern
 * @returns Promise resolving to updated ScheduledReportDetail
 * @throws ScheduledReportsApiError on failure (404 if not found, 403 if not owned by user)
 *
 * @example
 * ```typescript
 * const updated = await updateReport('rpt-uuid-789', {
 *   title: 'Updated Report Title',
 *   recurrence_pattern: {
 *     type: 'daily',
 *     time_hour: 9,
 *     time_minute: 0,
 *     timezone: 'UTC'
 *   }
 * });
 * ```
 */
export async function updateReport(
  reportId: string,
  updates: Partial<UpdateReportRequest>,
): Promise<ScheduledReportDetail> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}`,
      {
        method: 'PATCH',
        headers: buildHeaders(),
        body: JSON.stringify(updates),
        signal: controller.signal,
      },
    );

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as ScheduledReportDetail;
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Delete a scheduled report (soft-delete).
 * The report configuration is removed, but execution history is preserved.
 *
 * @param reportId UUID of the scheduled report to delete
 * @returns Promise that resolves when deletion is complete
 * @throws ScheduledReportsApiError on failure (404 if not found, 403 if not owned by user)
 *
 * @example
 * ```typescript
 * await deleteReport('rpt-uuid-789');
 * console.log('Report deleted');
 * ```
 */
export async function deleteReport(reportId: string): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}`,
      {
        method: 'DELETE',
        headers: buildHeaders(),
        signal: controller.signal,
      },
    );

    // DELETE returns 204 No Content on success
    if (!response.ok && response.status !== 204) {
      const responseBody = await response.json();
      await handleErrorResponse(response, responseBody);
    }
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Pause a scheduled report.
 * The report configuration is preserved but the schedule is disabled.
 *
 * @param reportId UUID of the scheduled report to pause
 * @returns Promise resolving to response with status field
 * @throws ScheduledReportsApiError on failure
 *
 * @example
 * ```typescript
 * const result = await pauseReport('rpt-uuid-789');
 * console.log(`Report paused: ${result.status}`);
 * ```
 */
export async function pauseReport(
  reportId: string,
): Promise<{ status: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}/pause`,
      {
        method: 'POST',
        headers: buildHeaders(),
        signal: controller.signal,
      },
    );

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as { status: string };
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Resume a paused scheduled report.
 * The schedule is re-enabled and the next execution time is recomputed.
 *
 * @param reportId UUID of the scheduled report to resume
 * @returns Promise resolving to response with status field
 * @throws ScheduledReportsApiError on failure
 *
 * @example
 * ```typescript
 * const result = await resumeReport('rpt-uuid-789');
 * console.log(`Report resumed: ${result.status}`);
 * ```
 */
export async function resumeReport(
  reportId: string,
): Promise<{ status: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}/resume`,
      {
        method: 'POST',
        headers: buildHeaders(),
        signal: controller.signal,
      },
    );

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as { status: string };
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Trigger an immediate execution of a scheduled report.
 * Useful for testing or re-running a failed report.
 *
 * @param reportId UUID of the scheduled report to execute
 * @returns Promise resolving to response with status and optional execution_arn
 * @throws ScheduledReportsApiError on failure
 *
 * @example
 * ```typescript
 * const result = await retryReport('rpt-uuid-789');
 * console.log(`Execution triggered: ${result.execution_arn}`);
 * ```
 */
export async function retryReport(
  reportId: string,
): Promise<{ status: string; execution_arn?: string }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), RETRY_TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}/retry`,
      {
        method: 'POST',
        headers: buildHeaders(),
        signal: controller.signal,
      },
    );

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as { status: string; execution_arn?: string };
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Get paginated execution history for a scheduled report.
 * Returns the most recent executions sorted by timestamp descending.
 *
 * @param reportId UUID of the scheduled report
 * @param page Page number (1-indexed, default: 1)
 * @param page_size Number of items per page (default: 10)
 * @returns Promise resolving to paginated execution history with metadata
 * @throws ScheduledReportsApiError on failure
 *
 * @example
 * ```typescript
 * const history = await getExecutionHistory('rpt-uuid-789', 1, 10);
 * console.log(`Total executions: ${history.total_count}`);
 * history.executions.forEach(execution => {
 *   console.log(`${execution.execution_timestamp}: ${execution.status}`);
 * });
 * ```
 */
export async function getExecutionHistory(
  reportId: string,
  page: number = 1,
  page_size: number = 10,
): Promise<ExecutionHistoryResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const baseUrl = `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}/executions`;
    const params = new URLSearchParams({ page: String(page), page_size: String(page_size) });
    const fullUrl = `${baseUrl}?${params.toString()}`;

    const response = await fetch(fullUrl, {
      method: 'GET',
      headers: buildHeaders(),
      signal: controller.signal,
    });

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as ExecutionHistoryResponse;
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}


/**
 * Add a new prompt to a scheduled report.
 * Runs the query through the NLP pipeline and adds the result to the report.
 * Uses RETRY_TIMEOUT_MS since it executes the full NLP query pipeline.
 *
 * @param reportId UUID of the scheduled report
 * @param queryText The natural language query to add
 * @returns Promise resolving to {viz_id, rendered_output}
 * @throws ScheduledReportsApiError on failure
 */
export async function addPrompt(
  reportId: string,
  queryText: string,
): Promise<{ viz_id: string; rendered_output: Record<string, unknown> }> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), RETRY_TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}/prompts`,
      {
        method: 'POST',
        headers: buildHeaders(),
        body: JSON.stringify({ query_text: queryText }),
        signal: controller.signal,
      },
    );

    const responseBody = await response.json();

    if (!response.ok) {
      await handleErrorResponse(response, responseBody);
    }

    return responseBody as { viz_id: string; rendered_output: Record<string, unknown> };
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. The query took too long.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Delete a prompt from a scheduled report.
 * Removes the visualization from the report configuration.
 *
 * @param reportId UUID of the scheduled report
 * @param vizId UUID of the visualization/prompt to remove
 * @returns Promise that resolves when deletion is complete
 * @throws ScheduledReportsApiError on failure
 */
export async function deletePrompt(
  reportId: string,
  vizId: string,
): Promise<void> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(
      `${API_BASE}/scheduled-reports/${encodeURIComponent(reportId)}/prompts/${encodeURIComponent(vizId)}`,
      {
        method: 'DELETE',
        headers: buildHeaders(),
        signal: controller.signal,
      },
    );

    // DELETE returns 204 No Content on success
    if (!response.ok && response.status !== 204) {
      const responseBody = await response.json();
      await handleErrorResponse(response, responseBody);
    }
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ScheduledReportsApiError(408, 'Request timeout. Please try again.');
    }
    if (err instanceof ScheduledReportsApiError) {
      throw err;
    }
    throw new ScheduledReportsApiError(0, 'Network error. Please check your connection.');
  } finally {
    clearTimeout(timeoutId);
  }
}
