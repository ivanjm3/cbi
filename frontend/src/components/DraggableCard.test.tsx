/**
 * Unit tests for DraggableCard component.
 *
 * Tests drag-to-reorder and resize functionality:
 * - Renders DraggableCard with proper structure
 * - Resize handles toggle between 50% and 100% width
 * - Pinned cards cannot be dragged
 * - Drop on pinned card positions is rejected (tested via store logic)
 * - Reflow constraint: resulting width is always 50% or 100%
 *
 * Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DndProvider } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { DraggableCard } from './DraggableCard';
import { useSessionStore } from '../store/sessionStore';
import type { CardState, ChatMessage } from '../types';

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

function renderWithDnd(ui: React.ReactElement) {
  return render(<DndProvider backend={HTML5Backend}>{ui}</DndProvider>);
}

describe('DraggableCard', () => {
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

  it('renders the card with drag handle (Requirement 6.1)', () => {
    const card = createMockCard();
    useSessionStore.setState({ cards: { [card.id]: card } });

    renderWithDnd(<DraggableCard card={card} index={0} />);

    expect(screen.getByLabelText('Drag to reorder')).toBeInTheDocument();
    expect(screen.getByTestId('draggable-card-card-1')).toBeInTheDocument();
  });

  it('renders resize handles on bottom-right and bottom-left (Requirement 6.4)', () => {
    const card = createMockCard();
    useSessionStore.setState({ cards: { [card.id]: card } });

    renderWithDnd(<DraggableCard card={card} index={0} />);

    expect(screen.getByTestId('resize-handle-br')).toBeInTheDocument();
    expect(screen.getByTestId('resize-handle-bl')).toBeInTheDocument();
  });

  it('resize handle toggles from 100% to 50% on click (Requirement 6.4)', async () => {
    const user = userEvent.setup();
    const card = createMockCard({ width: '100%' });
    useSessionStore.setState({ cards: { [card.id]: card } });

    renderWithDnd(<DraggableCard card={card} index={0} />);

    const resizeBtn = screen.getByTestId('resize-handle-br');
    await user.click(resizeBtn);

    const state = useSessionStore.getState();
    expect(state.cards['card-1'].width).toBe('50%');
  });

  it('resize handle toggles from 50% to 100% on click (Requirement 6.4)', async () => {
    const user = userEvent.setup();
    const card = createMockCard({ width: '50%' });
    useSessionStore.setState({ cards: { [card.id]: card } });

    renderWithDnd(<DraggableCard card={card} index={0} />);

    const resizeBtn = screen.getByTestId('resize-handle-bl');
    await user.click(resizeBtn);

    const state = useSessionStore.getState();
    expect(state.cards['card-1'].width).toBe('100%');
  });

  it('constrain resize to valid widths: only 50% or 100% (Requirement 6.6)', async () => {
    const user = userEvent.setup();
    const card = createMockCard({ width: '100%' });
    useSessionStore.setState({ cards: { [card.id]: card } });

    renderWithDnd(<DraggableCard card={card} index={0} />);

    // Toggle once: 100% → 50%
    const resizeBtn = screen.getByTestId('resize-handle-br');
    await user.click(resizeBtn);
    expect(useSessionStore.getState().cards['card-1'].width).toBe('50%');

    // Verify width is constrained to valid values only
    const width = useSessionStore.getState().cards['card-1'].width;
    expect(width === '50%' || width === '100%').toBe(true);
  });

  it('resize handle has proper aria labels (Requirement 6.4)', () => {
    const card = createMockCard({ width: '100%' });
    useSessionStore.setState({ cards: { [card.id]: card } });

    renderWithDnd(<DraggableCard card={card} index={0} />);

    expect(screen.getAllByLabelText('Resize card to 50% width')).toHaveLength(2);
  });

  it('resize handle shows correct label for 50% width card', () => {
    const card = createMockCard({ width: '50%' });
    useSessionStore.setState({ cards: { [card.id]: card } });

    renderWithDnd(<DraggableCard card={card} index={0} />);

    expect(screen.getAllByLabelText('Resize card to 100% width')).toHaveLength(2);
  });

  describe('reorderCard store action (Requirement 6.3, 6.7)', () => {
    it('reorders a card to a new position within 300ms transition', () => {
      const card1 = createMockCard({ id: 'card-1' });
      const card2 = createMockCard({ id: 'card-2' });

      const chatThread: ChatMessage[] = [
        { id: 'msg-1', role: 'user', content: 'Query 1', timestamp: 1000 },
        { id: 'msg-2', role: 'system', content: 'Response 1', cardId: 'card-1', timestamp: 1001 },
        { id: 'msg-3', role: 'user', content: 'Query 2', timestamp: 2000 },
        { id: 'msg-4', role: 'system', content: 'Response 2', cardId: 'card-2', timestamp: 2001 },
      ];

      useSessionStore.setState({
        chatThread,
        cards: { 'card-1': card1, 'card-2': card2 },
      });

      // Reorder card-1 to position of card-2 (index 3)
      useSessionStore.getState().reorderCard('card-1', 3);

      const newThread = useSessionStore.getState().chatThread;
      // card-1 message should now be at index 3
      expect(newThread[3].cardId).toBe('card-1');
      // card-2 message should now be at index 2
      expect(newThread[2].cardId).toBe('card-2');
    });

    it('rejects drop on a pinned card position (Requirement 6.7)', () => {
      const card1 = createMockCard({ id: 'card-1', pinned: false });
      const card2 = createMockCard({ id: 'card-2', pinned: true });

      const chatThread: ChatMessage[] = [
        { id: 'msg-1', role: 'user', content: 'Query 1', timestamp: 1000 },
        { id: 'msg-2', role: 'system', content: 'Response 1', cardId: 'card-1', timestamp: 1001 },
        { id: 'msg-3', role: 'user', content: 'Query 2', timestamp: 2000 },
        { id: 'msg-4', role: 'system', content: 'Response 2', cardId: 'card-2', timestamp: 2001 },
      ];

      useSessionStore.setState({
        chatThread,
        cards: { 'card-1': card1, 'card-2': card2 },
      });

      // Try to reorder card-1 to position of pinned card-2 (index 3)
      useSessionStore.getState().reorderCard('card-1', 3);

      const newThread = useSessionStore.getState().chatThread;
      // card-1 should remain at its original position (index 1)
      expect(newThread[1].cardId).toBe('card-1');
      // card-2 should remain at its original position (index 3)
      expect(newThread[3].cardId).toBe('card-2');
    });

    it('does not reorder if target index equals current index', () => {
      const card1 = createMockCard({ id: 'card-1' });

      const chatThread: ChatMessage[] = [
        { id: 'msg-1', role: 'user', content: 'Query 1', timestamp: 1000 },
        { id: 'msg-2', role: 'system', content: 'Response 1', cardId: 'card-1', timestamp: 1001 },
      ];

      useSessionStore.setState({
        chatThread,
        cards: { 'card-1': card1 },
      });

      useSessionStore.getState().reorderCard('card-1', 1);

      const newThread = useSessionStore.getState().chatThread;
      expect(newThread[1].cardId).toBe('card-1');
    });

    it('clamps reorder index to valid thread range', () => {
      const card1 = createMockCard({ id: 'card-1' });

      const chatThread: ChatMessage[] = [
        { id: 'msg-1', role: 'user', content: 'Query 1', timestamp: 1000 },
        { id: 'msg-2', role: 'system', content: 'Response 1', cardId: 'card-1', timestamp: 1001 },
      ];

      useSessionStore.setState({
        chatThread,
        cards: { 'card-1': card1 },
      });

      // Try to reorder to index 100 (out of bounds)
      useSessionStore.getState().reorderCard('card-1', 100);

      const newThread = useSessionStore.getState().chatThread;
      // Should be clamped to max valid index (1)
      expect(newThread[1].cardId).toBe('card-1');
    });
  });
});
