/**
 * CardToolbar component.
 *
 * Renders action buttons on each Visualization Card:
 * - Download PNG: exports the chart area as a PNG image
 * - Download CSV: exports the underlying data as a CSV file
 * - Pin/Unpin: toggles card persistence across new queries
 * - Bookmark: toggles card-level bookmark state
 *
 * Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7
 */

import { useCallback, useRef, useState } from 'react';
import type { CardState } from '../types';
import { useSessionStore } from '../store/sessionStore';
import { exportCSV } from '../utils/csvExport';
import { exportPNG } from '../utils/pngExport';

export interface CardToolbarProps {
  card: CardState;
  /** Optional ref to the chart container element for PNG export */
  chartRef?: React.RefObject<HTMLElement | null>;
}

export function CardToolbar({
  card,
  chartRef,
}: CardToolbarProps) {
  const pinCard = useSessionStore((s) => s.pinCard);
  const unpinCard = useSessionStore((s) => s.unpinCard);
  const toggleCardBookmark = useSessionStore((s) => s.toggleCardBookmark);

  const [exportError, setExportError] = useState<string | null>(null);
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

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
      const nestedData = (chartData as any).data;
      if (nestedData && typeof nestedData === 'object' && !Array.isArray(nestedData)) {
        if (Array.isArray(nestedData.labels) && Array.isArray(nestedData.datasets)) {
          const labels = nestedData.labels as string[];
          const datasets = nestedData.datasets as Array<{ label?: string; data?: unknown[] }>;
          headers = ['Label', ...datasets.map((ds: any) => ds.label ?? 'Value')];
          rows = labels.map((label: string, i: number) => [
            String(label),
            ...datasets.map((ds: any) => String(ds.data?.[i] ?? '')),
          ]);
        }
      }

      // Handle top-level labels + datasets
      if (headers.length === 0 && Array.isArray((chartData as any).labels) && Array.isArray((chartData as any).datasets)) {
        const labels = (chartData as any).labels as string[];
        const datasets = (chartData as any).datasets as Array<{ label?: string; data?: unknown[] }>;
        headers = ['Label', ...datasets.map((ds: any) => ds.label ?? 'Value')];
        rows = labels.map((label: string, i: number) => [
          String(label),
          ...datasets.map((ds: any) => String(ds.data?.[i] ?? '')),
        ]);
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
      if (headers.length === 0 && Array.isArray((chartData as any).columns) && Array.isArray((chartData as any).rows)) {
        headers = (chartData as any).columns;
        rows = ((chartData as any).rows as unknown[][]).map((row: unknown[]) =>
          row.map((cell) => String(cell ?? '')),
        );
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

  // ----- Bookmark -----
  const handleBookmark = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      toggleCardBookmark(card.id);
    },
    [card.id, toggleCardBookmark],
  );

  return (
    <div className="relative">
      <div
        className="flex items-center gap-1 py-1 border-b border-gray-100 dark:border-gray-800"
        role="toolbar"
        aria-label={`Toolbar for card: ${card.query}`}
      >
        {/* Spacer */}
        <div className="flex-1" />

        {/* Download PNG */}
        <button
          type="button"
          onClick={handleDownloadPNG}
          className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
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
          className="p-1 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
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
          className={`p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 ${
            card.pinned
              ? 'text-amber-500 dark:text-amber-400'
              : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
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

        {/* Bookmark */}
        <button
          type="button"
          onClick={handleBookmark}
          className={`p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 ${
            card.bookmarked
              ? 'text-blue-500 dark:text-blue-400'
              : 'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300'
          }`}
          title={card.bookmarked ? 'Remove bookmark' : 'Bookmark'}
          aria-label={card.bookmarked ? 'Remove bookmark' : 'Bookmark'}
          aria-pressed={card.bookmarked}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill={card.bookmarked ? 'currentColor' : 'none'}
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={card.bookmarked ? 0 : 2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
            />
          </svg>
        </button>
      </div>

      {/* Export error message */}
      {exportError && (
        <div
          className="absolute top-full left-0 right-0 mt-1 px-2 py-1 text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded"
          role="alert"
          aria-live="polite"
        >
          {exportError}
        </div>
      )}
    </div>
  );
}
