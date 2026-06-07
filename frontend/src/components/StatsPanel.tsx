import { useSessionStore } from '../store/sessionStore';
import { formatLatency } from '../utils/formatters';
import type { ColumnMeta } from '../types';

/**
 * Renders per-column statistics for a single column entry.
 */
function ColumnStatsEntry({ column }: { column: ColumnMeta }) {
  return (
    <div className="border-b border-gray-200 pb-3 mb-3 last:border-b-0 last:pb-0 last:mb-0">
      <h4 className="text-sm font-semibold text-gray-800 mb-1">{column.name}</h4>
      <p className="text-xs text-gray-500 mb-2 capitalize">{column.type}</p>

      {/* Common stats for all column types */}
      <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        {column.row_count != null && (
          <>
            <dt className="text-gray-500">Row Count</dt>
            <dd className="text-gray-900 font-medium">{column.row_count}</dd>
          </>
        )}
        {column.null_percentage != null && (
          <>
            <dt className="text-gray-500">Null %</dt>
            <dd className="text-gray-900 font-medium">
              {column.null_percentage.toFixed(1)}%
            </dd>
          </>
        )}
      </dl>

      {/* Numeric stats */}
      {column.type === 'numeric' && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mt-1">
          {column.min != null && (
            <>
              <dt className="text-gray-500">Min</dt>
              <dd className="text-gray-900 font-medium">{column.min.toFixed(2)}</dd>
            </>
          )}
          {column.max != null && (
            <>
              <dt className="text-gray-500">Max</dt>
              <dd className="text-gray-900 font-medium">{column.max.toFixed(2)}</dd>
            </>
          )}
          {column.mean != null && (
            <>
              <dt className="text-gray-500">Mean</dt>
              <dd className="text-gray-900 font-medium">{column.mean.toFixed(2)}</dd>
            </>
          )}
          {column.median != null && (
            <>
              <dt className="text-gray-500">Median</dt>
              <dd className="text-gray-900 font-medium">{column.median.toFixed(2)}</dd>
            </>
          )}
          {column.std_dev != null && (
            <>
              <dt className="text-gray-500">Std Dev</dt>
              <dd className="text-gray-900 font-medium">{column.std_dev.toFixed(2)}</dd>
            </>
          )}
        </dl>
      )}

      {/* Categorical stats */}
      {column.type === 'categorical' && column.cardinality != null && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mt-1">
          <dt className="text-gray-500">Cardinality</dt>
          <dd className="text-gray-900 font-medium">{column.cardinality}</dd>
        </dl>
      )}

      {/* Time-series stats */}
      {column.type === 'time-series' && (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mt-1">
          {column.time_range_start != null && (
            <>
              <dt className="text-gray-500">Start</dt>
              <dd className="text-gray-900 font-medium">{column.time_range_start}</dd>
            </>
          )}
          {column.time_range_end != null && (
            <>
              <dt className="text-gray-500">End</dt>
              <dd className="text-gray-900 font-medium">{column.time_range_end}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}

/**
 * StatsPanel component — collapsible right panel displaying per-column
 * statistics for the active visualization card.
 *
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
 */
export function StatsPanel() {
  const activeCardId = useSessionStore((s) => s.activeCardId);
  const cards = useSessionStore((s) => s.cards);
  const collapsed = useSessionStore((s) => s.statsPanelCollapsed);
  const toggleStatsPanel = useSessionStore((s) => s.toggleStatsPanel);

  const activeCard = activeCardId ? cards.find((c) => c.id === activeCardId) : undefined;
  const columns = activeCard?.renderedOutput?.metadata?.columns;
  const latencyMs = activeCard?.renderedOutput?.metadata?.latency_ms;

  return (
    <aside
      className={`flex-shrink-0 border-l border-gray-200 bg-white transition-all duration-200 overflow-hidden ${
        collapsed ? 'w-0' : 'w-[300px]'
      }`}
      aria-label="Statistics Panel"
    >
      {/* Toggle button — always accessible */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-700">Statistics</h3>
        <button
          onClick={toggleStatsPanel}
          className="text-gray-400 hover:text-gray-600 text-xs"
          aria-label={collapsed ? 'Expand stats panel' : 'Collapse stats panel'}
        >
          {collapsed ? '◀' : '▶'}
        </button>
      </div>

      <div className="p-4 overflow-y-auto h-[calc(100%-49px)]">
        {/* Empty state: no card active */}
        {!activeCard && (
          <p className="text-sm text-gray-400 text-center mt-8">
            No card selected. Click a visualization card to view statistics.
          </p>
        )}

        {/* Empty state: card active but no columns */}
        {activeCard && (!columns || columns.length === 0) && (
          <p className="text-sm text-gray-400 text-center mt-8">
            No column statistics available for this card.
          </p>
        )}

        {/* Stats content */}
        {activeCard && columns && columns.length > 0 && (
          <>
            {/* Latency badge */}
            {latencyMs != null && (
              <div className="mb-4">
                <span className="inline-block bg-blue-50 text-blue-700 text-xs font-medium px-2 py-1 rounded">
                  {formatLatency(latencyMs)}
                </span>
              </div>
            )}

            {/* Per-column stats */}
            <div>
              {columns.map((col) => (
                <ColumnStatsEntry key={col.name} column={col} />
              ))}
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

export default StatsPanel;
