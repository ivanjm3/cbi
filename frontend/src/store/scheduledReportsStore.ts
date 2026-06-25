/**
 * Zustand Store for Scheduled Reports Management
 *
 * Manages scheduled reports state and integrates with the Scheduling API (port 8005).
 * Handles list/detail views, CRUD operations, execution history, and error states.
 *
 * Requirements: 3.1, 4.1, 11.1, 12.1
 */

import { create } from 'zustand';
import type {
  ScheduledReportsState,
  ScheduledReportListItem,
  ScheduledReportDetail,
  ExecutionHistoryItem,
  CreateReportRequest,
  UpdateReportRequest,
} from '../types/scheduledReports';
import * as scheduledReportsApi from '../api/scheduledReportsApi';

/**
 * Initial state for the scheduled reports store
 */
const initialState = {
  reports: [] as ScheduledReportListItem[],
  currentReport: null as ScheduledReportDetail | null,
  executionHistory: [] as ExecutionHistoryItem[],
  loading: false,
  error: null as string | null,
  currentPage: 1,
  pageSize: 10,
  totalExecutions: 0,
};

/**
 * Create the scheduled reports Zustand store
 *
 * Provides:
 * - State for reports list, current report detail, and execution history
 * - Loading and error states for async operations
 * - Pagination state for execution history
 * - Actions for CRUD operations and history fetching
 */
export const useScheduledReportsStore = create<ScheduledReportsState>()(
  (set, get) => ({
    ...initialState,

    // =========================================================================
    // FETCH OPERATIONS
    // =========================================================================

    /**
     * Fetch all scheduled reports for the authenticated user
     * Sets loading state, updates reports list, clears error on success
     */
    fetchReports: async () => {
      set({ loading: true, error: null });
      try {
        const response = await scheduledReportsApi.listReports();
        set({
          reports: response.reports,
          loading: false,
          error: null,
        });
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        set({
          error: errorMessage,
          loading: false,
        });
      }
    },

    /**
     * Fetch detailed information about a specific scheduled report
     * Sets loading state, updates currentReport, clears error on success
     */
    fetchReportDetail: async (reportId: string) => {
      set({ loading: true, error: null });
      try {
        const report = await scheduledReportsApi.getReport(reportId);
        set({
          currentReport: report,
          loading: false,
          error: null,
        });
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        set({
          error: errorMessage,
          loading: false,
        });
      }
    },

    /**
     * Fetch paginated execution history for a specific report
     * Defaults to page 1 if not provided
     * Updates executionHistory, currentPage, totalExecutions, and clears error
     */
    fetchExecutionHistory: async (reportId: string, page?: number) => {
      const effectivePage = page ?? 1;
      const state = get();
      set({ loading: true, error: null });

      try {
        const response = await scheduledReportsApi.getExecutionHistory(
          reportId,
          effectivePage,
          state.pageSize,
        );

        set({
          executionHistory: response.executions,
          currentPage: response.page,
          totalExecutions: response.total_count,
          loading: false,
          error: null,
        });
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        set({
          error: errorMessage,
          loading: false,
        });
      }
    },

    // =========================================================================
    // CREATE, UPDATE, DELETE OPERATIONS
    // =========================================================================

    /**
     * Create a new scheduled report
     * Returns the created report_id on success, empty string on error
     * Automatically refreshes the reports list on success
     */
    createReport: async (config: CreateReportRequest) => {
      set({ loading: true, error: null });
      try {
        const response = await scheduledReportsApi.createReport(config);
        const { report_id } = response;

        // Refresh reports list to include the new report
        const state = get();
        await state.fetchReports();

        set({ loading: false, error: null });
        return report_id;
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        set({
          error: errorMessage,
          loading: false,
        });
        return '';
      }
    },

    /**
     * Update an existing scheduled report with partial changes
     * Updates currentReport with the response, refreshes list, clears error
     */
    updateReport: async (reportId: string, updates: Partial<UpdateReportRequest>) => {
      set({ loading: true, error: null });
      try {
        const updated = await scheduledReportsApi.updateReport(reportId, updates);

        // Update currentReport and refresh list
        const state = get();
        await state.fetchReports();

        set({
          currentReport: updated,
          loading: false,
          error: null,
        });
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        // For recurrence updates, log the error but don't fail — the config may have updated
        // even if the EventBridge schedule failed to update (IAM permission issue)
        console.warn(`Update partially succeeded: ${errorMessage}`);
        set({
          error: errorMessage,
          loading: false,
        });
      }
    },

    /**
     * Delete a scheduled report
     * Clears currentReport, refreshes list, clears error on success
     */
    deleteReport: async (reportId: string) => {
      set({ loading: true, error: null });
      try {
        await scheduledReportsApi.deleteReport(reportId);

        // Clear current report and refresh list
        const state = get();
        await state.fetchReports();

        set({
          currentReport: null,
          loading: false,
          error: null,
        });
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        set({
          error: errorMessage,
          loading: false,
        });
      }
    },

    // =========================================================================
    // PAUSE, RESUME, RETRY OPERATIONS
    // =========================================================================

    /**
     * Pause a scheduled report
     * Refreshes both detail and list views
     */
    pauseReport: async (reportId: string) => {
      set({ loading: true, error: null });
      try {
        await scheduledReportsApi.pauseReport(reportId);

        // Refresh report detail and list
        const state = get();
        await state.fetchReportDetail(reportId);
        await state.fetchReports();

        set({ loading: false });
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        set({
          error: errorMessage,
          loading: false,
        });
      }
    },

    /**
     * Resume a paused scheduled report
     * Refreshes both detail and list views
     */
    resumeReport: async (reportId: string) => {
      set({ loading: true, error: null });
      try {
        await scheduledReportsApi.resumeReport(reportId);

        // Refresh report detail and list
        const state = get();
        await state.fetchReportDetail(reportId);
        await state.fetchReports();

        set({ loading: false });
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        set({
          error: errorMessage,
          loading: false,
        });
      }
    },

    /**
     * Trigger an immediate execution/retry of a scheduled report
     * Refreshes execution history
     */
    retryReport: async (reportId: string) => {
      set({ loading: true, error: null });
      try {
        await scheduledReportsApi.retryReport(reportId);

        // Refresh execution history (start from page 1)
        const state = get();
        await state.fetchExecutionHistory(reportId, 1);

        set({ loading: false });
      } catch (err) {
        const errorMessage = extractErrorMessage(err);
        set({
          error: errorMessage,
          loading: false,
        });
      }
    },

    // =========================================================================
    // HELPER ACTIONS
    // =========================================================================

    /**
     * Clear the error message
     */
    clearError: () => {
      set({ error: null });
    },

    /**
     * Clear the current report detail view
     */
    clearCurrentReport: () => {
      set({ currentReport: null });
    },

    /**
     * Set the current page for execution history pagination
     * Automatically fetches execution history for the current report
     */
    setCurrentPage: (page: number) => {
      set({ currentPage: page });
      const state = get();
      if (state.currentReport?.report_id) {
        state.fetchExecutionHistory(state.currentReport.report_id, page);
      }
    },

    /**
     * Reset store to initial state
     */
    reset: () => {
      set(initialState);
    },
  }),
);

/**
 * Helper function to extract user-friendly error messages from API errors
 * Handles ScheduledReportsApiError and generic Error types
 */
function extractErrorMessage(err: unknown): string {
  if (err instanceof scheduledReportsApi.ScheduledReportsApiError) {
    return err.message;
  }

  if (err instanceof Error) {
    return err.message;
  }

  return 'An unexpected error occurred';
}
