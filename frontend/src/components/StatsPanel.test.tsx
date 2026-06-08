/**
 * Unit tests for StatsPanel component.
 * Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { StatsPanel } from './StatsPanel';
import { useSessionStore } from '../store/sessionStore';
import type { CardState, ColumnMeta } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCard(columns: ColumnMeta[], latencyMs?: number): CardState {
  return {
    id: 'card-1',
    query: 'show revenue by region',
    renderedOutput: {
      output_type: 'chart',
      chart_type: 'bar',
      chart_data: { labels: ['A'], datasets: [] },
      description: 'Revenue by region',
      metadata: {
        query_id: 'q-123',
        query_type: 'aggregation',
        latency_ms: latencyMs,
        columns,
      },
    },
    transparencyData: {
      queryRewrite: null,
      structuredIntent: null,
      apiCallSummary: null,
    },
    pinned: false,
    width: '100%',
    createdAt: Date.now(),
  };
}

function resetStore(overrides?: Record<string, unknown>) {
  useSessionStore.setState({
    traceabilityPanelVisible: false,
    sidebarCollapsed: false,
    savedPrompts: [],
    chatHistory: [],
    chatThread: [],
    cards: {},
    activeCardId: null,
    loading: false,
    statsPanelCollapsed: false,
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StatsPanel', () => {
  beforeEach(() => {
    resetStore();
  });

  describe('Empty state: no active card (Requirement 7.8)', () => {
    it('displays empty state when no card is active', () => {
      render(<StatsPanel />);
      expect(
        screen.getByText('Select a card to view statistics'),
      ).toBeInTheDocument();
    });

    it('renders as an aside with aria-label', () => {
      render(<StatsPanel />);
      const panel = screen.getByRole('complementary', {
        name: /stats panel/i,
      });
      expect(panel).toBeInTheDocument();
    });
  });

  describe('Empty state: no columns available (Requirement 7.7)', () => {
    it('displays no-columns message when columns array is empty', () => {
      const card = makeCard([], 250);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(
        screen.getByText('No column statistics available'),
      ).toBeInTheDocument();
    });

    it('displays no-columns message when columns is undefined', () => {
      const card: CardState = {
        id: 'card-1',
        query: 'test',
        renderedOutput: {
          output_type: 'chart',
          chart_type: 'bar',
          chart_data: {},
          description: 'test',
          metadata: {
            query_id: 'q-1',
            query_type: 'agg',
          },
        },
        transparencyData: {
          queryRewrite: null,
          structuredIntent: null,
          apiCallSummary: null,
        },
        pinned: false,
        width: '100%',
        createdAt: Date.now(),
      };
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(
        screen.getByText('No column statistics available'),
      ).toBeInTheDocument();
    });
  });

  describe('Latency badge (Requirement 7.6)', () => {
    it('displays latency badge with correct format', () => {
      const card = makeCard(
        [{ name: 'revenue', type: 'numeric', row_count: 100, null_percentage: 0 }],
        2340,
      );
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('↯ 2340ms')).toBeInTheDocument();
    });

    it('does not display latency badge when latency_ms is absent', () => {
      const card = makeCard(
        [{ name: 'revenue', type: 'numeric', row_count: 100, null_percentage: 0 }],
        undefined,
      );
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.queryByText(/↯/)).not.toBeInTheDocument();
    });
  });

  describe('Common stats: row_count and null_percentage (Requirement 7.2)', () => {
    it('displays row_count for all column types', () => {
      const card = makeCard([
        { name: 'col1', type: 'numeric', row_count: 1500, null_percentage: 2.5 },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('1,500')).toBeInTheDocument();
    });

    it('displays null_percentage rounded to 1 decimal place', () => {
      const card = makeCard([
        { name: 'col1', type: 'numeric', row_count: 100, null_percentage: 12.567 },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('12.6%')).toBeInTheDocument();
    });

    it('displays 0.0% for zero null_percentage', () => {
      const card = makeCard([
        { name: 'col1', type: 'numeric', row_count: 100, null_percentage: 0 },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('0.0%')).toBeInTheDocument();
    });
  });

  describe('Numeric columns (Requirement 7.3)', () => {
    it('displays min, max, mean, median, std_dev with 2 decimal places', () => {
      const card = makeCard([
        {
          name: 'revenue',
          type: 'numeric',
          row_count: 100,
          null_percentage: 0,
          min: 12000.456,
          max: 98000.123,
          mean: 45000.789,
          median: 42000.5,
          std_dev: 18000.333,
        },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('12000.46')).toBeInTheDocument();
      expect(screen.getByText('98000.12')).toBeInTheDocument();
      expect(screen.getByText('45000.79')).toBeInTheDocument();
      expect(screen.getByText('42000.50')).toBeInTheDocument();
      expect(screen.getByText('18000.33')).toBeInTheDocument();
    });

    it('displays type badge as "numeric"', () => {
      const card = makeCard([
        { name: 'revenue', type: 'numeric', row_count: 100, null_percentage: 0 },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('numeric')).toBeInTheDocument();
    });
  });

  describe('Categorical columns (Requirement 7.4)', () => {
    it('displays cardinality for categorical columns', () => {
      const card = makeCard([
        {
          name: 'region',
          type: 'categorical',
          row_count: 100,
          null_percentage: 0,
          cardinality: 8,
        },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('Cardinality')).toBeInTheDocument();
      expect(screen.getByText('8')).toBeInTheDocument();
    });

    it('displays type badge as "categorical"', () => {
      const card = makeCard([
        { name: 'region', type: 'categorical', row_count: 50, null_percentage: 1.5, cardinality: 5 },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('categorical')).toBeInTheDocument();
    });
  });

  describe('Time-series columns (Requirement 7.5)', () => {
    it('displays time_range_start and time_range_end in ISO 8601', () => {
      const card = makeCard([
        {
          name: 'date',
          type: 'time-series',
          row_count: 365,
          null_percentage: 0,
          time_range_start: '2024-01-01T00:00:00Z',
          time_range_end: '2024-12-31T23:59:59Z',
        },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('Start')).toBeInTheDocument();
      expect(screen.getByText('2024-01-01T00:00:00Z')).toBeInTheDocument();
      expect(screen.getByText('End')).toBeInTheDocument();
      expect(screen.getByText('2024-12-31T23:59:59Z')).toBeInTheDocument();
    });

    it('displays type badge as "time-series"', () => {
      const card = makeCard([
        {
          name: 'date',
          type: 'time-series',
          row_count: 100,
          null_percentage: 0,
          time_range_start: '2024-01-01T00:00:00Z',
          time_range_end: '2024-12-31T00:00:00Z',
        },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      expect(screen.getByText('time-series')).toBeInTheDocument();
    });
  });

  describe('Mixed column types (Requirement 7.1)', () => {
    it('renders stats for multiple columns of different types', () => {
      const card = makeCard([
        {
          name: 'revenue',
          type: 'numeric',
          row_count: 100,
          null_percentage: 2.3,
          min: 100,
          max: 5000,
          mean: 2500,
          median: 2400,
          std_dev: 800,
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
          null_percentage: 0,
          time_range_start: '2024-01-01T00:00:00Z',
          time_range_end: '2024-12-31T00:00:00Z',
        },
      ]);
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<StatsPanel />);
      // All column names present
      expect(screen.getByText('revenue')).toBeInTheDocument();
      expect(screen.getByText('region')).toBeInTheDocument();
      expect(screen.getByText('date')).toBeInTheDocument();
      // Type badges
      expect(screen.getByText('numeric')).toBeInTheDocument();
      expect(screen.getByText('categorical')).toBeInTheDocument();
      expect(screen.getByText('time-series')).toBeInTheDocument();
    });
  });

  describe('Collapse/expand toggle', () => {
    it('shows collapsed state with expand button', () => {
      resetStore({ statsPanelCollapsed: true });

      render(<StatsPanel />);
      expect(
        screen.getByRole('button', { name: /expand stats panel/i }),
      ).toBeInTheDocument();
    });

    it('clicking expand button toggles panel open', () => {
      resetStore({ statsPanelCollapsed: true });

      render(<StatsPanel />);
      const expandBtn = screen.getByRole('button', { name: /expand stats panel/i });
      fireEvent.click(expandBtn);

      // After toggle, store should have statsPanelCollapsed = false
      expect(useSessionStore.getState().statsPanelCollapsed).toBe(false);
    });

    it('clicking collapse button toggles panel closed', () => {
      resetStore({ statsPanelCollapsed: false });

      render(<StatsPanel />);
      const collapseBtn = screen.getByRole('button', { name: /collapse stats panel/i });
      fireEvent.click(collapseBtn);

      expect(useSessionStore.getState().statsPanelCollapsed).toBe(true);
    });
  });
});
