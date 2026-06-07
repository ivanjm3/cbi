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
} from 'recharts';
import type { RenderedOutput } from '../types';
import { selectChartType } from '../utils/chartSelector';

interface ChartRendererProps {
  renderedOutput: RenderedOutput;
}

/** Default color palette for charts */
const COLORS = [
  '#3b82f6', '#10b981', '#f59e0b', '#ef4444',
  '#8b5cf6', '#06b6d4', '#f97316', '#ec4899',
];

/**
 * Extracts chart data array from the backend chart_data payload.
 * The backend typically sends { labels: string[], datasets: Array<{ label, data }> }
 * or a flat array of records. We normalize to an array of row objects.
 */
function normalizeChartData(
  chartData: Record<string, unknown> | null | undefined,
): Record<string, unknown>[] | null {
  if (!chartData) return null;

  // Already an array of records
  if (Array.isArray(chartData)) {
    return chartData as Record<string, unknown>[];
  }

  // { labels: [...], datasets: [{ label, data: [...] }] } format
  const labels = chartData.labels as string[] | undefined;
  const datasets = chartData.datasets as
    | Array<{ label?: string; data: number[] }>
    | undefined;

  if (labels && datasets) {
    return labels.map((label, idx) => {
      const row: Record<string, unknown> = { name: label };
      datasets.forEach((ds) => {
        const key = ds.label ?? `value_${datasets.indexOf(ds)}`;
        row[key] = ds.data[idx];
      });
      return row;
    });
  }

  // { rows: [...] } format
  if (Array.isArray(chartData.rows)) {
    return chartData.rows as Record<string, unknown>[];
  }

  return null;
}

/** Extracts dataset keys (numeric value columns) from normalized data */
function getDatasetKeys(data: Record<string, unknown>[]): string[] {
  if (data.length === 0) return [];
  const firstRow = data[0];
  return Object.keys(firstRow).filter(
    (key) => key !== 'name' && typeof firstRow[key] === 'number',
  );
}

function BarChartView({ data }: { data: Record<string, unknown>[] }) {
  const keys = getDatasetKeys(data);
  return (
    <div data-testid="chart-bar">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Legend />
          {keys.map((key, idx) => (
            <Bar key={key} dataKey={key} fill={COLORS[idx % COLORS.length]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function LineChartView({ data }: { data: Record<string, unknown>[] }) {
  const keys = getDatasetKeys(data);
  return (
    <div data-testid="chart-line">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Legend />
          {keys.map((key, idx) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={COLORS[idx % COLORS.length]}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ScatterChartView({ data }: { data: Record<string, unknown>[] }) {
  const keys = getDatasetKeys(data);
  const xKey = keys[0] ?? 'x';
  const yKey = keys[1] ?? 'y';

  return (
    <div data-testid="chart-scatter">
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey={xKey} type="number" name={xKey} />
          <YAxis dataKey={yKey} type="number" name={yKey} />
          <Tooltip cursor={{ strokeDasharray: '3 3' }} />
          <Legend />
          <Scatter name="Data" data={data} fill={COLORS[0]} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

function PieChartView({ data }: { data: Record<string, unknown>[] }) {
  const keys = getDatasetKeys(data);
  const valueKey = keys[0] ?? 'value';

  return (
    <div data-testid="chart-pie">
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Tooltip />
          <Legend />
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey="name"
            cx="50%"
            cy="50%"
            outerRadius={100}
            label
          >
            {data.map((_, idx) => (
              <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function HeatmapChartView({ data }: { data: Record<string, unknown>[] }) {
  // Heatmap rendered as a bar chart with multiple grouped series
  // A true heatmap is not natively supported in Recharts, so we use a stacked bar
  const keys = getDatasetKeys(data);
  return (
    <div data-testid="chart-heatmap">
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="name" />
          <YAxis />
          <Tooltip />
          <Legend />
          {keys.map((key, idx) => (
            <Bar
              key={key}
              dataKey={key}
              stackId="heatmap"
              fill={COLORS[idx % COLORS.length]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function DataTableView({ data }: { data: Record<string, unknown>[] }) {
  if (data.length === 0) {
    return <p className="text-gray-500 text-sm p-4">No data available</p>;
  }

  const columns = Object.keys(data[0]);

  return (
    <div className="overflow-auto max-h-[300px]">
      <table className="min-w-full text-sm border-collapse" aria-label="Data table">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200">
            {columns.map((col) => (
              <th
                key={col}
                className="px-3 py-2 text-left font-medium text-gray-700"
                role="columnheader"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className="border-b border-gray-100 hover:bg-gray-50"
            >
              {columns.map((col) => (
                <td key={col} className="px-3 py-2 text-gray-600">
                  {String(row[col] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TextBlockView({ content }: { content: string }) {
  return (
    <div
      className="p-4 prose prose-sm max-w-none"
      data-testid="text-block"
      aria-label="Text output"
    >
      <p className="whitespace-pre-wrap text-gray-800">{content}</p>
    </div>
  );
}

function ErrorState() {
  return (
    <div
      className="p-4 flex items-center justify-center text-red-600 bg-red-50 rounded"
      data-testid="chart-error"
      role="alert"
    >
      <p className="text-sm font-medium">Chart could not be rendered</p>
    </div>
  );
}

/**
 * ChartRenderer selects and renders the appropriate chart type
 * based on the backend response and column metadata.
 */
export default function ChartRenderer({ renderedOutput }: ChartRendererProps) {
  const chartType = selectChartType(renderedOutput);

  // Text-only output
  if (chartType === 'text') {
    const textContent = renderedOutput.text_content ?? renderedOutput.description;
    return <TextBlockView content={textContent} />;
  }

  // Chart types require valid chart_data
  const data = normalizeChartData(renderedOutput.chart_data);

  if (!data || data.length === 0) {
    return <ErrorState />;
  }

  switch (chartType) {
    case 'bar':
      return <BarChartView data={data} />;
    case 'line':
      return <LineChartView data={data} />;
    case 'scatter':
      return <ScatterChartView data={data} />;
    case 'pie':
      return <PieChartView data={data} />;
    case 'heatmap':
      return <HeatmapChartView data={data} />;
    case 'table':
      return <DataTableView data={data} />;
    default:
      return <ErrorState />;
  }
}
