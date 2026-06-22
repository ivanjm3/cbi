/**
 * ChartRenderer component — renders Chart.js configs directly.
 *
 * The backend agent produces complete Chart.js v4 configurations.
 * This component renders them as-is using react-chartjs-2, supporting
 * ANY chart type Chart.js supports (bar, line, radar, doughnut, polarArea,
 * scatter, bubble, pie, etc.) without needing type-specific frontend code.
 *
 * For text-only responses or table data, renders appropriate fallbacks.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
 */

import { useMemo } from 'react';
import {
  Chart as ChartJS,
  registerables,
} from 'chart.js';
import { Chart } from 'react-chartjs-2';
import type { RenderedOutput } from '../types';

// Register ALL Chart.js components (handles any chart type the LLM might produce)
ChartJS.register(...registerables);

interface ChartRendererProps {
  renderedOutput: RenderedOutput;
  userRequestedChartType?: import('../types').ChartType | null;
  /** When true, chart fills available space without maintaining aspect ratio */
  fullscreen?: boolean;
}

/**
 * Extracts a Chart.js config from the rendered output.
 * The backend returns configs in `chart_data` with `type`, `data`, and `options`.
 */
function extractChartJsConfig(chartData: Record<string, unknown> | null | undefined): {
  type: string;
  data: Record<string, unknown>;
  options: Record<string, unknown>;
} | null {
  if (!chartData) return null;

  // Table format takes priority — not a Chart.js chart
  if (chartData.type === 'table') return null;

  // Direct Chart.js config: { type, data, options }
  if (chartData.type && chartData.data && typeof chartData.data === 'object') {
    return {
      type: chartData.type as string,
      data: chartData.data as Record<string, unknown>,
      options: (chartData.options as Record<string, unknown>) ?? {},
    };
  }

  return null;
}

/**
 * Extracts table data from chart_data for table rendering.
 */
function extractTableData(chartData: Record<string, unknown> | null | undefined): {
  columns: string[];
  rows: unknown[][];
} | null {
  if (!chartData) return null;

  if (chartData.type === 'table' && Array.isArray(chartData.columns) && Array.isArray(chartData.rows)) {
    return {
      columns: chartData.columns as string[],
      rows: chartData.rows as unknown[][],
    };
  }

  // Also handle { columns, rows } without explicit type
  if (Array.isArray(chartData.columns) && Array.isArray(chartData.rows) && !chartData.type) {
    return {
      columns: chartData.columns as string[],
      rows: chartData.rows as unknown[][],
    };
  }

  return null;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RenderChartJs({ config, fullscreen }: { config: { type: string; data: Record<string, unknown>; options: Record<string, unknown> }; fullscreen?: boolean }) {
  // Enhance chart options for proper responsive scaling
  const enhancedOptions = useMemo(() => {
    const baseOptions = config.options as any || {};
    
    return {
      ...baseOptions,
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        ...(baseOptions.plugins || {}),
        legend: {
          ...(baseOptions.plugins?.legend || {}),
          labels: {
            ...(baseOptions.plugins?.legend?.labels || {}),
            usePointStyle: true,
            padding: 12,
            boxWidth: 8,
            boxHeight: 8,
          },
        },
      },
      layout: {
        ...(baseOptions.layout || {}),
        padding: { top: 8, bottom: 8, left: 8, right: 8 },
      },
    };
  }, [config.options, fullscreen]);

  return (
    <div
      className="w-full relative"
      style={{ minHeight: fullscreen ? '400px' : '280px', height: fullscreen ? '80vh' : '340px' }}
      aria-label={`${config.type} chart`}
    >
      <Chart
        type={config.type as any}
        data={config.data as any}
        options={enhancedOptions as any}
      />
    </div>
  );
}

function RenderDataTable({ columns, rows }: { columns: string[]; rows: unknown[][] }) {
  if (rows.length === 0) return <p className="text-sm text-text-muted">No data</p>;

  return (
    <div className="overflow-x-auto" aria-label="Data table" role="table">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className="p-2 text-left font-medium text-text-secondary border border-border-default bg-bg-input"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 200).map((row, rowIdx) => (
            <tr key={rowIdx} className="hover:bg-bg-input/50">
              {row.map((cell, colIdx) => (
                <td
                  key={colIdx}
                  className="p-2 text-text-primary border border-border-default"
                >
                  {cell != null ? String(cell) : '—'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RenderTextBlock({ content, description }: { content: string; description: string }) {
  return (
    <div className="space-y-3" aria-label="Text output">
      <div className="prose prose-sm max-w-none">
        <p className="whitespace-pre-wrap text-text-primary">{content}</p>
      </div>
      {description && description !== content && (
        <p className="text-xs text-text-muted italic">{description}</p>
      )}
    </div>
  );
}

function RenderError({ message }: { message: string }) {
  return (
    <div
      className="flex items-center gap-2 rounded border border-status-error/30 bg-red-50 p-4"
      role="alert"
      aria-label="Chart error"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-5 w-5 text-status-error"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      <span className="text-sm text-status-error">{message}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ChartRenderer
// ---------------------------------------------------------------------------

export function ChartRenderer({ renderedOutput, fullscreen }: ChartRendererProps) {
  // Guard against undefined renderedOutput
  if (!renderedOutput) {
    return <RenderError message="No visualization data available." />;
  }

  // Handle text-only output
  if (renderedOutput.output_type === 'text' || (!renderedOutput.chart_data && renderedOutput.text_content)) {
    const textContent = renderedOutput.text_content ?? renderedOutput.description ?? '';
    return (
      <RenderTextBlock
        content={textContent}
        description={renderedOutput.description ?? ''}
      />
    );
  }

  // Try to extract a Chart.js config
  const chartConfig = extractChartJsConfig(renderedOutput.chart_data);
  if (chartConfig) {
    return <RenderChartJs config={chartConfig} fullscreen={fullscreen} />;
  }

  // Try table format
  const tableData = extractTableData(renderedOutput.chart_data);
  if (tableData) {
    return <RenderDataTable columns={tableData.columns} rows={tableData.rows} />;
  }

  // Nothing renderable
  return <RenderError message="Chart could not be rendered — unsupported data format" />;
}
