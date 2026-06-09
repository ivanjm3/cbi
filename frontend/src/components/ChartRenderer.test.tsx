/**
 * Unit tests for ChartRenderer component.
 * Validates that the renderer correctly handles Chart.js configs, table data,
 * text output, and error states.
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChartRenderer } from './ChartRenderer';
import type { RenderedOutput } from '../types';

// Mock canvas for Chart.js in jsdom
beforeAll(() => {
  HTMLCanvasElement.prototype.getContext = (() => ({
    fillRect: () => {},
    clearRect: () => {},
    getImageData: () => ({ data: [] }),
    putImageData: () => {},
    createImageData: () => [],
    setTransform: () => {},
    drawImage: () => {},
    save: () => {},
    fillText: () => {},
    restore: () => {},
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    closePath: () => {},
    stroke: () => {},
    translate: () => {},
    scale: () => {},
    rotate: () => {},
    arc: () => {},
    fill: () => {},
    measureText: () => ({ width: 0 }),
    transform: () => {},
    rect: () => {},
    clip: () => {},
    createLinearGradient: () => ({ addColorStop: () => {} }),
    createRadialGradient: () => ({ addColorStop: () => {} }),
    createPattern: () => ({}),
  })) as any;
});

function makeRenderedOutput(overrides: Partial<RenderedOutput> = {}): RenderedOutput {
  return {
    output_type: 'chart',
    chart_type: 'bar',
    chart_data: {
      type: 'bar',
      data: {
        labels: ['A', 'B', 'C'],
        datasets: [{ label: 'Values', data: [10, 20, 30] }],
      },
      options: { responsive: true },
    },
    text_content: null,
    description: 'Test chart',
    metadata: { query_id: 'test', query_type: 'lookup' },
    ...overrides,
  };
}

describe('ChartRenderer', () => {
  describe('Chart.js rendering', () => {
    it('renders a canvas element for bar chart config', () => {
      const output = makeRenderedOutput();
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('canvas')).toBeInTheDocument();
    });

    it('renders a canvas element for radar chart config', () => {
      const output = makeRenderedOutput({
        chart_type: 'radar',
        chart_data: {
          type: 'radar',
          data: {
            labels: ['Revenue', 'Orders', 'Returns'],
            datasets: [{ label: 'Electronics', data: [100, 75, 62] }],
          },
          options: { scales: { r: { min: 0, max: 100 } } },
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('canvas')).toBeInTheDocument();
    });

    it('renders a canvas element for doughnut chart config', () => {
      const output = makeRenderedOutput({
        chart_type: 'doughnut',
        chart_data: {
          type: 'doughnut',
          data: {
            labels: ['A', 'B', 'C'],
            datasets: [{ data: [30, 50, 20] }],
          },
          options: { cutout: '72%' },
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('canvas')).toBeInTheDocument();
    });

    it('renders a canvas element for any Chart.js type (polarArea)', () => {
      const output = makeRenderedOutput({
        chart_type: 'polarArea',
        chart_data: {
          type: 'polarArea',
          data: {
            labels: ['X', 'Y', 'Z'],
            datasets: [{ data: [10, 20, 30] }],
          },
          options: {},
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('canvas')).toBeInTheDocument();
    });
  });

  describe('Text output', () => {
    it('renders text content for text output type', () => {
      const output = makeRenderedOutput({
        output_type: 'text',
        chart_data: null,
        text_content: 'No data available.',
        description: 'No data available.',
      });
      render(<ChartRenderer renderedOutput={output} />);
      expect(screen.getByText('No data available.')).toBeInTheDocument();
    });

    it('renders text when chart_data is null but text_content exists', () => {
      const output = makeRenderedOutput({
        output_type: 'chart',
        chart_data: null,
        text_content: 'Summary text here',
        description: 'desc',
      });
      render(<ChartRenderer renderedOutput={output} />);
      expect(screen.getByText('Summary text here')).toBeInTheDocument();
    });
  });

  describe('Table output', () => {
    it('renders a data table for table-type chart_data', () => {
      const output = makeRenderedOutput({
        chart_type: 'table',
        chart_data: {
          type: 'table',
          columns: ['Name', 'Value'],
          rows: [['Item A', 10], ['Item B', 20]],
        },
      });
      const { container } = render(<ChartRenderer renderedOutput={output} />);
      expect(container.querySelector('table')).toBeInTheDocument();
      expect(screen.getByText('Name')).toBeInTheDocument();
      expect(screen.getByText('Item A')).toBeInTheDocument();
    });
  });

  describe('Error handling', () => {
    it('renders error when chart_data has no recognizable format', () => {
      const output = makeRenderedOutput({
        chart_data: { something: 'unknown' } as any,
      });
      render(<ChartRenderer renderedOutput={output} />);
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });
});
