/**
 * Unit tests for TraceabilityPanel component.
 * Validates: Requirements 3.1, 3.2, 3.4, 3.5, 3.6
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TraceabilityPanel } from './TraceabilityPanel';
import { useSessionStore } from '../store/sessionStore';
import type { CardState, TransparencyData } from '../types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeCard(overrides?: Partial<CardState>): CardState {
  const defaultTransparency: TransparencyData = {
    queryRewrite: 'Show total revenue by region for Q4 2024',
    structuredIntent: {
      query_id: 'q-123',
      query_type: 'aggregation',
      entity_refs: ['revenue', 'region'],
      routing_metadata: { agent: 'sql-gen', confidence: 0.92 },
      timestamp: '2025-01-15T10:30:00Z',
    },
    apiCallSummary: {
      agents: [
        { id: 'sql-gen', dataSources: ['financial_data'], status: 'success' },
        { id: 'cache-agent', dataSources: ['redis'], status: 'timeout' },
      ],
    },
  };

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
      },
    },
    transparencyData: defaultTransparency,
    pinned: false,
    width: '100%',
    createdAt: Date.now(),
    ...overrides,
  };
}

function resetStore(overrides?: Record<string, unknown>) {
  useSessionStore.setState({
    traceabilityPanelVisible: true,
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

describe('TraceabilityPanel', () => {
  beforeEach(() => {
    resetStore();
  });

  describe('Empty state (Requirement 3.6)', () => {
    it('displays empty state when no card is active', () => {
      render(<TraceabilityPanel />);
      expect(
        screen.getByText('Select a visualization to view traceability'),
      ).toBeInTheDocument();
    });

    it('does not render section headings when no card is active', () => {
      render(<TraceabilityPanel />);
      expect(screen.queryByText('Query Rewrite')).not.toBeInTheDocument();
      expect(screen.queryByText('Structured Intent')).not.toBeInTheDocument();
      expect(screen.queryByText('API Call Summary')).not.toBeInTheDocument();
    });
  });

  describe('Active card with full data (Requirement 3.2)', () => {
    beforeEach(() => {
      const card = makeCard();
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });
    });

    it('renders the header', () => {
      render(<TraceabilityPanel />);
      expect(
        screen.getByText('Traceability & Explainability'),
      ).toBeInTheDocument();
    });

    it('renders the query rewrite section with content', () => {
      render(<TraceabilityPanel />);
      expect(screen.getByText('Query Rewrite')).toBeInTheDocument();
      expect(
        screen.getByText('Show total revenue by region for Q4 2024'),
      ).toBeInTheDocument();
    });

    it('renders the structured intent section with formatted JSON', () => {
      render(<TraceabilityPanel />);
      expect(screen.getByText('Structured Intent')).toBeInTheDocument();
      // The JSON should contain key fields
      expect(screen.getByText(/q-123/)).toBeInTheDocument();
      expect(screen.getByText(/aggregation/)).toBeInTheDocument();
    });

    it('renders the API call summary section with agent details', () => {
      render(<TraceabilityPanel />);
      expect(screen.getByText('API Call Summary')).toBeInTheDocument();
      expect(screen.getByText('sql-gen')).toBeInTheDocument();
      expect(screen.getByText('cache-agent')).toBeInTheDocument();
    });

    it('shows status badges for agents', () => {
      render(<TraceabilityPanel />);
      expect(screen.getByText('success')).toBeInTheDocument();
      expect(screen.getByText('timeout')).toBeInTheDocument();
    });

    it('shows data sources for agents', () => {
      render(<TraceabilityPanel />);
      expect(screen.getByText('Sources: financial_data')).toBeInTheDocument();
      expect(screen.getByText('Sources: redis')).toBeInTheDocument();
    });
  });

  describe('Content updates on active card change (Requirement 3.4)', () => {
    it('updates content when active card changes', () => {
      const card1 = makeCard({
        id: 'card-1',
        transparencyData: {
          queryRewrite: 'First card interpretation',
          structuredIntent: null,
          apiCallSummary: null,
        },
      });
      const card2 = makeCard({
        id: 'card-2',
        transparencyData: {
          queryRewrite: 'Second card interpretation',
          structuredIntent: null,
          apiCallSummary: null,
        },
      });

      resetStore({
        cards: { 'card-1': card1, 'card-2': card2 },
        activeCardId: 'card-1',
      });

      const { rerender } = render(<TraceabilityPanel />);
      expect(screen.getByText('First card interpretation')).toBeInTheDocument();

      // Change active card
      useSessionStore.setState({ activeCardId: 'card-2' });
      rerender(<TraceabilityPanel />);
      expect(
        screen.getByText('Second card interpretation'),
      ).toBeInTheDocument();
    });
  });

  describe('Placeholder messages for unavailable data (Requirement 3.5)', () => {
    it('shows placeholder when queryRewrite is null', () => {
      const card = makeCard({
        transparencyData: {
          queryRewrite: null,
          structuredIntent: {
            query_id: 'q-1',
            query_type: 'agg',
            entity_refs: [],
            routing_metadata: {},
            timestamp: '2025-01-01T00:00:00Z',
          },
          apiCallSummary: { agents: [] },
        },
      });
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<TraceabilityPanel />);
      expect(screen.getByText('Query Rewrite')).toBeInTheDocument();
      // The placeholder appears in the first section
      const placeholders = screen.getAllByText('Data could not be retrieved');
      expect(placeholders.length).toBeGreaterThanOrEqual(1);
    });

    it('shows placeholder when structuredIntent is null', () => {
      const card = makeCard({
        transparencyData: {
          queryRewrite: 'Some rewrite',
          structuredIntent: null,
          apiCallSummary: { agents: [] },
        },
      });
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<TraceabilityPanel />);
      expect(screen.getByText('Structured Intent')).toBeInTheDocument();
      const placeholders = screen.getAllByText('Data could not be retrieved');
      expect(placeholders.length).toBeGreaterThanOrEqual(1);
    });

    it('shows placeholder when apiCallSummary is null', () => {
      const card = makeCard({
        transparencyData: {
          queryRewrite: 'Some rewrite',
          structuredIntent: {
            query_id: 'q-1',
            query_type: 'agg',
            entity_refs: [],
            routing_metadata: {},
            timestamp: '2025-01-01T00:00:00Z',
          },
          apiCallSummary: null,
        },
      });
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<TraceabilityPanel />);
      expect(screen.getByText('API Call Summary')).toBeInTheDocument();
      const placeholders = screen.getAllByText('Data could not be retrieved');
      expect(placeholders.length).toBeGreaterThanOrEqual(1);
    });

    it('shows all three placeholders when all data is null', () => {
      const card = makeCard({
        transparencyData: {
          queryRewrite: null,
          structuredIntent: null,
          apiCallSummary: null,
        },
      });
      resetStore({ cards: { 'card-1': card }, activeCardId: 'card-1' });

      render(<TraceabilityPanel />);
      // All three sections should still be rendered with placeholders
      expect(screen.getByText('Query Rewrite')).toBeInTheDocument();
      expect(screen.getByText('Structured Intent')).toBeInTheDocument();
      expect(screen.getByText('API Call Summary')).toBeInTheDocument();
      const placeholders = screen.getAllByText('Data could not be retrieved');
      expect(placeholders).toHaveLength(3);
    });
  });

  describe('Layout and styling (Requirement 3.1)', () => {
    it('renders as an aside with aria-label', () => {
      render(<TraceabilityPanel />);
      const panel = screen.getByRole('complementary', {
        name: /traceability panel/i,
      });
      expect(panel).toBeInTheDocument();
    });

    it('has 360px width class', () => {
      render(<TraceabilityPanel />);
      const panel = screen.getByRole('complementary', {
        name: /traceability panel/i,
      });
      expect(panel).toHaveClass('w-[360px]');
    });

    it('has slide-in-right animation class', () => {
      render(<TraceabilityPanel />);
      const panel = screen.getByRole('complementary', {
        name: /traceability panel/i,
      });
      expect(panel).toHaveClass('animate-slide-in-right');
    });
  });
});
