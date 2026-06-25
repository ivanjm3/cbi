/**
 * CardToolbar component.
 *
 * Renders action buttons on each Visualization Card:
 * - Download PNG: exports the chart area as a PNG image
 * - Download CSV: exports the underlying data as a CSV file
 * - Pin/Unpin: toggles card persistence across new queries
 * - Expand fullscreen: opens the card in a fullscreen modal overlay
 * - Save Prompt: saves the current session as a saved prompt
 * - Three-dot menu: provides additional actions (Schedule, Rename, Delete)
 * - Drag handle: visual handle for drag-to-reorder
 *
 * Displays inline error toast on export failure (auto-dismisses after 3s).
 *
 * Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 5.1, 5.2, 5.3, 5.5, 5.6, 5.7
 */

import { useCallback, useRef, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { CardState, ChartType } from '../types';
import { useSessionStore } from '../store/sessionStore';
import { exportCSV } from '../utils/csvExport';
import { exportPNG } from '../utils/pngExport';
import { AVAILABLE_VIZ_TYPES } from '../utils/chartTypeConverter';

export interface CardToolbarProps {
  card: CardState;
  /** Optional ref to the chart container element for PNG export */
  chartRef?: React.RefObject<HTMLElement | null>;
  /** Callback to open the fullscreen modal */
  onExpandFullscreen?: () => void;
  /** Ref callback for the drag handle element — provided by DraggableCard via VisualizationCard */
  dragHandleRef?: (el: HTMLElement | null) => void;
}

export function CardToolbar({
  card,
  chartRef,
  onExpandFullscreen,
  dragHandleRef,
}: CardToolbarProps) {
  const navigate = useNavigate();
  const pinCard = useSessionStore((s) => s.pinCard);
  const unpinCard = useSessionStore((s) => s.unpinCard);
  const saveSavedPrompt = useSessionStore((s) => s.saveSavedPrompt);
  const changeCardVisualizationType = useSessionStore((s) => s.changeCardVisualizationType);

  const [exportError, setExportError] = useState<string | null>(null);
  const [vizTypeMenuOpen, setVizTypeMenuOpen] = useState(false);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const vizMenuRef = useRef<HTMLDivElement>(null);
  const moreMenuRef = useRef<HTMLDivElement>(null);

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (vizMenuRef.current && !vizMenuRef.current.contains(event.target as Node)) {
        setVizTypeMenuOpen(false);
      }
      if (moreMenuRef.current && !moreMenuRef.current.contains(event.target as Node)) {
        setMoreMenuOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Clear export error after a delay
  const showExportError = useCallback((message: string) => {
    setExportError(message);
    if (errorTimeoutRef.current) {
      clearTimeout(errorTimeoutRef.current);
    }
    errorTimeoutRef.current = setTimeout(() => {
      setExportError(null);
      errorTimeoutRef.current = null;
    }, 3000);
  }, []);

  // ----- PNG Export -----
  const handleDownloadPNG = useCallback(async () => {
    if (!chartRef?.current) {
      showExportError('Export failed: chart element not available');
      return;
    }
    await exportPNG({
      element: chartRef.current,
      filename: `chart-${card.id}`,
      onError: (error) => {
        showExportError(`Export failed: ${error.message}`);
      },
    });
  }, [chartRef, card.id, showExportError]);

  // ----- CSV Export -----
  const handleDownloadCSV = useCallback(() => {
    try {
      const chartData = card.renderedOutput.chart_data;
      if (!chartData) {
        showExportError('Export failed: no data available');
        return;
      }

      let headers: string[] = [];
      let rows: string[][] = [];

      // Handle nested Chart.js format: { type, data: { labels, datasets }, options }
      const nestedData = (chartData as Record<string, unknown>).data;
      if (nestedData && typeof nestedData === 'object' && !Array.isArray(nestedData)) {
        const nested = nestedData as Record<string, unknown>;
        if (Array.isArray(nested.labels) && Array.isArray(nested.datasets)) {
          const labels = nested.labels as string[];
          const datasets = nested.datasets as Array<{ label?: string; data?: unknown[] }>;

          // Check if datasets use object-format data (scatter/bubble: [{x, y}, ...])
          const firstDataPoint = datasets[0]?.data?.[0];
          if (firstDataPoint && typeof firstDataPoint === 'object' && !Array.isArray(firstDataPoint)) {
            // Object-format data points (scatter: {x,y}, bubble: {x,y,r})
            const samplePoint = firstDataPoint as Record<string, unknown>;
            const pointKeys = Object.keys(samplePoint); // e.g., ['x', 'y'] or ['x', 'y', 'r']
            headers = ['Dataset', ...pointKeys];
            for (const ds of datasets) {
              const dsLabel = ds.label ?? 'Value';
              for (const point of (ds.data ?? []) as Record<string, unknown>[]) {
                if (point && typeof point === 'object') {
                  rows.push([dsLabel, ...pointKeys.map((k) => String(point[k] ?? ''))]);
                }
              }
            }
          } else {
            // Standard label-based data
            headers = ['Label', ...datasets.map((ds) => ds.label ?? 'Value')];
            rows = labels.map((label: string, i: number) => [
              String(label),
              ...datasets.map((ds) => String(ds.data?.[i] ?? '')),
            ]);
          }
        } else if (Array.isArray(nested.datasets)) {
          // No labels but has datasets (scatter/bubble without labels)
          const datasets = nested.datasets as Array<{ label?: string; data?: unknown[] }>;
          const firstDataPoint = datasets[0]?.data?.[0];
          if (firstDataPoint && typeof firstDataPoint === 'object' && !Array.isArray(firstDataPoint)) {
            const samplePoint = firstDataPoint as Record<string, unknown>;
            const pointKeys = Object.keys(samplePoint);
            headers = ['Dataset', ...pointKeys];
            for (const ds of datasets) {
              const dsLabel = ds.label ?? 'Value';
              for (const point of (ds.data ?? []) as Record<string, unknown>[]) {
                if (point && typeof point === 'object') {
                  rows.push([dsLabel, ...pointKeys.map((k) => String(point[k] ?? ''))]);
                }
              }
            }
          }
        }
      }

      // Handle top-level labels + datasets
      if (headers.length === 0) {
        const topLevel = chartData as Record<string, unknown>;
        if (Array.isArray(topLevel.labels) && Array.isArray(topLevel.datasets)) {
          const labels = topLevel.labels as string[];
          const datasets = topLevel.datasets as Array<{ label?: string; data?: unknown[] }>;

          const firstDataPoint = datasets[0]?.data?.[0];
          if (firstDataPoint && typeof firstDataPoint === 'object' && !Array.isArray(firstDataPoint)) {
            const samplePoint = firstDataPoint as Record<string, unknown>;
            const pointKeys = Object.keys(samplePoint);
            headers = ['Dataset', ...pointKeys];
            for (const ds of datasets) {
              const dsLabel = ds.label ?? 'Value';
              for (const point of (ds.data ?? []) as Record<string, unknown>[]) {
                if (point && typeof point === 'object') {
                  rows.push([dsLabel, ...pointKeys.map((k) => String(point[k] ?? ''))]);
                }
              }
            }
          } else {
            headers = ['Label', ...datasets.map((ds) => ds.label ?? 'Value')];
            rows = labels.map((label: string, i: number) => [
              String(label),
              ...datasets.map((ds) => String(ds.data?.[i] ?? '')),
            ]);
          }
        }
      }

      // Handle array of objects
      if (headers.length === 0 && Array.isArray(chartData)) {
        if (chartData.length > 0 && typeof chartData[0] === 'object') {
          headers = Object.keys(chartData[0] as Record<string, unknown>);
          rows = (chartData as Record<string, unknown>[]).map((item) =>
            headers.map((h) => String(item[h] ?? '')),
          );
        }
      }

      // Handle { columns, rows } table format
      if (headers.length === 0) {
        const tableData = chartData as Record<string, unknown>;
        if (Array.isArray(tableData.columns) && Array.isArray(tableData.rows)) {
          headers = tableData.columns as string[];
          rows = (tableData.rows as unknown[][]).map((row: unknown[]) =>
            row.map((cell) => String(cell ?? '')),
          );
        }
      }

      if (headers.length === 0) {
        showExportError('Export failed: unsupported data format');
        return;
      }

      exportCSV(headers, rows, `data-${card.id}.csv`);
    } catch {
      showExportError('Export failed: unexpected error');
    }
  }, [card.renderedOutput.chart_data, card.id, showExportError]);

  // ----- Pin/Unpin -----
  const handleTogglePin = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      if (card.pinned) {
        unpinCard(card.id);
      } else {
        pinCard(card.id);
      }
    },
    [card.id, card.pinned, pinCard, unpinCard],
  );

  // ----- Expand Fullscreen -----
  const handleExpandFullscreen = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onExpandFullscreen?.();
    },
    [onExpandFullscreen],
  );

  // ----- Save Chat Session -----
  const handleSavePrompt = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      // Save the current chat session (all cards in this thread)
      const sessionName = card.query.slice(0, 100) || 'Untitled Session';
      saveSavedPrompt(sessionName);
    },
    [card.query, saveSavedPrompt],
  );

  // ----- Schedule Report (whole chat session - all pinned cards) -----
  const handleScheduleReport = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setMoreMenuOpen(false);
      // Get all pinned cards from the session store
      const allCards = useSessionStore.getState().cards;
      const pinnedCardIds = Object.values(allCards)
        .filter(c => c.pinned)
        .map(c => c.id);
      
      if (pinnedCardIds.length === 0) {
        console.warn('No pinned cards to schedule');
        return;
      }
      
      // Navigate to scheduled reports creation page with all pinned card IDs
      // Note: The chat_id will be the current session ID (if available from context)
      // For now, use a placeholder - this will be passed from the session context
      const vizIds = pinnedCardIds.join(',');
      navigate(`/scheduled-reports/new?chat_id=current-session&viz_ids=${vizIds}`);
    },
    [navigate],
  );

  // ----- Rename Card (placeholder) -----
  const handleRenameCard = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setMoreMenuOpen(false);
      // TODO: Implement rename dialog/modal
      console.log('Rename card:', card.id);
    },
    [card.id],
  );

  // ----- Delete Card -----
  const handleDeleteCard = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setMoreMenuOpen(false);
      // TODO: Implement delete with confirmation dialog
      console.log('Delete card:', card.id);
    },
    [card.id],
  );

  // ----- Change Visualization Type -----
  const handleChangeVisualizationType = useCallback(
    (e: React.MouseEvent, newType: ChartType | 'text') => {
      e.stopPropagation();
      changeCardVisualizationType(card.id, newType);
      setVizTypeMenuOpen(false);
    },
    [card.id, changeCardVisualizationType],
  );

  return (
    <div className="relative">
      <div
        className="flex items-center gap-1 py-2 border-b border-border-default"
        role="toolbar"
        aria-label={`Toolbar for card: ${card.query}`}
      >
        {/* Drag handle (leftmost) */}
        <button
          type="button"
          ref={dragHandleRef as React.Ref<HTMLButtonElement>}
          className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-bg-input transition-colors duration-200 cursor-grab active:cursor-grabbing"
          title="Drag to reorder"
          aria-label="Drag to reorder"
          data-drag-handle
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 8h16M4 16h16"
            />
          </svg>
        </button>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Visualization Type Selector */}
        <div className="relative" ref={vizMenuRef}>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setVizTypeMenuOpen(!vizTypeMenuOpen);
            }}
            className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-subtle transition-colors duration-200"
            title="Change visualization type"
            aria-label="Change visualization type"
            aria-haspopup="menu"
            aria-expanded={vizTypeMenuOpen}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
              />
            </svg>
          </button>

          {/* Visualization Type Dropdown Menu */}
          {vizTypeMenuOpen && (
            <div
              className="absolute right-0 mt-1 w-32 bg-bg-secondary border border-border-default rounded-lg shadow-card z-20 py-1"
              role="menu"
            >
              {AVAILABLE_VIZ_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={(e) => handleChangeVisualizationType(e, type)}
                  className={`w-full text-left px-3 py-2 text-sm transition-colors duration-200 ${
                    card.selectedVisualizationType === type
                      ? 'bg-accent-primary/10 text-accent-primary font-medium'
                      : 'text-text-primary hover:bg-bg-input'
                  }`}
                  role="menuitem"
                >
                  {type === 'text' ? 'Text' : type.charAt(0).toUpperCase() + type.slice(1)}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Download PNG */}
        <button
          type="button"
          onClick={handleDownloadPNG}
          className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-subtle transition-colors duration-200"
          title="Download PNG"
          aria-label="Download PNG"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </button>

        {/* Download CSV */}
        <button
          type="button"
          onClick={handleDownloadCSV}
          className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-subtle transition-colors duration-200"
          title="Download CSV"
          aria-label="Download CSV"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </button>

        {/* Pin/Unpin */}
        <button
          type="button"
          onClick={handleTogglePin}
          className={`p-1.5 rounded-lg transition-colors duration-200 ${
            card.pinned
              ? 'text-amber-500 hover:bg-amber-50'
              : 'text-text-muted hover:text-amber-500 hover:bg-accent-subtle'
          }`}
          title={card.pinned ? 'Unpin card' : 'Pin to canvas'}
          aria-label={card.pinned ? 'Unpin card' : 'Pin to canvas'}
          aria-pressed={card.pinned}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill={card.pinned ? 'currentColor' : 'none'}
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={card.pinned ? 0 : 2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"
            />
          </svg>
        </button>

        {/* Expand Fullscreen */}
        <button
          type="button"
          onClick={handleExpandFullscreen}
          className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-subtle transition-colors duration-200"
          title="Expand fullscreen"
          aria-label="Expand fullscreen"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5v-4m0 4h-4m4 0l-5-5"
            />
          </svg>
        </button>

        {/* Save Chat */}
        <button
          type="button"
          onClick={handleSavePrompt}
          className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-subtle transition-colors duration-200"
          title="Save Chat"
          aria-label="Save Chat"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
            />
          </svg>
        </button>

        {/* Three-dot menu (More actions) */}
        <div className="relative" ref={moreMenuRef}>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setMoreMenuOpen(!moreMenuOpen);
            }}
            className="p-1.5 rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-subtle transition-colors duration-200"
            title="More actions"
            aria-label="More actions"
            aria-haspopup="menu"
            aria-expanded={moreMenuOpen}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M12 8a2 2 0 110-4 2 2 0 010 4zM12 14a2 2 0 110-4 2 2 0 010 4zM12 20a2 2 0 110-4 2 2 0 010 4z" />
            </svg>
          </button>

          {/* Three-dot Menu Dropdown */}
          {moreMenuOpen && (
            <div
              className="absolute right-0 mt-1 w-40 bg-bg-secondary border border-border-default rounded-lg shadow-card z-20 py-1"
              role="menu"
            >
              {/* Schedule option - only for pinned cards */}
              {card.pinned && (
                <>
                  <button
                    type="button"
                    onClick={handleScheduleReport}
                    className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-bg-input transition-colors duration-200 flex items-center gap-2"
                    role="menuitem"
                  >
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-4 w-4"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={2}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    Schedule
                  </button>
                  <div className="border-t border-border-default" />
                </>
              )}

              {/* Rename option */}
              <button
                type="button"
                onClick={handleRenameCard}
                className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-bg-input transition-colors duration-200 flex items-center gap-2"
                role="menuitem"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                  />
                </svg>
                Rename
              </button>

              {/* Delete option */}
              <button
                type="button"
                onClick={handleDeleteCard}
                className="w-full text-left px-3 py-2 text-sm text-status-error hover:bg-red-50 transition-colors duration-200 flex items-center gap-2"
                role="menuitem"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={2}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
                Delete
              </button>
            </div>
          )}
        </div>

        {/* Export error toast - inline on the card */}
        {exportError && (
          <div
            className="absolute top-full left-0 right-0 mt-2 px-3 py-2 text-xs text-status-error bg-red-50 border border-red-200 rounded-lg shadow-card"
            role="alert"
            aria-live="polite"
          >
            {exportError}
          </div>
        )}
      </div>
    </div>
  );
}
