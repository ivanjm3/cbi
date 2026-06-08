/**
 * StatsPanel component.
 * Displays per-column statistics for the active visualization card.
 * Includes latency badge, row count, and column-level stats by type.
 *
 * On desktop (≥1024px): Renders as a 300px collapsible right rail.
 * On narrow (<1024px): Renders as a collapsible accordion below the canvas.
 *   - Accordion header shows active card query title + latency badge.
 *   - Expanding reveals the same per-column stats content.
 *   - Default collapsed on narrow screens.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 1.5, 1.6
 */

import { useState } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { formatLatency } from '../utils/formatters';
import type { ColumnMeta } from '../types';

interface StatsPanelProps {
  collapsed: boolean;
  onToggle: () => void;
}

// ---------------------------------------------------------------------------
// Stats content — shared between desktop rail and mobile accordion
// ---------------------------------------------------------------------------

function StatsContent() {
  const activeCardId = useSessionStore((s) => s.activeCardId);
  const cards = useSessionStore((s) => s.cards);

  const activeCard = activeCardId
    ? cards.find((c) => c.id === activeCardId) ?? null
    : null;

  const metadata = activeCard?.renderedOutput?.metadata ?? null;
  const columns = metadata?.columns ?? [];

  if (!activeCard) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        No card selected
      </p>
    );
  }

  if (columns.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400">
        No column statistics available
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {/* Latency badge */}
      {metadata?.latency_ms != null && (
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded bg-blue-100 dark:bg-blue-900 px-2 py-0.5 text-xs font-medium text-blue-800 dark:text-blue-200">
            {formatLatency(metadata.latency_ms)}
          </span>
        </div>
      )}

      {/* Row count */}
      {metadata?.row_count != null && (
        <div className="text-sm text-gray-700 dark:text-gray-300">
          <span className="font-medium">Row count:</span>{' '}
          {metadata.row_count.toLocaleString()}
        </div>
      )}

      {/* Column statistics */}
      <div className="space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Column Statistics
        </h3>
        {columns.map((col) => (
          <ColumnStatsSection key={col.name} column={col} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Desktop Stats Panel (right rail)
// ---------------------------------------------------------------------------

export function StatsPanel({ collapsed, onToggle }: StatsPanelProps) {
  return (
    <aside
      className={`hidden lg:flex h-full border-l border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 flex-col transition-[width] duration-200 ease-in-out overflow-hidden ${
        collapsed ? 'w-0 min-w-0' : 'w-[300px] min-w-[300px]'
      }`}
      aria-label="Stats panel"
      aria-hidden={collapsed}
    >
      {/* Header */}
      <div className="p-4 flex items-center justify-between border-b border-gray-200 dark:border-gray-700">
        <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Statistics
        </span>
        <button
          type="button"
          onClick={onToggle}
          className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          aria-label="Collapse stats panel"
        >
          ✕
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <StatsContent />
      </div>
    </aside>
  );
}

// ---------------------------------------------------------------------------
// Mobile Stats Accordion (below canvas on narrow screens)
// ---------------------------------------------------------------------------

export function StatsPanelAccordion() {
  const [expanded, setExpanded] = useState(false);
  const activeCardId = useSessionStore((s) => s.activeCardId);
  const cards = useSessionStore((s) => s.cards);

  const activeCard = activeCardId
    ? cards.find((c) => c.id === activeCardId) ?? null
    : null;

  const metadata = activeCard?.renderedOutput?.metadata ?? null;
  const cardTitle = activeCard?.query
    ? activeCard.query.length > 40
      ? activeCard.query.slice(0, 40) + '…'
      : activeCard.query
    : 'Statistics';

  return (
    <div
      className="lg:hidden border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900"
      aria-label="Stats accordion"
    >
      {/* Accordion Header */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-4 py-3 text-left min-h-[44px]"
        aria-expanded={expanded}
        aria-controls="stats-accordion-content"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">
            {cardTitle}
          </span>
          {metadata?.latency_ms != null && (
            <span className="inline-flex shrink-0 items-center rounded bg-blue-100 dark:bg-blue-900 px-2 py-0.5 text-xs font-medium text-blue-800 dark:text-blue-200">
              {formatLatency(metadata.latency_ms)}
            </span>
          )}
        </div>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className={`h-4 w-4 shrink-0 text-gray-500 dark:text-gray-400 transition-transform duration-200 ${
            expanded ? 'rotate-180' : ''
          }`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Accordion Content */}
      {expanded && (
        <div
          id="stats-accordion-content"
          className="border-t border-gray-200 dark:border-gray-700 px-4 py-3 max-h-[50vh] overflow-y-auto"
        >
          <StatsContent />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Column Stats Section
// ---------------------------------------------------------------------------

function ColumnStatsSection({ column }: { column: ColumnMeta }) {
  return (
    <div className="rounded border border-gray-200 dark:border-gray-700 p-2">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
          {column.name}
        </span>
        <span className="text-xs text-gray-500 dark:text-gray-400 ml-2 shrink-0">
          {column.type}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-2 gap-y-1 text-xs text-gray-600 dark:text-gray-400">
        {/* Common stats for all column types */}
        {column.row_count != null && (
          <StatEntry label="Row count" value={column.row_count.toLocaleString()} />
        )}
        {column.null_percentage != null && (
          <StatEntry label="Null %" value={`${column.null_percentage.toFixed(2)}%`} />
        )}

        {/* Numeric-specific stats */}
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

        {/* Time-series-specific stats */}
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

function StatEntry({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="font-medium text-gray-500 dark:text-gray-400">{label}</dt>
      <dd className="text-gray-700 dark:text-gray-300 truncate" title={value}>
        {value}
      </dd>
    </>
  );
}
