/**
 * ChartRenderer component.
 * Renders the appropriate chart type based on the selectChartType result.
 * Supports: BarChart, LineChart, ScatterChart, PieChart, HeatmapChart, DataTable, and text output.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
 */

import {
  BarChart,
  Bar,
  LineChart,
  Line,
  ScatterChart,
  Scatter,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Brush,
} from 'recharts';
import type { RenderedOutput } from '../types';
import { selectChartType } from '../utils/chartSelector';
import type { ChartType } from '../utils/chartSelector';

interface ChartRendererProps {
  renderedOutput: RenderedOutput;
}

// Default color palette for charts
const COLORS = [
  '#3b82f6', // blue-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#ef4444', // red-500
  '#8b5cf6', // violet-500
  '#06b6d4', // cyan-500
  '#f97316', // orange-500
  '#84cc16', // lime-500
];

/**
 * Extracts chart data rows from the rendered output chart_data field.
 * Attempts to handle common data shapes from the backend.
 */
function extractChartData(chartData: Record<string, unknown> | null | undefined): Record<string, unknown>[] | null {
  if (!chartData) return null;

  // If chart_data has a "data" key that is an array, use it directly
  if (Array.isArray(chartData.data)) {
    return chartData.data as Record<string, unknown>[];
  }

  // If chart_data has "labels" and "datasets" (Chart.js style, top-level)
  if (Array.isArray(chartData.labels) && Array.isArray(chartData.datasets)) {
    const labels = chartData.labels as string[];
    const datasets = chartData.datasets as Array<{ label?: string; data: number[] }>;

    return labels.map((label, i) => {
      const row: Record<string, unknown> = { name: label };
      datasets.forEach((ds) => {
        const key = ds.label ?? `value${datasets.indexOf(ds)}`;
        row[key] = ds.data?.[i] ?? 0;
      });
      return row;
    });
  }

  // If chart_data has nested "data" object with "labels" and "datasets" (Chart.js wrapped)
  if (chartData.data && typeof chartData.data === 'object' && !Array.isArray(chartData.data)) {
    const nested = chartData.data as Record<string, unknown>;
    if (Array.isArray(nested.labels) && Array.isArray(nested.datasets)) {
      const labels = nested.labels as string[];
      const datasets = nested.datasets as Array<{ label?: string; data: number[] | Array<{x: number; y: number}> }>;

      // Check if datasets contain point objects (scatter/bubble) or plain numbers
      const firstDataset = datasets[0];
      if (firstDataset?.data?.length && typeof firstDataset.data[0] === 'object') {
        // Scatter/bubble: data is [{x, y}, ...] — flatten into rows
        return firstDataset.data.map((point) => {
          if (typeof point === 'object' && point !== null) {
            return point as Record<string, unknown>;
          }
          return { value: point };
        });
      }

      return labels.map((label, i) => {
        const row: Record<string, unknown> = { name: label };
        datasets.forEach((ds) => {
          const key = ds.label ?? `value${datasets.indexOf(ds)}`;
          row[key] = (ds.data as number[])?.[i] ?? 0;
        });
        return row;
      });
    }

    // Nested data with datasets but no labels (scatter format)
    if (Array.isArray(nested.datasets)) {
      const datasets = nested.datasets as Array<{ label?: string; data: Array<{x: number; y: number; r?: number}> }>;
      const firstDataset = datasets[0];
      if (firstDataset?.data?.length) {
        return firstDataset.data.map((point) => point as unknown as Record<string, unknown>);
      }
    }
  }

  // If chart_data itself is an array
  if (Array.isArray(chartData)) {
    return chartData as Record<string, unknown>[];
  }

  // If chart_data has "rows" and "columns" (table format)
  if (Array.isArray(chartData.rows) && Array.isArray(chartData.columns)) {
    const columns = chartData.columns as string[];
    const rows = chartData.rows as unknown[][];
    return rows.map((row) => {
      const obj: Record<string, unknown> = {};
      columns.forEach((col, i) => {
        obj[col] = row[i];
      });
      return obj;
    });
  }

  return null;
}

/**
 * Extracts numeric keys from data rows for use as chart value fields.
 */
function getNumericKeys(data: Record<string, unknown>[]): string[] {
  if (data.length === 0) return [];
  const firstRow = data[0];
  return Object.keys(firstRow).filter((key) => typeof firstRow[key] === 'number');
}

/**
 * Gets the category/label key from data rows (first non-numeric key).
 */
function getCategoryKey(data: Record<string, unknown>[]): string {
  if (data.length === 0) return 'name';
  const firstRow = data[0];
  const key = Object.keys(firstRow).find((k) => typeof firstRow[k] !== 'number');
  return key ?? 'name';
}

// ---------------------------------------------------------------------------
// Sub-components for each chart type
// ---------------------------------------------------------------------------

function RenderBarChart({ data }: { data: Record<string, unknown>[] }) {
  const categoryKey = getCategoryKey(data);
  const numericKeys = getNumericKeys(data);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} aria-label="Bar chart">
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={categoryKey} />
        <YAxis />
        <Tooltip />
        <Legend />
        {numericKeys.map((key, i) => (
          <Bar key={key} dataKey={key} fill={COLORS[i % COLORS.length]} cursor="pointer" />
        ))}
        <Brush dataKey={categoryKey} height={20} stroke="#3b82f6" />
      </BarChart>
    </ResponsiveContainer>
  );
}

function RenderLineChart({ data }: { data: Record<string, unknown>[] }) {
  const categoryKey = getCategoryKey(data);
  const numericKeys = getNumericKeys(data);

  return (
    <ResponsiveContainer width="100%" height={300}>
      <LineChart data={data} aria-label="Line chart">
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={categoryKey} />
        <YAxis />
        <Tooltip />
        <Legend />
        {numericKeys.map((key, i) => (
          <Line
            key={key}
            type="monotone"
            dataKey={key}
            stroke={COLORS[i % COLORS.length]}
            activeDot={{ r: 6 }}
            cursor="pointer"
          />
        ))}
        <Brush dataKey={categoryKey} height={20} stroke="#3b82f6" />
      </LineChart>
    </ResponsiveContainer>
  );
}

function RenderScatterChart({ data }: { data: Record<string, unknown>[] }) {
  const numericKeys = getNumericKeys(data);
  const xKey = numericKeys[0] ?? 'x';
  const yKey = numericKeys[1] ?? 'y';

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart aria-label="Scatter chart">
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey={xKey} name={xKey} type="number" />
        <YAxis dataKey={yKey} name={yKey} type="number" />
        <Tooltip cursor={{ strokeDasharray: '3 3' }} />
        <Scatter data={data} fill={COLORS[0]} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function RenderPieChart({ data }: { data: Record<string, unknown>[] }) {
  const categoryKey = getCategoryKey(data);
  const numericKeys = getNumericKeys(data);
  const valueKey = numericKeys[0] ?? 'value';

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart aria-label="Pie chart">
        <Tooltip />
        <Legend />
        <Pie
          data={data}
          dataKey={valueKey}
          nameKey={categoryKey}
          cx="50%"
          cy="50%"
          outerRadius={100}
          label
        >
          {data.map((_, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
      </PieChart>
    </ResponsiveContainer>
  );
}

function RenderHeatmapChart({ data }: { data: Record<string, unknown>[] }) {
  // Heatmap rendered as a color-coded table since Recharts doesn't have a native heatmap
  const numericKeys = getNumericKeys(data);
  const categoryKey = getCategoryKey(data);

  // Compute min/max for color scaling
  let globalMin = Infinity;
  let globalMax = -Infinity;
  data.forEach((row) => {
    numericKeys.forEach((key) => {
      const val = row[key] as number;
      if (typeof val === 'number' && !isNaN(val)) {
        if (val < globalMin) globalMin = val;
        if (val > globalMax) globalMax = val;
      }
    });
  });

  function getCellColor(value: number): string {
    if (globalMax === globalMin) return 'rgb(59, 130, 246)';
    const ratio = (value - globalMin) / (globalMax - globalMin);
    // Gradient from light blue to dark blue
    const r = Math.round(219 - ratio * 160);
    const g = Math.round(234 - ratio * 104);
    const b = Math.round(254 - ratio * 8);
    return `rgb(${r}, ${g}, ${b})`;
  }

  return (
    <div className="overflow-x-auto" aria-label="Heatmap chart" role="table">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            <th className="p-2 text-left font-medium text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700">
              {categoryKey}
            </th>
            {numericKeys.map((key) => (
              <th
                key={key}
                className="p-2 text-center font-medium text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700"
              >
                {key}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIdx) => (
            <tr key={rowIdx}>
              <td className="p-2 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700">
                {String(row[categoryKey] ?? '')}
              </td>
              {numericKeys.map((key) => {
                const val = row[key] as number;
                return (
                  <td
                    key={key}
                    className="p-2 text-center border border-gray-200 dark:border-gray-700 font-mono"
                    style={{ backgroundColor: getCellColor(val) }}
                    title={`${key}: ${val}`}
                  >
                    {typeof val === 'number' ? val.toLocaleString() : String(val)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RenderDataTable({ data }: { data: Record<string, unknown>[] }) {
  if (data.length === 0) return <p className="text-sm text-gray-500">No data</p>;

  const columns = Object.keys(data[0]);

  return (
    <div className="overflow-x-auto" aria-label="Data table" role="table">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className="p-2 text-left font-medium text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIdx) => (
            <tr key={rowIdx} className="hover:bg-gray-50 dark:hover:bg-gray-800">
              {columns.map((col) => (
                <td
                  key={col}
                  className="p-2 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700"
                >
                  {row[col] != null ? String(row[col]) : '—'}
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
      <div className="prose prose-sm dark:prose-invert max-w-none">
        <p className="whitespace-pre-wrap text-gray-800 dark:text-gray-200">{content}</p>
      </div>
      {description && (
        <p className="text-xs text-gray-500 dark:text-gray-400 italic">{description}</p>
      )}
    </div>
  );
}

function RenderError({ message }: { message: string }) {
  return (
    <div
      className="flex items-center gap-2 rounded border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4"
      role="alert"
      aria-label="Chart error"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-5 w-5 text-red-500"
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
      <span className="text-sm text-red-700 dark:text-red-300">{message}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main ChartRenderer
// ---------------------------------------------------------------------------

export function ChartRenderer({ renderedOutput }: ChartRendererProps) {
  const chartType: ChartType = selectChartType(renderedOutput);

  // Handle text-only output
  if (chartType === 'text') {
    const textContent = renderedOutput.text_content ?? renderedOutput.description ?? '';
    return (
      <RenderTextBlock
        content={textContent}
        description={renderedOutput.description}
      />
    );
  }

  // Extract chart data
  const data = extractChartData(renderedOutput.chart_data);

  // Handle invalid/missing chart_data
  if (!data || data.length === 0) {
    return <RenderError message="Chart could not be rendered" />;
  }

  switch (chartType) {
    case 'bar':
      return <RenderBarChart data={data} />;
    case 'line':
      return <RenderLineChart data={data} />;
    case 'scatter':
      return <RenderScatterChart data={data} />;
    case 'pie':
      return <RenderPieChart data={data} />;
    case 'heatmap':
      return <RenderHeatmapChart data={data} />;
    case 'table':
      return <RenderDataTable data={data} />;
    default:
      return <RenderError message="Chart could not be rendered" />;
  }
}
