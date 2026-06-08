/**
 * Unit tests for ChartRenderer component.
 * Validates rendering of different chart types, text output, error states, and tooltip presence.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChartRenderer } from './ChartRenderer';
import type { RenderedOutput } from '../types';

// Mock ResponsiveContainer since jsdom has no layout
vi.mock('recharts', async () => {
  const actual = await vi.importActual<typeof import('recharts')>('recharts');
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 400, height: 300 }}>
        {children}
      </div>
    ),
  };
});

// Helper to create a minimal RenderedOutput
function makeRenderedOutput(overrides: Partial<RenderedOutput> = {}): RenderedOutput {
  return {
    output_type: 'chart',
    chart_type: 'bar',
    chart_data: {
      labels: ['Q1', 'Q2', 'Q3'],
      datasets: [{ label: 'Revenue', data: [100, 200, 300] }],
    },
    text_content: null,
    description: 'Test chart',
    metadata: {
      query_id: 'test-123',
      query_type: 'aggregation',
      columns: [
        { name: 'quarter', type: 'categorical', cardinality: 3 },
        { name: 'revenue', type: 'numeric', min: 100, max: 300, mean: 200, median: 200 },
      ],
    },
    ...overrides,
  };
}

describe('ChartRenderer', () => {
  describe('chart type rendering', () => {
    it('renders a bar chart when chart_type is bar', () => {
      const output = makeRenderedOutput({ chart_type: 'bar' });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      // Recharts BarChart renders inside ResponsiveContainer
      expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument();
      // Should not show error
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });

    it('renders a line chart when chart_type is line', () => {
      const output = makeRenderedOutput({ chart_type: 'line' });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument();
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });

    it('renders a scatter chart when chart_type is scatter', () => {
      const output = makeRenderedOutput({
        chart_type: 'scatter',
        chart_data: {
          data: [
            { x: 1, y: 2 },
            { x: 3, y: 4 },
            { x: 5, y: 6 },
          ],
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument();
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });

    it('renders a pie chart when chart_type is pie', () => {
      const output = makeRenderedOutput({
        chart_type: 'pie',
        chart_data: {
          labels: ['A', 'B', 'C'],
          datasets: [{ label: 'Share', data: [30, 50, 20] }],
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument();
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });

    it('renders a heatmap when chart_type is heatmap', () => {
      const output = makeRenderedOutput({
        chart_type: 'heatmap',
        chart_data: {
          data: [
            { category: 'A', metric1: 10, metric2: 20, metric3: 30 },
            { category: 'B', metric1: 40, metric2: 50, metric3: 60 },
          ],
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[aria-label="Heatmap chart"]')).toBeInTheDocument();
    });

    it('renders a data table when chart_type is table', () => {
      const output = makeRenderedOutput({
        chart_type: 'table',
        chart_data: {
          data: [
            { name: 'Alice', age: 30 },
            { name: 'Bob', age: 25 },
          ],
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[aria-label="Data table"]')).toBeInTheDocument();
    });
  });

  describe('text output handling', () => {
    it('renders text content when output_type is text', () => {
      const output = makeRenderedOutput({
        output_type: 'text',
        chart_type: null,
        chart_data: null,
        text_content: 'Revenue grew by 15% year-over-year.',
        description: 'Summary analysis',
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[aria-label="Text output"]')).toBeInTheDocument();
      expect(screen.getByText('Revenue grew by 15% year-over-year.')).toBeInTheDocument();
    });

    it('renders description as fallback when text_content is null', () => {
      const output = makeRenderedOutput({
        output_type: 'text',
        chart_type: null,
        chart_data: null,
        text_content: null,
        description: 'A summary of the data',
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[aria-label="Text output"]')).toBeInTheDocument();
      expect(screen.getByText('A summary of the data')).toBeInTheDocument();
    });

    it('renders description separately from text_content when they differ', () => {
      const output = makeRenderedOutput({
        output_type: 'text',
        chart_type: null,
        chart_data: null,
        text_content: 'The main content here.',
        description: 'Brief description of analysis',
      });
      render(<ChartRenderer renderedOutput={output} />);
      expect(screen.getByText('The main content here.')).toBeInTheDocument();
      expect(screen.getByText('Brief description of analysis')).toBeInTheDocument();
    });
  });

  describe('error state handling', () => {
    it('renders error state when chart_data is null', () => {
      const output = makeRenderedOutput({
        chart_type: 'bar',
        chart_data: null,
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[role="alert"]')).toBeInTheDocument();
      expect(screen.getByText('Chart could not be rendered')).toBeInTheDocument();
    });

    it('renders error state when chart_data is undefined', () => {
      const output = makeRenderedOutput({
        chart_type: 'bar',
        chart_data: undefined,
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[role="alert"]')).toBeInTheDocument();
      expect(screen.getByText('Chart could not be rendered')).toBeInTheDocument();
    });

    it('renders error state when chart_data is empty object', () => {
      const output = makeRenderedOutput({
        chart_type: 'bar',
        chart_data: {},
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[role="alert"]')).toBeInTheDocument();
      expect(screen.getByText('Chart could not be rendered')).toBeInTheDocument();
    });

    it('renders error state when extracted data is empty array', () => {
      const output = makeRenderedOutput({
        chart_type: 'bar',
        chart_data: { data: [] },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[role="alert"]')).toBeInTheDocument();
      expect(screen.getByText('Chart could not be rendered')).toBeInTheDocument();
    });
  });

  describe('user chart type override', () => {
    it('respects userRequestedChartType over backend chart_type', () => {
      const output = makeRenderedOutput({
        chart_type: 'bar',
        chart_data: {
          data: [
            { x: 1, y: 2 },
            { x: 3, y: 4 },
          ],
        },
      });
      const { container } = render(
        <ChartRenderer renderedOutput={output} userRequestedChartType="scatter" />
      );
      // Scatter chart renders via ResponsiveContainer
      expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument();
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });

    it('uses backend chart_type when no user override is provided', () => {
      const output = makeRenderedOutput({ chart_type: 'line' });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument();
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });
  });

  describe('data table rendering', () => {
    it('renders column headers and data rows', () => {
      const output = makeRenderedOutput({
        chart_type: 'table',
        chart_data: {
          data: [
            { name: 'Alice', score: 95 },
            { name: 'Bob', score: 87 },
          ],
        },
      });
      render(<ChartRenderer renderedOutput={output} />);
      expect(screen.getByText('name')).toBeInTheDocument();
      expect(screen.getByText('score')).toBeInTheDocument();
      expect(screen.getByText('Alice')).toBeInTheDocument();
      expect(screen.getByText('Bob')).toBeInTheDocument();
      expect(screen.getByText('95')).toBeInTheDocument();
      expect(screen.getByText('87')).toBeInTheDocument();
    });

    it('displays dash for null values in table', () => {
      const output = makeRenderedOutput({
        chart_type: 'table',
        chart_data: {
          data: [
            { name: 'Alice', score: null },
          ],
        },
      });
      render(<ChartRenderer renderedOutput={output} />);
      expect(screen.getByText('—')).toBeInTheDocument();
    });
  });

  describe('heatmap rendering', () => {
    it('renders category labels and numeric values', () => {
      const output = makeRenderedOutput({
        chart_type: 'heatmap',
        chart_data: {
          data: [
            { region: 'North', sales: 100, cost: 40 },
            { region: 'South', sales: 200, cost: 80 },
          ],
        },
      });
      render(<ChartRenderer renderedOutput={output} />);
      expect(screen.getByText('North')).toBeInTheDocument();
      expect(screen.getByText('South')).toBeInTheDocument();
      expect(screen.getByText('region')).toBeInTheDocument();
      expect(screen.getByText('sales')).toBeInTheDocument();
      expect(screen.getByText('cost')).toBeInTheDocument();
    });

    it('applies title attributes for tooltip on heatmap cells', () => {
      const output = makeRenderedOutput({
        chart_type: 'heatmap',
        chart_data: {
          data: [
            { region: 'North', sales: 100 },
          ],
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      const cell = container.querySelector('td[title="sales: 100"]');
      expect(cell).toBeInTheDocument();
    });
  });

  describe('various data formats', () => {
    it('handles Chart.js labels+datasets format', () => {
      const output = makeRenderedOutput({
        chart_type: 'bar',
        chart_data: {
          labels: ['Jan', 'Feb', 'Mar'],
          datasets: [{ label: 'Revenue', data: [10, 20, 30] }],
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument();
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });

    it('handles rows+columns table format', () => {
      const output = makeRenderedOutput({
        chart_type: 'table',
        chart_data: {
          columns: ['name', 'value'],
          rows: [['Alpha', 10], ['Beta', 20]],
        },
      });
      render(<ChartRenderer renderedOutput={output} />);
      expect(screen.getByText('Alpha')).toBeInTheDocument();
      expect(screen.getByText('Beta')).toBeInTheDocument();
    });

    it('handles direct data array format', () => {
      const output = makeRenderedOutput({
        chart_type: 'bar',
        chart_data: {
          data: [
            { category: 'A', amount: 100 },
            { category: 'B', amount: 200 },
          ],
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('[data-testid="responsive-container"]')).toBeInTheDocument();
      expect(container.querySelector('[role="alert"]')).not.toBeInTheDocument();
    });
  });
});
