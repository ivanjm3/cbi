/**
 * ScheduledReportsListPage component.
 *
 * Displays a paginated list of scheduled reports for the authenticated user.
 * Each report shows: title, next execution time, last run timestamp, recurrence pattern, and status.
 * Includes a "Create New Scheduled Report" button and row navigation to detail view.
 *
 * Features:
 * - List view with key metadata for each report
 * - "Never run" indicator for reports without execution history
 * - Status badges (active/paused/failed)
 * - Info tooltip for last run timestamp (full datetime on hover)
 * - Loading shimmer and error states
 * - Click row to navigate to detail page
 * - Create new report button
 *
 * Route: /scheduled-reports
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
 */

import { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useScheduledReportsStore } from '../store/scheduledReportsStore';
import type { ScheduledReportListItem } from '../types/scheduledReports';

export function ScheduledReportsListPage() {
  const navigate = useNavigate();
  const { reports, loading, error, fetchReports, clearError, pauseReport, resumeReport, deleteReport } = useScheduledReportsStore();
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Fetch reports on mount
  useEffect(() => {
    fetchReports();
  }, []);

  /**
   * Navigate to detail page for a specific report
   */
  const handleRowClick = (reportId: string) => {
    navigate(`/scheduled-reports/${reportId}`);
  };

  /**
   * Navigate to create new report page
   */
  const handleCreateNew = () => {
    navigate('/scheduled-reports/new');
  };

  /**
   * Handle pause/resume action
   */
  const handleTogglePause = async (e: React.MouseEvent, reportId: string, isActive: boolean) => {
    e.stopPropagation();
    try {
      if (isActive) {
        await pauseReport(reportId);
      } else {
        await resumeReport(reportId);
      }
      await fetchReports();
    } catch {
      // Error already in store
    }
  };

  /**
   * Handle delete action
   */
  const handleDelete = async (e: React.MouseEvent, reportId: string) => {
    e.stopPropagation();
    setDeleteConfirm(reportId);
  };

  /**
   * Confirm and execute delete
   */
  const confirmDelete = async (reportId: string) => {
    try {
      await deleteReport(reportId);
      setDeleteConfirm(null);
      await fetchReports();
    } catch {
      // Error already in store
    }
  };

  /**
   * Format timestamp for display (abbreviated)
   */
  const formatLastRunDisplay = (timestamp: string | null) => {
    if (!timestamp) {
      return 'Never run';
    }
    try {
      const date = new Date(timestamp);
      return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' });
    } catch {
      return 'Never run';
    }
  };

  /**
   * Format timestamp for tooltip (full datetime)
   */
  const formatLastRunFull = (timestamp: string | null) => {
    if (!timestamp) {
      return 'Never run';
    }
    try {
      const date = new Date(timestamp);
      return date.toLocaleString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        timeZoneName: 'short',
      });
    } catch {
      return 'Never run';
    }
  };

  /**
   * Get status badge styling
   */
  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'active':
        return 'bg-green-100 text-green-800 border border-green-300';
      case 'paused':
        return 'bg-yellow-100 text-yellow-800 border border-yellow-300';
      case 'failed':
        return 'bg-red-100 text-red-800 border border-red-300';
      default:
        return 'bg-gray-100 text-gray-800 border border-gray-300';
    }
  };

  /**
   * Render loading state with skeleton shimmer
   */
  if (loading && reports.length === 0) {
    return (
      <div className="min-h-screen bg-bg-primary">
        <nav className="border-b border-border-default bg-bg-secondary px-6 py-3">
          <Link to="/" className="text-sm text-accent-primary hover:underline font-medium">
            ← Back to Chat
          </Link>
        </nav>
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex justify-between items-center mb-8">
            <h1 className="text-3xl font-bold text-text-primary">Scheduled Reports</h1>
            <button
              type="button"
              onClick={handleCreateNew}
              disabled
              className="px-4 py-2 bg-accent-primary text-white rounded-lg font-medium opacity-50 cursor-not-allowed"
            >
              Create New Scheduled Report
            </button>
          </div>

          {/* Loading skeleton */}
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="h-16 bg-gradient-to-r from-bg-input via-bg-secondary to-bg-input rounded-lg animate-pulse"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  /**
   * Render error state
   */
  if (error && reports.length === 0) {
    return (
      <div className="min-h-screen bg-bg-primary">
        <nav className="border-b border-border-default bg-bg-secondary px-6 py-3">
          <Link to="/" className="text-sm text-accent-primary hover:underline font-medium">
            ← Back to Chat
          </Link>
        </nav>
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex justify-between items-center mb-8">
            <h1 className="text-3xl font-bold text-text-primary">Scheduled Reports</h1>
            <button
              type="button"
              onClick={handleCreateNew}
              className="px-4 py-2 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
            >
              Create New Scheduled Report
            </button>
          </div>

          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-sm font-semibold text-red-800">Error loading reports</h3>
                <p className="text-sm text-red-700 mt-1">{error}</p>
                <p className="text-xs text-red-600 mt-2">
                  Make sure the Scheduling API is running on port 8005.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  clearError();
                  fetchReports();
                }}
                className="text-sm text-red-700 hover:text-red-900 font-medium"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  /**
   * Render empty state
   */
  if (reports.length === 0) {
    return (
      <div className="min-h-screen bg-bg-primary">
        <nav className="border-b border-border-default bg-bg-secondary px-6 py-3">
          <Link to="/" className="text-sm text-accent-primary hover:underline font-medium">
            ← Back to Chat
          </Link>
        </nav>
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex justify-between items-center mb-8">
            <h1 className="text-3xl font-bold text-text-primary">Scheduled Reports</h1>
            <button
              type="button"
              onClick={handleCreateNew}
              className="px-4 py-2 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
            >
              Create New Scheduled Report
            </button>
          </div>

          <div className="text-center py-12">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-16 w-16 text-text-muted mx-auto mb-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <h3 className="text-lg font-medium text-text-secondary mb-1">No scheduled reports yet</h3>
            <p className="text-text-muted mb-2">Create your first scheduled report to automate recurring queries</p>
            <p className="text-xs text-text-muted mb-6">
              Tip: Pin a visualization card in the chat, then use the clock icon or three-dot menu to schedule it.
            </p>
            <button
              type="button"
              onClick={handleCreateNew}
              className="px-4 py-2 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
            >
              Create New Scheduled Report
            </button>
          </div>
        </div>
      </div>
    );
  }

  /**
   * Render list of reports
   */
  return (
    <div className="min-h-screen bg-bg-primary">
      <nav className="border-b border-border-default bg-bg-secondary px-6 py-3">
        <Link to="/" className="text-sm text-accent-primary hover:underline font-medium">
          ← Back to Chat
        </Link>
      </nav>
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-3xl font-bold text-text-primary">Scheduled Reports</h1>
          <button
            type="button"
            onClick={handleCreateNew}
            className="px-4 py-2 bg-accent-primary text-white rounded-lg font-medium hover:bg-accent-primary/90 transition-colors"
          >
            Create New Scheduled Report
          </button>
        </div>

      {/* Error banner */}
      {error && (
        <div className="mb-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div className="flex items-start justify-between">
            <div>
              <h3 className="text-sm font-semibold text-yellow-800">Warning</h3>
              <p className="text-sm text-yellow-700 mt-1">{error}</p>
            </div>
            <button
              type="button"
              onClick={clearError}
              className="text-sm text-yellow-700 hover:text-yellow-900 font-medium"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Reports Table */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-border-default">
              <th className="text-left px-4 py-3 text-sm font-semibold text-text-secondary">Title</th>
              <th className="text-left px-4 py-3 text-sm font-semibold text-text-secondary">Recurrence</th>
              <th className="text-left px-4 py-3 text-sm font-semibold text-text-secondary">Next Execution</th>
              <th className="text-left px-4 py-3 text-sm font-semibold text-text-secondary">Last Run</th>
              <th className="text-left px-4 py-3 text-sm font-semibold text-text-secondary">Status</th>
              <th className="text-right px-4 py-3 text-sm font-semibold text-text-secondary">Actions</th>
            </tr>
          </thead>
          <tbody>
            {reports.map((report: ScheduledReportListItem) => (
              <tr
                key={report.report_id}
                onClick={() => handleRowClick(report.report_id)}
                className="border-b border-border-default hover:bg-bg-input transition-colors cursor-pointer"
              >
                {/* Title */}
                <td className="px-4 py-4">
                  <p className="text-sm font-medium text-accent-primary hover:underline">{report.title}</p>
                </td>

                {/* Recurrence Display */}
                <td className="px-4 py-4">
                  <p className="text-sm text-text-secondary">{report.recurrence_display}</p>
                </td>

                {/* Next Execution */}
                <td className="px-4 py-4">
                  <p className="text-sm text-text-secondary">
                    {report.next_execution_time
                      ? new Date(report.next_execution_time).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                          hour: '2-digit',
                          minute: '2-digit',
                        })
                      : '—'}
                  </p>
                </td>

                {/* Last Run with Info Tooltip */}
                <td className="px-4 py-4">
                  <div className="flex items-center gap-2 group">
                    <p className="text-sm text-text-secondary">{formatLastRunDisplay(report.last_run_timestamp)}</p>
                    {report.last_run_timestamp && (
                      <div className="relative">
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          className="h-4 w-4 text-text-muted hover:text-text-secondary cursor-help"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 hidden group-hover:block bg-bg-secondary text-text-secondary text-xs px-2 py-1 rounded border border-border-default whitespace-nowrap z-10">
                          {formatLastRunFull(report.last_run_timestamp)}
                        </div>
                      </div>
                    )}
                  </div>
                </td>

                {/* Status Badge */}
                <td className="px-4 py-4">
                  <span
                    className={`inline-block px-3 py-1 text-xs font-semibold rounded-full ${getStatusBadgeClass(report.status)}`}
                  >
                    {report.status.charAt(0).toUpperCase() + report.status.slice(1)}
                  </span>
                </td>

                {/* Action Buttons */}
                <td className="px-4 py-4 text-right">
                  <div className="flex gap-2 justify-end">
                    {/* Pause/Resume Button */}
                    <button
                      type="button"
                      onClick={(e) => handleTogglePause(e, report.report_id, report.status === 'active')}
                      className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                        report.status === 'active'
                          ? 'bg-yellow-100 text-yellow-900 hover:bg-yellow-200'
                          : 'bg-green-100 text-green-900 hover:bg-green-200'
                      }`}
                      title={report.status === 'active' ? 'Pause report' : 'Resume report'}
                    >
                      {report.status === 'active' ? 'Pause' : 'Resume'}
                    </button>

                    {/* Delete Button */}
                    <button
                      type="button"
                      onClick={(e) => handleDelete(e, report.report_id)}
                      className="px-3 py-1 text-xs font-medium bg-red-100 text-red-900 hover:bg-red-200 rounded transition-colors"
                      title="Delete report"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-bg-secondary border border-border-default rounded-lg p-6 max-w-sm">
            <h3 className="text-lg font-semibold text-text-primary mb-2">Delete Report?</h3>
            <p className="text-sm text-text-secondary mb-6">
              Are you sure you want to delete <span className="font-medium">"{reports.find(r => r.report_id === deleteConfirm)?.title}"</span>? This action cannot be undone, though execution history will be preserved.
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setDeleteConfirm(null)}
                className="flex-1 px-4 py-2 border border-border-default rounded-lg text-sm font-medium hover:bg-bg-input transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => confirmDelete(deleteConfirm)}
                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Loading indicator at bottom */}
      {loading && (
        <div className="mt-8 text-center">
          <div className="inline-flex items-center gap-2 text-text-secondary">
            <div className="h-4 w-4 border-2 border-accent-primary border-t-transparent rounded-full animate-spin" />
            <span className="text-sm">Loading...</span>
          </div>
        </div>
      )}
      </div>
    </div>
  );
}
