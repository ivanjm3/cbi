/**
 * Unit tests for StatsPanel component.
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StatsPanel } from './StatsPanel';
import { useSessionStore } from '../store/sessionStore';
import type { CardState } from '../types';

function makeCard(overrides: Partial<CardState> = {}): CardState {
  return {
    id: 'card-1',
    query: 'show revenue',
    renderedOutput: {
      output_type: 'chart',
      chart_type: 'bar',
      chart_data: {},
      text_content: null,
      description: 'Revenue data',
      metadata: {
        query_id: 'q1',
        query_type: 'aggregation',
        latency_ms: 245,
        row_count: 100,
        columns: [
          {
            name: 'revenue',
            type: 'numeric',
            row_count: 100,
            null_percentage: 2.5,
            min: 10,
            max: 99000,
            mean: 45000.123,
            median: 42000.789,
            std_dev: 18000.456,
          },
          {
            name: 'region',
            type: 'categorical',
            row_count: 100,
            null_percentage: 0,
            cardinality: 8,
          },
          {
            name: 'date',
            type: 'time-series',
            row_count: 100,
            null_percentage: 1.0,
            time_range_start: '2024-01-01T00:00:00Z',
            time_range_end: '2024-12-31T23:59:59Z',
          },
        ],
      },
    },
    gridPosition: { col: 0, row: 0 },
    gridSize: { colSpan: 1, rowSpan: 1 },
    pinned: false,
    bookmarked: false,
    createdAt: Date.now(),
    ...overrides,
  };
}

describe('StatsPanel', () => {
  beforeEach(() => {
    useSessionStore.setState({
      cards: [],
      activeCardId: null,
    });
  });

  it('renders with aria-label "Stats panel"', () => {
    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    expect(screen.getByLabelText('Stats panel')).toBeInTheDocument();
  });

  it('shows "No card selected" when no active card', () => {
    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    expect(screen.getByText('No card selected')).toBeInTheDocument();
  });

  it('shows "No column statistics available" when active card has no columns', () => {
    const card = makeCard({
      renderedOutput: {
        output_type: 'chart',
        chart_type: 'bar',
        chart_data: {},
        text_content: null,
        description: 'Test',
        metadata: {
          query_id: 'q1',
          query_type: 'aggregation',
          latency_ms: 100,
          row_count: 50,
          columns: [],
        },
      },
    });
    useSessionStore.setState({ cards: [card], activeCardId: 'card-1' });

    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    expect(screen.getByText('No column statistics available')).toBeInTheDocument();
  });

  it('displays latency badge with formatLatency output', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: 'card-1' });

    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    expect(screen.getByText('↯ 245ms')).toBeInTheDocument();
  });

  it('displays row count as formatted integer', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: 'card-1' });

    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    // The top-level row count is inside a div with "Row count:" label
    const rowCountDiv = screen.getByText('Row count:').closest('div');
    expect(rowCountDiv).toHaveTextContent('100');
  });

  it('renders numeric column stats with 2 decimal places', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: 'card-1' });

    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    expect(screen.getByText('45000.12')).toBeInTheDocument();
    expect(screen.getByText('42000.79')).toBeInTheDocument();
    expect(screen.getByText('18000.46')).toBeInTheDocument();
    expect(screen.getByText('10.00')).toBeInTheDocument();
    expect(screen.getByText('99000.00')).toBeInTheDocument();
  });

  it('renders categorical column with cardinality', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: 'card-1' });

    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    expect(screen.getByText('8')).toBeInTheDocument();
  });

  it('renders time-series column with start/end ISO 8601', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: 'card-1' });

    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    expect(screen.getByText('2024-01-01T00:00:00Z')).toBeInTheDocument();
    expect(screen.getByText('2024-12-31T23:59:59Z')).toBeInTheDocument();
  });

  it('renders row_count and null_percentage for all columns', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: 'card-1' });

    render(<StatsPanel collapsed={false} onToggle={() => {}} />);
    // All three columns have row_count and null_percentage
    const nullLabels = screen.getAllByText('Null %');
    expect(nullLabels).toHaveLength(3);
    const rowCountLabels = screen.getAllByText('Row count');
    // 3 column-level + 1 top-level row count label
    expect(rowCountLabels.length).toBeGreaterThanOrEqual(3);
  });

  it('calls onToggle when collapse button is clicked', async () => {
    const user = userEvent.setup();
    let toggled = false;
    render(<StatsPanel collapsed={false} onToggle={() => { toggled = true; }} />);

    await user.click(screen.getByLabelText('Collapse stats panel'));
    expect(toggled).toBe(true);
  });

  it('applies collapsed width when collapsed prop is true', () => {
    render(<StatsPanel collapsed={true} onToggle={() => {}} />);
    const panel = screen.getByLabelText('Stats panel');
    expect(panel).toHaveClass('w-0');
  });

  it('sets aria-hidden when collapsed', () => {
    render(<StatsPanel collapsed={true} onToggle={() => {}} />);
    const panel = screen.getByLabelText('Stats panel');
    expect(panel).toHaveAttribute('aria-hidden', 'true');
  });
});
