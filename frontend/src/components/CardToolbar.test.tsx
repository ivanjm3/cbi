/**
 * Unit tests for CardToolbar component.
 * Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.6, 5.7
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CardToolbar } from './CardToolbar';
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

describe('CardToolbar', () => {
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

  it('renders all 6 toolbar buttons (Requirement 5.1)', () => {
    const card = createMockCard();
    render(<CardToolbar card={card} />);

    expect(screen.getByLabelText('Download PNG')).toBeInTheDocument();
    expect(screen.getByLabelText('Download CSV')).toBeInTheDocument();
    expect(screen.getByLabelText('Pin to canvas')).toBeInTheDocument();
    expect(screen.getByLabelText('Expand fullscreen')).toBeInTheDocument();
    expect(screen.getByLabelText('Save Chat')).toBeInTheDocument();
    expect(screen.getByLabelText('Drag to reorder')).toBeInTheDocument();
  });

  it('renders the toolbar with proper role and label', () => {
    const card = createMockCard();
    render(<CardToolbar card={card} />);

    const toolbar = screen.getByRole('toolbar');
    expect(toolbar).toHaveAttribute(
      'aria-label',
      'Toolbar for card: Show revenue by region',
    );
  });

  it('shows "Unpin card" label when card is pinned (Requirement 5.5)', () => {
    const card = createMockCard({ pinned: true });
    render(<CardToolbar card={card} />);

    const pinBtn = screen.getByLabelText('Unpin card');
    expect(pinBtn).toBeInTheDocument();
    expect(pinBtn).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows "Pin to canvas" label when card is not pinned (Requirement 5.5)', () => {
    const card = createMockCard({ pinned: false });
    render(<CardToolbar card={card} />);

    const pinBtn = screen.getByLabelText('Pin to canvas');
    expect(pinBtn).toBeInTheDocument();
    expect(pinBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('toggles pin state via store when pin button is clicked (Requirement 5.5)', async () => {
    const user = userEvent.setup();
    const card = createMockCard({ id: 'card-pin-test' });
    useSessionStore.setState({ cards: { 'card-pin-test': card } });
    render(<CardToolbar card={card} />);

    await user.click(screen.getByLabelText('Pin to canvas'));

    expect(useSessionStore.getState().cards['card-pin-test'].pinned).toBe(true);
  });

  it('unpins a pinned card when pin button is clicked again (Requirement 5.5)', async () => {
    const user = userEvent.setup();
    const card = createMockCard({ id: 'card-unpin-test', pinned: true });
    useSessionStore.setState({ cards: { 'card-unpin-test': card } });
    render(<CardToolbar card={card} />);

    await user.click(screen.getByLabelText('Unpin card'));

    expect(useSessionStore.getState().cards['card-unpin-test'].pinned).toBe(false);
  });

  it('calls onExpandFullscreen when expand button is clicked', async () => {
    const user = userEvent.setup();
    const card = createMockCard();
    const onExpand = vi.fn();
    render(<CardToolbar card={card} onExpandFullscreen={onExpand} />);

    await user.click(screen.getByLabelText('Expand fullscreen'));

    expect(onExpand).toHaveBeenCalledTimes(1);
  });

  it('saves the current session as a saved chat when Save Chat is clicked (Requirement 5.6)', async () => {
    const user = userEvent.setup();
    const card = createMockCard({ query: 'Test prompt query' });
    useSessionStore.setState({
      chatThread: [{ id: 'msg-1', role: 'user', content: 'Test', timestamp: Date.now() }],
      cards: { 'card-1': card },
    });
    render(<CardToolbar card={card} />);

    await user.click(screen.getByLabelText('Save Chat'));

    const state = useSessionStore.getState();
    expect(state.savedPrompts.length).toBe(1);
    expect(state.savedPrompts[0].name).toBe('Test prompt query');
  });

  it('shows inline error toast when PNG export fails with no chart ref (Requirement 5.7)', async () => {
    const user = userEvent.setup();
    const card = createMockCard();
    render(<CardToolbar card={card} chartRef={{ current: null }} />);

    await user.click(screen.getByLabelText('Download PNG'));

    expect(screen.getByRole('alert')).toHaveTextContent('Export failed');
  });

  it('shows inline error toast when CSV export fails with no data (Requirement 5.7)', async () => {
    const user = userEvent.setup();
    const card = createMockCard();
    card.renderedOutput.chart_data = null;
    render(<CardToolbar card={card} />);

    await user.click(screen.getByLabelText('Download CSV'));

    expect(screen.getByRole('alert')).toHaveTextContent('Export failed: no data available');
  });

  it('drag handle button has the data-drag-handle attribute', () => {
    const card = createMockCard();
    render(<CardToolbar card={card} />);

    const dragHandle = screen.getByLabelText('Drag to reorder');
    expect(dragHandle).toHaveAttribute('data-drag-handle');
  });
});
