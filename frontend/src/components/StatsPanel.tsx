/**
 * StatsPanel component.
 *
 * Collapsible right rail displaying per-column statistical metadata
 * for the active VisualizationCard. Reads metadata.columns from the
 * active card's renderedOutput when a card is clicked.
 *
 * Displays:
 * - Latency badge (↯ {N}ms) from metadata.latency_ms
 * - Per-column: row_count + null_percentage (1 decimal)
 * - Numeric columns: min, max, mean, median, std_dev (2 decimals)
 * - Categorical columns: cardinality
 * - Time-series columns: time_range_start, time_range_end (ISO 8601)
 *
 * Empty state when no card is active or no columns available.
 * Connected to zustand store for activeCardId and statsPanelCollapsed.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
 */

import { useSessionStore } from '../store/sessionStore';
import { formatLatency } from '../utils/formatters';
import type { ColumnMeta } from '../types';

// ---------------------------------------------------------------------------
// Main StatsPanel component
// ---------------------------------------------------------------------------

export function StatsPanel() {
  const activeCardId = useSessionStore((s) => s.activeCardId);
  const cards = useSessionStore((s) => s.cards);
  const statsPanelCollapsed = useSessionStore((s) => s.statsPanelCollapsed);
  const toggleStatsPanel = useSessionStore((s) => s.toggleStatsPanel);

  const activeCard = activeCardId ? cards[activeCardId] ?? null : null;
  const metadata = activeCard?.renderedOutput?.metadata ?? null;
  const columns = metadata?.columns ?? [];

  if (statsPanelCollapsed) {
    return (
      <aside
        className="flex h-full w-10 min-w-[40px] flex-col items-center border-l border-border-default bg-bg-secondary pt-3"
        aria-label="Stats panel collapsed"
      >
        <button
          type="button"
          onClick={toggleStatsPanel}
          className="rounded p-1 text-text-muted hover:text-text-secondary hover:bg-accent-subtle transition-colors"
          aria-label="Expand stats panel"
          title="Expand stats panel"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
            />
          </svg>
        </button>
      </aside>
    );
  }

  return (
    <aside
      className="flex h-full w-[280px] min-w-[280px] flex-col border-l border-border-default bg-bg-secondary shadow-panel"
      aria-label="Stats panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
        <h2 className="text-sm font-semibold text-text-primary">Statistics</h2>
        <button
          type="button"
          onClick={toggleStatsPanel}
          className="rounded p-1 text-text-muted hover:text-text-secondary hover:bg-accent-subtle transition-colors"
          aria-label="Collapse stats panel"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Content */}
      {!activeCard ? (
        /* Empty state: no card selected */
        <div className="flex flex-1 items-center justify-center p-4">
          <div className="text-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="mx-auto h-10 w-10 text-text-muted mb-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z"
              />
            </svg>
            <p className="text-sm text-text-muted">
              Select a card to view statistics
            </p>
          </div>
        </div>
      ) : columns.length === 0 ? (
        /* Empty state: no columns */
        <div className="flex flex-1 items-center justify-center p-4">
          <div className="text-center">
            <p className="text-sm text-text-muted">
              No column statistics available
            </p>
          </div>
        </div>
      ) : (
        /* Active card with columns */
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Latency badge */}
          {metadata?.latency_ms != null && (
            <div className="flex items-center">
              <span className="inline-flex items-center rounded-full bg-accent-subtle px-2.5 py-0.5 text-xs font-medium text-accent-primary">
                {formatLatency(metadata.latency_ms)}
              </span>
            </div>
          )}

          {/* Column statistics */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Columns
            </h3>
            {columns.map((col) => (
              <ColumnStatsCard key={col.name} column={col} />
            ))}
          </div>
        </div>
      )}
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Column Stats Card
// ---------------------------------------------------------------------------

function ColumnStatsCard({ column }: { column: ColumnMeta }) {
  return (
    <div className="rounded-md border border-border-default bg-bg-primary p-3">
      {/* Column header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium text-text-primary truncate">
          {column.name}
        </span>
        <ColumnTypeBadge type={column.type} />
      </div>

      {/* Stats grid */}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        {/* Common stats: row_count and null_percentage for all column types */}
        {column.row_count != null && (
          <StatEntry label="Rows" value={column.row_count.toLocaleString()} />
        )}
        {column.null_percentage != null && (
          <StatEntry label="Null %" value={`${column.null_percentage.toFixed(1)}%`} />
        )}

        {/* Numeric-specific stats (2 decimal places) */}
        {column.type === 'numeric' && (
          <>
            {column.min != null && (
              <StatEntry label="Min" value={column.min.toFixed(2)} />
            )}
            {column.max != null && (
              <StatEntry label="Max" value={column.max.toFixed(2)} />
            )}
            {column.mean != null && (
              <StatEntry label="Mean" value={column.mean.toFixed(2)} />
            )}
            {column.median != null && (
              <StatEntry label="Median" value={column.median.toFixed(2)} />
            )}
            {column.std_dev != null && (
              <StatEntry label="Std Dev" value={column.std_dev.toFixed(2)} />
            )}
          </>
        )}

        {/* Categorical-specific stats */}
        {column.type === 'categorical' && column.cardinality != null && (
          <StatEntry label="Cardinality" value={column.cardinality.toLocaleString()} />
        )}

        {/* Time-series-specific stats (ISO 8601) */}
        {column.type === 'time-series' && (
          <>
            {column.time_range_start != null && (
              <StatEntry label="Start" value={column.time_range_start} />
            )}
            {column.time_range_end != null && (
              <StatEntry label="End" value={column.time_range_end} />
            )}
          </>
        )}
      </dl>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Column type badge
// ---------------------------------------------------------------------------

function ColumnTypeBadge({ type }: { type: ColumnMeta['type'] }) {
  const styles: Record<string, string> = {
    numeric: 'bg-accent-subtle text-accent-primary',
    categorical: 'bg-status-success/10 text-status-success',
    'time-series': 'bg-status-warning/10 text-status-warning',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium shrink-0 ml-2 ${styles[type]}`}
    >
      {type}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Stat entry (label + value pair)
// ---------------------------------------------------------------------------

function StatEntry({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="font-medium text-text-muted">{label}</dt>
      <dd className="text-text-secondary font-mono truncate" title={value}>
        {value}
      </dd>
    </>
  );
}
