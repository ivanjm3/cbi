import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, beforeEach } from 'vitest';
import { StatsPanel } from './StatsPanel';
import { useSessionStore } from '../store/sessionStore';
import type { CardState, RenderedOutput, ColumnMeta } from '../types';

function makeColumn(overrides: Partial<ColumnMeta> & { name: string; type: ColumnMeta['type'] }): ColumnMeta {
  return { ...overrides };
}

function makeCard(overrides: Partial<CardState> = {}): CardState {
  const defaultOutput: RenderedOutput = {
    output_type: 'chart',
    chart_type: 'bar',
    chart_data: {},
    text_content: null,
    description: 'Test chart',
    metadata: {
      query_id: 'q1',
      query_type: 'aggregation',
      latency_ms: 245,
      row_count: 100,
      columns: [
        makeColumn({
          name: 'revenue',
          type: 'numeric',
          row_count: 100,
          null_percentage: 2.5,
          min: 10.123,
          max: 99.876,
          mean: 50.555,
          median: 48.222,
          std_dev: 15.333,
        }),
        makeColumn({
          name: 'region',
          type: 'categorical',
          row_count: 100,
          null_percentage: 0,
          cardinality: 8,
        }),
        makeColumn({
          name: 'date',
          type: 'time-series',
          row_count: 100,
          null_percentage: 1.0,
          time_range_start: '2024-01-01T00:00:00Z',
          time_range_end: '2024-12-31T23:59:59Z',
        }),
      ],
    },
  };

  return {
    id: 'card-1',
    query: 'show revenue by region',
    renderedOutput: defaultOutput,
    gridPosition: { col: 0, row: 0 },
    gridSize: { colSpan: 1, rowSpan: 1 },
    pinned: false,
    createdAt: Date.now(),
    ...overrides,
  };
}

describe('StatsPanel', () => {
  beforeEach(() => {
    useSessionStore.setState({
      cards: [],
      activeCardId: null,
      statsPanelCollapsed: false,
    });
  });

  it('renders empty state when no card is active', () => {
    render(<StatsPanel />);
    expect(
      screen.getByText('No card selected. Click a visualization card to view statistics.'),
    ).toBeInTheDocument();
  });

  it('renders empty state when active card has no columns', () => {
    const card = makeCard({
      renderedOutput: {
        output_type: 'text',
        description: 'Text response',
        metadata: {
          query_id: 'q2',
          query_type: 'text',
          columns: [],
        },
      },
    });
    useSessionStore.setState({ cards: [card], activeCardId: card.id });

    render(<StatsPanel />);
    expect(
      screen.getByText('No column statistics available for this card.'),
    ).toBeInTheDocument();
  });

  it('renders empty state when active card has no columns field', () => {
    const card = makeCard({
      renderedOutput: {
        output_type: 'text',
        description: 'Text response',
        metadata: {
          query_id: 'q2',
          query_type: 'text',
        },
      },
    });
    useSessionStore.setState({ cards: [card], activeCardId: card.id });

    render(<StatsPanel />);
    expect(
      screen.getByText('No column statistics available for this card.'),
    ).toBeInTheDocument();
  });

  it('renders latency badge', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: card.id });

    render(<StatsPanel />);
    expect(screen.getByText('↯ 245ms')).toBeInTheDocument();
  });

  it('renders row_count and null_percentage for all columns', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: card.id });

    render(<StatsPanel />);
    // Row counts
    const rowCountValues = screen.getAllByText('100');
    expect(rowCountValues.length).toBeGreaterThanOrEqual(3);
    // Null percentages
    expect(screen.getByText('2.5%')).toBeInTheDocument();
    expect(screen.getByText('0.0%')).toBeInTheDocument();
    expect(screen.getByText('1.0%')).toBeInTheDocument();
  });

  it('renders numeric stats with 2 decimal places', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: card.id });

    render(<StatsPanel />);
    expect(screen.getByText('10.12')).toBeInTheDocument();
    expect(screen.getByText('99.88')).toBeInTheDocument();
    // 50.555.toFixed(2) produces "50.55" in JavaScript
    expect(screen.getByText('50.55')).toBeInTheDocument();
    expect(screen.getByText('48.22')).toBeInTheDocument();
    expect(screen.getByText('15.33')).toBeInTheDocument();
  });

  it('renders cardinality for categorical columns', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: card.id });

    render(<StatsPanel />);
    expect(screen.getByText('8')).toBeInTheDocument();
  });

  it('renders time_range_start and time_range_end for time-series columns', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: card.id });

    render(<StatsPanel />);
    expect(screen.getByText('2024-01-01T00:00:00Z')).toBeInTheDocument();
    expect(screen.getByText('2024-12-31T23:59:59Z')).toBeInTheDocument();
  });

  it('collapse toggle changes panel state', async () => {
    const user = userEvent.setup();
    render(<StatsPanel />);

    const toggleButton = screen.getByLabelText('Collapse stats panel');
    await user.click(toggleButton);

    expect(useSessionStore.getState().statsPanelCollapsed).toBe(true);
  });

  it('displays column names and types', () => {
    const card = makeCard();
    useSessionStore.setState({ cards: [card], activeCardId: card.id });

    render(<StatsPanel />);
    expect(screen.getByText('revenue')).toBeInTheDocument();
    expect(screen.getByText('region')).toBeInTheDocument();
    expect(screen.getByText('date')).toBeInTheDocument();
    expect(screen.getByText('numeric')).toBeInTheDocument();
    expect(screen.getByText('categorical')).toBeInTheDocument();
    expect(screen.getByText('time-series')).toBeInTheDocument();
  });
});
