import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ChartRenderer from './ChartRenderer';
import type { RenderedOutput } from '../types';

// Recharts uses ResizeObserver; mock it for jsdom
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

function makeOutput(overrides: Partial<RenderedOutput> = {}): RenderedOutput {
  return {
    output_type: 'chart',
    chart_type: 'bar',
    chart_data: {
      labels: ['A', 'B', 'C'],
      datasets: [{ label: 'Revenue', data: [100, 200, 300] }],
    },
    description: 'Test chart',
    metadata: {
      query_id: 'q1',
      query_type: 'aggregation',
      columns: [],
    },
    ...overrides,
  };
}

describe('ChartRenderer', () => {
  it('renders a bar chart for chart_type=bar', () => {
    render(<ChartRenderer renderedOutput={makeOutput()} />);
    expect(screen.getByTestId('chart-bar')).toBeInTheDocument();
  });

  it('renders a line chart for chart_type=line', () => {
    const output = makeOutput({ chart_type: 'line' });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-line')).toBeInTheDocument();
  });

  it('renders a scatter chart for chart_type=scatter', () => {
    const output = makeOutput({
      chart_type: 'scatter',
      chart_data: {
        rows: [
          { x: 1, y: 2 },
          { x: 3, y: 4 },
        ],
      },
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-scatter')).toBeInTheDocument();
  });

  it('renders a pie chart for chart_type=pie', () => {
    const output = makeOutput({
      chart_type: 'pie',
      chart_data: {
        labels: ['Cat1', 'Cat2', 'Cat3'],
        datasets: [{ label: 'count', data: [10, 20, 30] }],
      },
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-pie')).toBeInTheDocument();
  });

  it('renders a heatmap (stacked bar) for chart_type=heatmap', () => {
    const output = makeOutput({
      chart_type: 'heatmap',
      chart_data: {
        labels: ['Row1', 'Row2'],
        datasets: [
          { label: 'col1', data: [1, 2] },
          { label: 'col2', data: [3, 4] },
          { label: 'col3', data: [5, 6] },
        ],
      },
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-heatmap')).toBeInTheDocument();
  });

  it('renders a data table for chart_type=table', () => {
    const output = makeOutput({
      chart_type: 'table',
      chart_data: {
        rows: [
          { name: 'Alice', age: 30 },
          { name: 'Bob', age: 25 },
        ],
      },
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByRole('table', { name: 'Data table' })).toBeInTheDocument();
    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('renders text block for output_type=text', () => {
    const output = makeOutput({
      output_type: 'text',
      chart_type: null,
      chart_data: null,
      text_content: 'Hello this is a text response',
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('text-block')).toBeInTheDocument();
    expect(screen.getByText('Hello this is a text response')).toBeInTheDocument();
  });

  it('falls back to description when text_content is null for text output', () => {
    const output = makeOutput({
      output_type: 'text',
      chart_type: null,
      chart_data: null,
      text_content: null,
      description: 'Fallback description text',
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByText('Fallback description text')).toBeInTheDocument();
  });

  it('renders error state when chart_data is null for chart type', () => {
    const output = makeOutput({
      chart_type: 'bar',
      chart_data: null,
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-error')).toBeInTheDocument();
    expect(screen.getByText('Chart could not be rendered')).toBeInTheDocument();
  });

  it('renders error state when chart_data is an empty object (non-parseable)', () => {
    const output = makeOutput({
      chart_type: 'bar',
      chart_data: {},
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-error')).toBeInTheDocument();
  });

  it('renders error state when chart_data normalizes to empty array', () => {
    const output = makeOutput({
      chart_type: 'line',
      chart_data: { rows: [] },
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-error')).toBeInTheDocument();
  });

  it('handles flat array data format', () => {
    const output = makeOutput({
      chart_type: 'bar',
      chart_data: [
        { name: 'Q1', revenue: 100 },
        { name: 'Q2', revenue: 200 },
      ] as unknown as Record<string, unknown>,
    });
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-bar')).toBeInTheDocument();
  });

  it('infers chart type from column metadata when chart_type is absent', () => {
    const output: RenderedOutput = {
      output_type: 'chart',
      chart_data: {
        labels: ['2024-01', '2024-02', '2024-03'],
        datasets: [{ label: 'sales', data: [10, 20, 30] }],
      },
      description: 'Sales over time',
      metadata: {
        query_id: 'q2',
        query_type: 'trend',
        columns: [
          { name: 'month', type: 'time-series' },
          { name: 'sales', type: 'numeric', min: 10, max: 30 },
        ],
      },
    };
    // Should infer 'line' from time-series + numeric
    render(<ChartRenderer renderedOutput={output} />);
    expect(screen.getByTestId('chart-line')).toBeInTheDocument();
  });
});
