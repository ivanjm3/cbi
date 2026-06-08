/**
 * Unit tests for VisualizationCard component.
 * Validates: Requirements 2.6, 4.1, 5.5, 11.3
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { VisualizationCard } from './VisualizationCard';
import { useSessionStore } from '../store/sessionStore';
import type { CardState } from '../types';

function createMockCard(overrides: Partial<CardState> = {}): CardState {
  return {
    id: 'card-1',
    query: 'Show revenue by region',
    renderedOutput: {
      output_type: 'chart',
      chart_type: 'bar',
      chart_data: {
        labels: ['North', 'South', 'East'],
        datasets: [{ label: 'Revenue', data: [100, 200, 150] }],
      },
      description: 'Revenue breakdown by region',
      metadata: {
        query_id: 'q-1',
        query_type: 'aggregation',
        latency_ms: 250,
        row_count: 3,
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
    ...overrides,
  };
}

describe('VisualizationCard', () => {
  beforeEach(() => {
    useSessionStore.setState({
      chatThread: [],
      cards: {},
      activeCardId: null,
      chatHistory: [],
      savedPrompts: [],
      sidebarCollapsed: false,
      traceabilityPanelVisible: false,
      statsPanelCollapsed: false,
      loading: false,
    });
  });

  it('renders with article role and accessible label (Requirement 2.6)', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    const article = screen.getByRole('article', {
      name: /visualization card: show revenue by region/i,
    });
    expect(article).toBeInTheDocument();
  });

  it('sets active card in store on click (Requirement 2.6)', async () => {
    const user = userEvent.setup();
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    const article = screen.getByRole('article');
    await user.click(article);

    expect(useSessionStore.getState().activeCardId).toBe('card-1');
  });

  it('sets active card in store on focus (Requirement 2.6)', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    const article = screen.getByRole('article');
    article.focus();

    expect(useSessionStore.getState().activeCardId).toBe('card-1');
  });

  it('shows pinned indicator when card is pinned (Requirement 5.5)', () => {
    const card = createMockCard({ pinned: true });
    render(<VisualizationCard card={card} />);

    expect(screen.getByLabelText('Card is pinned')).toBeInTheDocument();
    expect(screen.getByText('Pinned')).toBeInTheDocument();
  });

  it('does not show pinned indicator when card is not pinned', () => {
    const card = createMockCard({ pinned: false });
    render(<VisualizationCard card={card} />);

    expect(screen.queryByLabelText('Card is pinned')).not.toBeInTheDocument();
  });

  it('renders at 100% width when card width is 100%', () => {
    const card = createMockCard({ width: '100%' });
    const { container } = render(<VisualizationCard card={card} />);

    const cardEl = container.firstChild as HTMLElement;
    expect(cardEl.style.width).toBe('100%');
  });

  it('renders at 50% width when card width is 50%', () => {
    const card = createMockCard({ width: '50%' });
    const { container } = render(<VisualizationCard card={card} />);

    const cardEl = container.firstChild as HTMLElement;
    expect(cardEl.style.width).toBe('50%');
  });

  it('applies active styling when card is the active card (Requirement 11.3)', () => {
    const card = createMockCard();
    useSessionStore.setState({ activeCardId: 'card-1' });
    render(<VisualizationCard card={card} />);

    const article = screen.getByRole('article');
    expect(article).toHaveAttribute('aria-selected', 'true');
  });

  it('renders the CardToolbar (Requirement 5.1)', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    const toolbar = screen.getByRole('toolbar');
    expect(toolbar).toBeInTheDocument();
  });

  it('is keyboard accessible with tabIndex 0', () => {
    const card = createMockCard();
    render(<VisualizationCard card={card} />);

    const article = screen.getByRole('article');
    expect(article).toHaveAttribute('tabindex', '0');
  });
});
