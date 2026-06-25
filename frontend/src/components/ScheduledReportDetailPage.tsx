/**
 * ScheduledReportDetailPage component.
 *
 * Redesigned detail view for a scheduled report.
 *
 * Layout:
 * - Center (main content): the latest execution version of the scheduled chat
 *   session — status, timing, and rendered output of the most recent run.
 * - Right sidebar (collapsible): Settings (title, description, recurrence) and
 *   execution History, each in its own collapsible panel.
 *
 * Modes:
 * - Create mode  (route: /scheduled-reports/new) — shows a creation form.
 * - Detail mode  (route: /scheduled-reports/:reportId) — shows the redesigned
 *   detail/edit layout described above.
 *
 * Routes: /scheduled-reports/new, /scheduled-reports/:reportId
 */

import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useScheduledReportsStore } from '../store/scheduledReportsStore';
import { useSessionStore } from '../store/sessionStore';
import { RecurrencePatternSelector } from './RecurrencePatternSelector';
import type { CardState, RenderedOutput } from '../types';
import { VisualizationCard } from './VisualizationCard';
import { addPrompt, deletePrompt } from '../api/scheduledReportsApi';
import type {
  ExecutionHistoryItem,
  RecurrencePattern,
} from '../types/scheduledReports';

const DEFAULT_RECURRENCE: RecurrencePattern = {
  type: 'daily',
  time_hour: 9,
  time_minute: 0,
  timezone: 'Asia/Kolkata',
};

/** Format an ISO timestamp into a readable local datetime. */
function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

/** Format a latency in ms into a compact human string. */
function formatLatency(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/** Styling for an execution status badge. */
function executionStatusClass(status: string): string {
  switch (status) {
    case 'success':
      return 'bg-green-100 text-green-800 border border-green-300';
    case 'failed':
      return 'bg-red-100 text-red-800 border border-red-300';
    case 'retrying':
      return 'bg-yellow-100 text-yellow-800 border border-yellow-300';
    default:
      return 'bg-gray-100 text-gray-800 border border-gray-300';
  }
}

export function ScheduledReportDetailPage() {
  const navigate = useNavigate();
  const { reportId } = useParams<{ reportId: string }>();
  const [searchParams] = useSearchParams();
  const isCreateMode = !reportId;

  // Access chat cards so we can attach the real StructuredIntent captured
  // when each visualization's query ran.
  const cards = useSessionStore((s) => s.cards);

  const {
    currentReport,
    executionHistory,
    totalExecutions,
    currentPage,
    pageSize,
    loading,
    error,
    fetchReportDetail,
    fetchExecutionHistory,
    createReport,
    updateReport,
    deleteReport,
    pauseReport,
    resumeReport,
    retryReport,
    setCurrentPage,
    clearError,
    clearCurrentReport,
  } = useScheduledReportsStore();

  // ----- Local editable form state -----
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [recurrence, setRecurrence] = useState<RecurrencePattern>(DEFAULT_RECURRENCE);

  // ----- UI state -----
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [promptInput, setPromptInput] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [promptError, setPromptError] = useState<string | null>(null);

  // Load report detail + execution history in detail mode.
  useEffect(() => {
    if (reportId) {
      fetchReportDetail(reportId);
      fetchExecutionHistory(reportId, 1);
    }
    return () => {
      clearCurrentReport();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reportId]);

  // Sync local form state when the loaded report changes.
  useEffect(() => {
    if (currentReport) {
      setTitle(currentReport.title);
      setDescription(currentReport.description ?? '');
      setRecurrence(currentReport.recurrence_pattern ?? DEFAULT_RECURRENCE);
    }
  }, [currentReport]);

  // The latest execution version of the scheduled chat session.
  const latestExecution: ExecutionHistoryItem | null = useMemo(() => {
    if (executionHistory.length === 0) return null;
    return [...executionHistory].sort(
      (a, b) =>
        new Date(b.execution_timestamp).getTime() -
        new Date(a.execution_timestamp).getTime(),
    )[0];
  }, [executionHistory]);

  const totalPages = useMemo(() => {
    const size = pageSize ?? 10;
    const total = totalExecutions ?? 0;
    return Math.max(1, Math.ceil(total / size));
  }, [totalExecutions, pageSize]);

  // ----- Handlers -----
  // Resolve scheduling context (chat + visualizations) from query params.
  const vizIds: string[] = (() => {
    const vizIdParam = searchParams.get('viz_id');
    const vizIdsParam = searchParams.get('viz_ids');
    if (vizIdParam) return [vizIdParam];
    if (vizIdsParam) return vizIdsParam.split(',').filter((id) => id.trim());
    return [];
  })();
  const hasSchedulingContext = vizIds.length > 0;

  const handleCreate = async () => {
    if (!title.trim()) return;

    if (!hasSchedulingContext) {
      console.warn('Create report: no visualization context. Start from a pinned card.');
      return;
    }

    const chatId = searchParams.get('chat_id') || 'current-session';

    console.log('Creating report with', { title, vizIds, chatId });

    // Gather the real StructuredIntent for each pinned viz from the session store.
    // This is the intent captured when the query originally ran.
    const structured_intents: Record<string, Record<string, unknown>> = {};
    const query_texts: Record<string, string> = {};
    for (const vid of vizIds) {
      const card = cards[vid];
      const intent = card?.transparencyData?.structuredIntent;
      if (intent) {
        structured_intents[vid] = intent as unknown as Record<string, unknown>;
      }
      if (card?.query) {
        query_texts[vid] = card.query;
      }
    }

    const newId = await createReport({
      title: title.trim(),
      description: description.trim(),
      original_chat_id: chatId,
      pinned_visualization_ids: vizIds,
      recurrence_pattern: recurrence,
      structured_intents: Object.keys(structured_intents).length
        ? structured_intents
        : undefined,
      query_texts: Object.keys(query_texts).length
        ? query_texts
        : undefined,
    });
    if (newId) {
      navigate(`/scheduled-reports/${newId}`);
    }
  };

  const handleSaveSettings = async () => {
    if (!reportId) return;
    await updateReport(reportId, {
      title: title.trim(),
      description: description.trim(),
      recurrence_pattern: recurrence,
    });
  };

  const handleTogglePause = async () => {
    if (!reportId || !currentReport) return;
    if (currentReport.is_active) {
      await pauseReport(reportId);
    } else {
      await resumeReport(reportId);
    }
  };

  const handleRetry = async () => {
    if (!reportId) return;
    await retryReport(reportId);
  };

  const handleConfirmDelete = async () => {
    if (!reportId) return;
    await deleteReport(reportId);
    setDeleteConfirm(false);
    navigate('/scheduled-reports');
  };

  const handlePageChange = (page: number) => {
    if (page < 1 || page > totalPages) return;
    setCurrentPage(page);
  };

  const handleAddPrompt = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reportId || !promptInput.trim() || promptLoading) return;

    setPromptLoading(true);
    setPromptError(null);
    try {
      // Backend runs only this new query and merges it into the latest execution.
      await addPrompt(reportId, promptInput.trim());
      setPromptInput('');
      await fetchReportDetail(reportId);
      await fetchExecutionHistory(reportId, 1);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to add prompt';
      setPromptError(msg);
    } finally {
      setPromptLoading(false);
    }
  };

  const handleDeletePrompt = async (vizId: string) => {
    if (!reportId) return;
    try {
      // Backend removes this viz from the latest execution (no full re-run).
      await deletePrompt(reportId, vizId);
      await fetchReportDetail(reportId);
      await fetchExecutionHistory(reportId, 1);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to delete prompt';
      setPromptError(msg);
    }
  };

  // -------------------------------------------------------------------------
  // CREATE MODE
  // -------------------------------------------------------------------------
  if (isCreateMode) {
    return (
      <div className="min-h-screen bg-bg-primary">
        <nav className="border-b border-border-default bg-bg-secondary px-6 py-3">
          <Link to="/scheduled-reports" className="text-sm text-accent-primary hover:underline font-medium">
            ← Back to Scheduled Reports
          </Link>
        </nav>

        <div className="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <h1 className="text-3xl font-bold text-text-primary mb-8">Create Scheduled Report</h1>

          {error && (
            <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {!hasSchedulingContext && (
            <div className="mb-6 bg-yellow-50 border border-yellow-200 rounded-lg p-4">
              <p className="text-sm text-yellow-800 font-medium">No visualization selected</p>
              <p className="text-sm text-yellow-700 mt-1">
                Scheduled reports run a pinned visualization. Open a chat, pin a
                visualization card, then click the clock icon on that card to schedule it.
              </p>
            </div>
          )}

          <div className="space-y-6">
            <div>
              <label htmlFor="report-title" className="block text-sm font-medium text-text-primary mb-2">
                Title
              </label>
              <input
                id="report-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Weekly Sales Report"
                className="w-full px-3 py-2 border border-border-default rounded-lg bg-bg-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
              />
            </div>

            <div>
              <label htmlFor="report-description" className="block text-sm font-medium text-text-primary mb-2">
                Description
              </label>
              <textarea
                id="report-description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                placeholder="Optional description of what this report covers"
                className="w-full px-3 py-2 border border-border-default rounded-lg bg-bg-secondary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
              />
            </div>

            <RecurrencePatternSelector value={recurrence} onChange={setRecurrence} />

            <div className="flex gap-3 pt-4">
              <button
                type="button"
                onClick={() => navigate('/scheduled-reports')}
                className="flex-1 px-4 py-2 border border-border-default rounded-lg text-sm font-medium hover:bg-bg-input transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreate}
                disabled={!title.trim() || loading || !hasSchedulingContext}
                className="flex-1 px-4 py-2 bg-accent-primary text-white rounded-lg text-sm font-medium hover:bg-accent-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Creating…' : 'Create Report'}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // DETAIL MODE — loading / not-found guards
  // -------------------------------------------------------------------------
  if (loading && !currentReport) {
    return (
      <div className="min-h-screen bg-bg-primary">
        <nav className="border-b border-border-default bg-bg-secondary px-6 py-3">
          <Link to="/scheduled-reports" className="text-sm text-accent-primary hover:underline font-medium">
            ← Back to Scheduled Reports
          </Link>
        </nav>
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="h-10 w-1/3 bg-bg-input rounded animate-pulse mb-6" />
          <div className="h-72 bg-bg-input rounded-lg animate-pulse" />
        </div>
      </div>
    );
  }

  if (!currentReport) {
    return (
      <div className="min-h-screen bg-bg-primary">
        <nav className="border-b border-border-default bg-bg-secondary px-6 py-3">
          <Link to="/scheduled-reports" className="text-sm text-accent-primary hover:underline font-medium">
            ← Back to Scheduled Reports
          </Link>
        </nav>
        <div className="max-w-6xl mx-auto px-6 py-8">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <h3 className="text-sm font-semibold text-red-800">Report not found</h3>
            <p className="text-sm text-red-700 mt-1">{error ?? 'This scheduled report could not be loaded.'}</p>
            <button
              type="button"
              onClick={() => {
                clearError();
                if (reportId) fetchReportDetail(reportId);
              }}
              className="mt-3 text-sm text-red-700 hover:text-red-900 font-medium"
            >
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // -------------------------------------------------------------------------
  // DETAIL MODE — redesigned layout
  // -------------------------------------------------------------------------
  const statusLabel = currentReport.is_active ? 'Active' : 'Paused';
  const statusBadgeClass = currentReport.is_active
    ? 'bg-green-100 text-green-800 border border-green-300'
    : 'bg-yellow-100 text-yellow-800 border border-yellow-300';

  return (
    <div className="min-h-screen bg-bg-primary flex flex-col">
      {/* Top nav */}
      <nav className="border-b border-border-default bg-bg-secondary px-6 py-3 flex items-center justify-between">
        <Link to="/scheduled-reports" className="text-sm text-accent-primary hover:underline font-medium">
          ← Back to Scheduled Reports
        </Link>
        <button
          type="button"
          onClick={() => setSidebarOpen((v) => !v)}
          className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-text-secondary hover:bg-bg-input rounded-lg transition-colors"
          aria-expanded={sidebarOpen}
          title={sidebarOpen ? 'Hide settings & history' : 'Show settings & history'}
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h7" />
          </svg>
          {sidebarOpen ? 'Hide panel' : 'Settings & History'}
        </button>
      </nav>

      {/* Non-blocking error / warning banner (e.g. EventBridge IAM degradation) */}
      {error && (
        <div className="bg-yellow-50 border-b border-yellow-200 px-6 py-3">
          <div className="max-w-7xl mx-auto flex items-start justify-between gap-4">
            <p className="text-sm text-yellow-800">{error}</p>
            <button type="button" onClick={clearError} className="text-sm text-yellow-700 hover:text-yellow-900 font-medium flex-shrink-0">
              Dismiss
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* ============================ CENTER ============================ */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="max-w-3xl mx-auto">
            {/* Header */}
            <div className="flex items-start justify-between gap-4 mb-6">
              <div className="min-w-0">
                <h1 className="text-2xl font-bold text-text-primary truncate">{currentReport.title}</h1>
                {currentReport.description && (
                  <p className="text-sm text-text-secondary mt-1">{currentReport.description}</p>
                )}
              </div>
              <span className={`flex-shrink-0 inline-block px-3 py-1 text-xs font-semibold rounded-full ${statusBadgeClass}`}>
                {statusLabel}
              </span>
            </div>

            {/* Action bar */}
            <div className="flex flex-wrap gap-2 mb-6">
              <button
                type="button"
                onClick={handleRetry}
                disabled={loading}
                className="px-3 py-1.5 text-sm font-medium bg-accent-primary text-white rounded-lg hover:bg-accent-primary/90 transition-colors disabled:opacity-50"
              >
                Run Now
              </button>
              <button
                type="button"
                onClick={handleTogglePause}
                disabled={loading}
                className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
                  currentReport.is_active
                    ? 'bg-yellow-100 text-yellow-900 hover:bg-yellow-200'
                    : 'bg-green-100 text-green-900 hover:bg-green-200'
                }`}
              >
                {currentReport.is_active ? 'Pause' : 'Resume'}
              </button>
              <button
                type="button"
                onClick={() => setDeleteConfirm(true)}
                className="px-3 py-1.5 text-sm font-medium bg-red-100 text-red-900 hover:bg-red-200 rounded-lg transition-colors"
              >
                Delete
              </button>
            </div>

            {/* Latest execution version of the scheduled chat session */}
            <section aria-label="Latest execution" className="rounded-lg border border-border-default bg-bg-secondary shadow-card">
              <header className="flex items-center justify-between px-5 py-3 border-b border-border-default">
                <h2 className="text-sm font-semibold text-text-primary">Latest Execution</h2>
                {latestExecution && (
                  <span className={`inline-block px-2.5 py-0.5 text-xs font-semibold rounded-full ${executionStatusClass(latestExecution.status)}`}>
                    {latestExecution.status.charAt(0).toUpperCase() + latestExecution.status.slice(1)}
                  </span>
                )}
              </header>

              <div className="p-5">
                {latestExecution ? (
                  <div className="space-y-5">
                    {/* Execution metadata */}
                    <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                      <div>
                        <dt className="text-xs text-text-muted">Executed</dt>
                        <dd className="text-sm text-text-primary mt-0.5">{formatDateTime(latestExecution.execution_timestamp)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-text-muted">Latency</dt>
                        <dd className="text-sm text-text-primary mt-0.5">{formatLatency(latestExecution.query_latency_ms)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-text-muted">Retries</dt>
                        <dd className="text-sm text-text-primary mt-0.5">{latestExecution.retry_count}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-text-muted">Completed</dt>
                        <dd className="text-sm text-text-primary mt-0.5">{formatDateTime(latestExecution.actual_end_timestamp)}</dd>
                      </div>
                    </dl>

                    {/* Rendered output / error */}
                    {latestExecution.status === 'failed' ? (
                      <div className="rounded border border-status-error/30 bg-red-50 p-4">
                        <h3 className="text-sm font-semibold text-status-error mb-1">Execution failed</h3>
                        <p className="text-sm text-red-700">
                          {latestExecution.error_message ?? 'No error details were provided.'}
                        </p>
                      </div>
                    ) : latestExecution.rendered_output ? (
                      <div className="flex flex-col gap-4">
                        {(Array.isArray(latestExecution.rendered_output)
                          ? latestExecution.rendered_output
                          : [latestExecution.rendered_output]
                        ).map((output, idx) => {
                          // Tagged shape: {viz_id, query_text, rendered_output}
                          // Legacy shape: a bare RenderedOutput (or {rendered_output:{...}})
                          const tagged = output as {
                            viz_id?: string;
                            query_text?: string;
                            rendered_output?: Record<string, unknown>;
                          };
                          const ro = (tagged.rendered_output ?? output) as Record<string, unknown>;
                          const renderedOutput = ro as unknown as RenderedOutput;

                          // Prefer the viz_id embedded in the output; fall back to index.
                          const vizId =
                            tagged.viz_id ??
                            currentReport.pinned_visualization_ids[idx] ??
                            null;
                          const queryText =
                            tagged.query_text ??
                            (vizId && currentReport.query_texts
                              ? currentReport.query_texts[vizId] ?? ''
                              : '');

                          // Build a CardState-like object so VisualizationCard renders identically to chat
                          const cardState: CardState = {
                            id: `exec-${latestExecution.execution_id}-${vizId ?? idx}`,
                            query: queryText || ((ro as { description?: string }).description ?? ''),
                            renderedOutput,
                            transparencyData: {
                              queryRewrite: null,
                              structuredIntent: null,
                              apiCallSummary: null,
                            },
                            pinned: true,
                            width: '100%' as const,
                            createdAt: new Date(latestExecution.execution_timestamp).getTime(),
                          };

                          return (
                            <div key={vizId ?? idx} className="w-full relative group/card">
                              {vizId && (
                                <button
                                  type="button"
                                  onClick={() => handleDeletePrompt(vizId)}
                                  className="absolute top-2 right-2 z-10 opacity-0 group-hover/card:opacity-100 transition-opacity p-1.5 rounded-lg bg-bg-secondary/90 border border-border-default hover:bg-red-50 hover:border-red-300 text-text-muted hover:text-red-600"
                                  title="Remove this prompt"
                                  aria-label="Remove this prompt from the report"
                                >
                                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                  </svg>
                                </button>
                              )}
                              <VisualizationCard card={cardState} />
                            </div>
                          );
                        })}
                      </div>
                    ) : (
                      <p className="text-sm text-text-muted italic">
                        This execution completed but produced no stored output.
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-10">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 text-text-muted mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <h3 className="text-sm font-medium text-text-secondary">Never run</h3>
                    <p className="text-xs text-text-muted mt-1">
                      This report has not executed yet. The next run is scheduled for{' '}
                      {formatDateTime(currentReport.next_execution_time)}.
                    </p>
                    <button
                      type="button"
                      onClick={handleRetry}
                      disabled={loading}
                      className="mt-4 px-4 py-2 text-sm font-medium bg-accent-primary text-white rounded-lg hover:bg-accent-primary/90 transition-colors disabled:opacity-50"
                    >
                      Run Now
                    </button>
                  </div>
                )}
              </div>
            </section>

            {/* Schedule summary */}
            <div className="mt-4 grid grid-cols-2 gap-4">
              <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
                <p className="text-xs text-text-muted">Next execution</p>
                <p className="text-sm text-text-primary mt-1">{formatDateTime(currentReport.next_execution_time)}</p>
              </div>
              <div className="rounded-lg border border-border-default bg-bg-secondary p-4">
                <p className="text-xs text-text-muted">Last run</p>
                <p className="text-sm text-text-primary mt-1">{formatDateTime(currentReport.last_run_timestamp)}</p>
              </div>
            </div>
          </div>

          {/* Chat input bar — sticky at bottom of scroll area */}
          <div className="sticky bottom-0 pt-4 pb-2 max-w-3xl mx-auto w-full">
            {promptError && (
              <div className="mb-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-center justify-between">
                <p className="text-xs text-red-700">{promptError}</p>
                <button type="button" onClick={() => setPromptError(null)} className="text-xs text-red-500 hover:text-red-700 ml-2">✕</button>
              </div>
            )}
            <form
              onSubmit={handleAddPrompt}
              className="flex items-center gap-2 rounded-xl border border-border-default bg-bg-secondary/95 px-3 py-2 shadow-sm backdrop-blur-sm"
            >
              <input
                type="text"
                value={promptInput}
                onChange={(e) => setPromptInput(e.target.value)}
                placeholder="Ask a question about your data..."
                disabled={promptLoading}
                className="flex-1 bg-transparent text-sm text-text-primary placeholder-text-muted outline-none disabled:opacity-50"
                aria-label="Add a new prompt to this report"
              />
              <button
                type="submit"
                disabled={!promptInput.trim() || promptLoading}
                className="flex-shrink-0 p-1.5 rounded-lg text-accent-primary hover:bg-accent-subtle disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                aria-label="Submit prompt"
              >
                {promptLoading ? (
                  <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 19V5m0 0l-7 7m7-7l7 7" />
                  </svg>
                )}
              </button>
            </form>
          </div>
        </main>

        {/* ========================= RIGHT SIDEBAR ========================= */}
        {sidebarOpen && (
          <aside className="w-full max-w-sm flex-shrink-0 border-l border-border-default bg-bg-secondary overflow-y-auto">
            {/* Settings panel */}
            <section className="border-b border-border-default">
              <button
                type="button"
                onClick={() => setSettingsOpen((v) => !v)}
                className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-bg-input transition-colors"
                aria-expanded={settingsOpen}
              >
                <span className="text-sm font-semibold text-text-primary">Settings</span>
                <Chevron expanded={settingsOpen} />
              </button>

              {settingsOpen && (
                <div className="px-5 pb-5 space-y-4">
                  <div>
                    <label htmlFor="settings-title" className="block text-xs font-medium text-text-secondary mb-1">
                      Title
                    </label>
                    <input
                      id="settings-title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-3 py-2 text-sm border border-border-default rounded-lg bg-bg-primary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
                    />
                  </div>

                  <div>
                    <label htmlFor="settings-description" className="block text-xs font-medium text-text-secondary mb-1">
                      Description
                    </label>
                    <textarea
                      id="settings-description"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={2}
                      className="w-full px-3 py-2 text-sm border border-border-default rounded-lg bg-bg-primary text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary"
                    />
                  </div>

                  <RecurrencePatternSelector value={recurrence} onChange={setRecurrence} />

                  <button
                    type="button"
                    onClick={handleSaveSettings}
                    disabled={loading || !title.trim()}
                    className="w-full px-4 py-2 text-sm font-medium bg-accent-primary text-white rounded-lg hover:bg-accent-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loading ? 'Saving…' : 'Save Settings'}
                  </button>
                </div>
              )}
            </section>

            {/* History panel */}
            <section>
              <button
                type="button"
                onClick={() => setHistoryOpen((v) => !v)}
                className="w-full flex items-center justify-between px-5 py-3 text-left hover:bg-bg-input transition-colors"
                aria-expanded={historyOpen}
              >
                <span className="text-sm font-semibold text-text-primary">
                  Execution History
                  {typeof totalExecutions === 'number' && totalExecutions > 0 && (
                    <span className="ml-2 text-xs font-normal text-text-muted">({totalExecutions})</span>
                  )}
                </span>
                <Chevron expanded={historyOpen} />
              </button>

              {historyOpen && (
                <div className="px-5 pb-5">
                  {executionHistory.length === 0 ? (
                    <p className="text-sm text-text-muted py-4">No executions yet.</p>
                  ) : (
                    <ul className="space-y-2">
                      {executionHistory.map((exec) => {
                        const isLatest = latestExecution?.execution_id === exec.execution_id;
                        return (
                          <li
                            key={exec.execution_id}
                            className={`rounded-lg border p-3 ${
                              isLatest ? 'border-accent-primary/40 bg-accent-subtle' : 'border-border-default bg-bg-primary'
                            }`}
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs text-text-secondary">{formatDateTime(exec.execution_timestamp)}</span>
                              <span className={`inline-block px-2 py-0.5 text-[10px] font-semibold rounded-full ${executionStatusClass(exec.status)}`}>
                                {exec.status}
                              </span>
                            </div>
                            <div className="flex items-center justify-between mt-1.5">
                              <span className="text-[11px] text-text-muted">{formatLatency(exec.query_latency_ms)}</span>
                              {isLatest && (
                                <span className="text-[10px] font-medium text-accent-primary">Latest</span>
                              )}
                            </div>
                            {exec.status === 'failed' && exec.error_message && (
                              <p className="text-[11px] text-red-700 mt-1.5 line-clamp-2">{exec.error_message}</p>
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  )}

                  {/* Pagination */}
                  {totalPages > 1 && (
                    <div className="flex items-center justify-between mt-4">
                      <button
                        type="button"
                        onClick={() => handlePageChange(currentPage - 1)}
                        disabled={currentPage <= 1 || loading}
                        className="px-2 py-1 text-xs font-medium text-text-secondary hover:bg-bg-input rounded disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        ← Prev
                      </button>
                      <span className="text-xs text-text-muted">
                        Page {currentPage} of {totalPages}
                      </span>
                      <button
                        type="button"
                        onClick={() => handlePageChange(currentPage + 1)}
                        disabled={currentPage >= totalPages || loading}
                        className="px-2 py-1 text-xs font-medium text-text-secondary hover:bg-bg-input rounded disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        Next →
                      </button>
                    </div>
                  )}
                </div>
              )}
            </section>
          </aside>
        )}
      </div>

      {/* Delete confirmation modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-bg-secondary border border-border-default rounded-lg p-6 max-w-sm">
            <h3 className="text-lg font-semibold text-text-primary mb-2">Delete Report?</h3>
            <p className="text-sm text-text-secondary mb-6">
              Are you sure you want to delete <span className="font-medium">"{currentReport.title}"</span>? This action
              cannot be undone, though execution history will be preserved.
            </p>
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setDeleteConfirm(false)}
                className="flex-1 px-4 py-2 border border-border-default rounded-lg text-sm font-medium hover:bg-bg-input transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                className="flex-1 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** Chevron icon that rotates based on expanded state. */
function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`h-4 w-4 text-text-muted transition-transform ${expanded ? 'rotate-90' : ''}`}
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M6 5L10 9L6 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
