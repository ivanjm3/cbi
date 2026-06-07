import { useState, useCallback } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { exportPNG } from '../utils/pngExport';
import { exportCSV } from '../utils/csvExport';
import type { RenderedOutput } from '../types';

export interface CardToolbarProps {
  cardId: string;
  cardRef: React.RefObject<HTMLElement | null>;
  chartData: RenderedOutput;
  pinned: boolean;
  onExpandFullscreen: () => void;
}

/**
 * CardToolbar — action toolbar for each VisualizationCard.
 * Buttons: Download PNG, Download CSV, Pin/Unpin, Expand fullscreen, Bookmark, Drag handle.
 */
export default function CardToolbar({
  cardId,
  cardRef,
  chartData,
  pinned,
  onExpandFullscreen,
}: CardToolbarProps) {
  const pinCard = useSessionStore((s) => s.pinCard);
  const unpinCard = useSessionStore((s) => s.unpinCard);
  const saveBookmark = useSessionStore((s) => s.saveBookmark);

  const [exportError, setExportError] = useState<string | null>(null);

  const handleExportPNG = useCallback(async () => {
    setExportError(null);
    const element = cardRef.current;
    if (!element) {
      setExportError('Export failed');
      return;
    }
    await exportPNG(element, `chart-${cardId}.png`, () => {
      setExportError('Export failed');
    });
  }, [cardId, cardRef]);

  const handleExportCSV = useCallback(() => {
    setExportError(null);
    try {
      const data = chartData.chart_data;
      if (!data) {
        setExportError('Export failed');
        return;
      }

      // Extract headers and rows from chart_data
      const { headers, rows } = extractCSVData(data);
      exportCSV(headers, rows, `data-${cardId}.csv`);
    } catch {
      setExportError('Export failed');
    }
  }, [cardId, chartData]);

  const handleTogglePin = useCallback(() => {
    if (pinned) {
      unpinCard(cardId);
    } else {
      pinCard(cardId);
    }
  }, [cardId, pinned, pinCard, unpinCard]);

  const handleBookmark = useCallback(() => {
    saveBookmark(`Card ${cardId.slice(0, 8)}`);
  }, [cardId, saveBookmark]);

  return (
    <div className="flex items-center gap-1 px-2 py-1 border-b border-gray-200 bg-gray-50" data-testid="card-toolbar">
      {/* Download PNG */}
      <button
        onClick={handleExportPNG}
        className="p-1.5 rounded hover:bg-gray-200 transition-colors text-gray-600"
        aria-label="Download PNG"
        title="Download PNG"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <polyline points="21 15 16 10 5 21" />
        </svg>
      </button>

      {/* Download CSV */}
      <button
        onClick={handleExportCSV}
        className="p-1.5 rounded hover:bg-gray-200 transition-colors text-gray-600"
        aria-label="Download CSV"
        title="Download CSV"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="12" y1="18" x2="12" y2="12" />
          <polyline points="9 15 12 18 15 15" />
        </svg>
      </button>

      {/* Pin/Unpin */}
      <button
        onClick={handleTogglePin}
        className={`p-1.5 rounded hover:bg-gray-200 transition-colors ${pinned ? 'text-blue-600 bg-blue-100' : 'text-gray-600'}`}
        aria-label={pinned ? 'Unpin card' : 'Pin card'}
        title={pinned ? 'Unpin card' : 'Pin card'}
        aria-pressed={pinned}
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill={pinned ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="12" y1="17" x2="12" y2="22" />
          <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24z" />
        </svg>
      </button>

      {/* Expand fullscreen */}
      <button
        onClick={onExpandFullscreen}
        className="p-1.5 rounded hover:bg-gray-200 transition-colors text-gray-600"
        aria-label="Expand fullscreen"
        title="Expand fullscreen"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="15 3 21 3 21 9" />
          <polyline points="9 21 3 21 3 15" />
          <line x1="21" y1="3" x2="14" y2="10" />
          <line x1="3" y1="21" x2="10" y2="14" />
        </svg>
      </button>

      {/* Bookmark */}
      <button
        onClick={handleBookmark}
        className="p-1.5 rounded hover:bg-gray-200 transition-colors text-gray-600"
        aria-label="Bookmark"
        title="Bookmark"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
        </svg>
      </button>

      {/* Drag handle */}
      <div
        className="p-1.5 rounded cursor-grab text-gray-400 hover:text-gray-600 ml-auto"
        aria-label="Drag handle"
        title="Drag to reorder"
        data-testid="drag-handle"
      >
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="9" cy="5" r="1" />
          <circle cx="9" cy="12" r="1" />
          <circle cx="9" cy="19" r="1" />
          <circle cx="15" cy="5" r="1" />
          <circle cx="15" cy="12" r="1" />
          <circle cx="15" cy="19" r="1" />
        </svg>
      </div>

      {/* Export error message */}
      {exportError && (
        <span
          className="text-xs text-red-600 ml-2"
          role="alert"
          data-testid="export-error"
        >
          {exportError}
        </span>
      )}
    </div>
  );
}

/**
 * Extracts headers and rows from chart_data for CSV export.
 * Supports common formats: { labels, datasets } and { columns, rows }.
 */
function extractCSVData(data: Record<string, unknown>): { headers: string[]; rows: unknown[][] } {
  // Format: { labels: string[], datasets: [{ label, data }] }
  if (Array.isArray(data.labels) && Array.isArray(data.datasets)) {
    const labels = data.labels as string[];
    const datasets = data.datasets as Array<{ label?: string; data?: unknown[] }>;
    const headers = ['Label', ...datasets.map((ds) => ds.label ?? 'Value')];
    const rows = labels.map((label, idx) => [
      label,
      ...datasets.map((ds) => (ds.data ? ds.data[idx] : null)),
    ]);
    return { headers, rows };
  }

  // Format: { columns: string[], rows: unknown[][] }
  if (Array.isArray(data.columns) && Array.isArray(data.rows)) {
    return {
      headers: data.columns as string[],
      rows: data.rows as unknown[][],
    };
  }

  // Fallback: try to interpret as array of objects
  if (Array.isArray(data.data)) {
    const records = data.data as Record<string, unknown>[];
    if (records.length > 0) {
      const headers = Object.keys(records[0]);
      const rows = records.map((record) => headers.map((h) => record[h]));
      return { headers, rows };
    }
  }

  // No recognized structure
  return { headers: [], rows: [] };
}
