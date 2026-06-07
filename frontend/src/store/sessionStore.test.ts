import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useSessionStore } from './sessionStore';
import type { CardState, RenderedOutput } from '../types';

// Helper to create a mock RenderedOutput
function mockRenderedOutput(overrides?: Partial<RenderedOutput>): RenderedOutput {
  return {
    output_type: 'chart',
    chart_type: 'bar',
    chart_data: { labels: ['A', 'B'], datasets: [{ data: [1, 2] }] },
    text_content: null,
    description: 'Test chart',
    metadata: {
      query_id: 'test-query-id',
      query_type: 'aggregation',
      latency_ms: 100,
      row_count: 2,
      columns: [],
    },
    ...overrides,
  };
}

// Helper to create a mock CardState
function mockCard(overrides?: Partial<CardState>): CardState {
  return {
    id: crypto.randomUUID(),
    query: 'test query',
    renderedOutput: mockRenderedOutput(),
    gridPosition: { col: 0, row: 0 },
    gridSize: { colSpan: 1, rowSpan: 1 },
    pinned: false,
    createdAt: Date.now(),
    ...overrides,
  };
}

describe('sessionStore', () => {
  beforeEach(() => {
    // Reset store to initial state before each test
    useSessionStore.setState({
      cards: [],
      activeCardId: null,
      chatThread: [],
      threads: [],
      bookmarks: [],
      statsPanelCollapsed: false,
      loading: false,
      canvasFullNotification: false,
    });
    localStorage.clear();
  });

  describe('addCard', () => {
    it('adds a card to the first available position', () => {
      const card = mockCard({ id: 'card-1' });
      useSessionStore.getState().addCard(card);

      const state = useSessionStore.getState();
      expect(state.cards).toHaveLength(1);
      expect(state.cards[0].gridPosition).toEqual({ col: 0, row: 0 });
    });

    it('places cards in LTR-TTB order', () => {
      const card1 = mockCard({ id: 'card-1' });
      const card2 = mockCard({ id: 'card-2' });
      const card3 = mockCard({ id: 'card-3' });

      useSessionStore.getState().addCard(card1);
      useSessionStore.getState().addCard(card2);
      useSessionStore.getState().addCard(card3);

      const state = useSessionStore.getState();
      expect(state.cards[0].gridPosition).toEqual({ col: 0, row: 0 });
      expect(state.cards[1].gridPosition).toEqual({ col: 1, row: 0 });
      expect(state.cards[2].gridPosition).toEqual({ col: 0, row: 1 });
    });

    it('replaces oldest unpinned card when canvas is full', () => {
      // Fill canvas with 6 cards
      const cards: CardState[] = [];
      const positions = [
        { col: 0, row: 0 },
        { col: 1, row: 0 },
        { col: 0, row: 1 },
        { col: 1, row: 1 },
        { col: 0, row: 2 },
        { col: 1, row: 2 },
      ];

      for (let i = 0; i < 6; i++) {
        cards.push(
          mockCard({
            id: `card-${i}`,
            gridPosition: positions[i],
            pinned: false,
            createdAt: 1000 + i * 100,
          }),
        );
      }

      useSessionStore.setState({ cards });

      const newCard = mockCard({ id: 'new-card', createdAt: 9999 });
      useSessionStore.getState().addCard(newCard);

      const state = useSessionStore.getState();
      // Should have replaced card-0 (oldest unpinned)
      expect(state.cards.find((c) => c.id === 'card-0')).toBeUndefined();
      expect(state.cards.find((c) => c.id === 'new-card')).toBeDefined();
      expect(state.cards).toHaveLength(6);
    });

    it('sets canvasFullNotification when all cards are pinned on full canvas', () => {
      const positions = [
        { col: 0, row: 0 },
        { col: 1, row: 0 },
        { col: 0, row: 1 },
        { col: 1, row: 1 },
        { col: 0, row: 2 },
        { col: 1, row: 2 },
      ];
      const cards = positions.map((pos, i) =>
        mockCard({ id: `card-${i}`, gridPosition: pos, pinned: true }),
      );

      useSessionStore.setState({ cards });

      const newCard = mockCard({ id: 'new-card' });
      useSessionStore.getState().addCard(newCard);

      const state = useSessionStore.getState();
      expect(state.canvasFullNotification).toBe(true);
      expect(state.cards).toHaveLength(6); // New card NOT added
    });
  });

  describe('removeCard', () => {
    it('removes a card by id', () => {
      const card = mockCard({ id: 'card-1' });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().removeCard('card-1');
      expect(useSessionStore.getState().cards).toHaveLength(0);
    });

    it('clears activeCardId if removed card was active', () => {
      const card = mockCard({ id: 'card-1' });
      useSessionStore.setState({ cards: [card], activeCardId: 'card-1' });

      useSessionStore.getState().removeCard('card-1');
      expect(useSessionStore.getState().activeCardId).toBeNull();
    });
  });

  describe('moveCard', () => {
    it('updates the grid position of a card', () => {
      const card = mockCard({ id: 'card-1', gridPosition: { col: 0, row: 0 } });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().moveCard('card-1', { col: 1, row: 2 });

      const state = useSessionStore.getState();
      expect(state.cards[0].gridPosition).toEqual({ col: 1, row: 2 });
    });
  });

  describe('resizeCard', () => {
    it('updates the grid size of a card', () => {
      const card = mockCard({ id: 'card-1', gridSize: { colSpan: 1, rowSpan: 1 } });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().resizeCard('card-1', { colSpan: 2, rowSpan: 2 });

      const state = useSessionStore.getState();
      expect(state.cards[0].gridSize).toEqual({ colSpan: 2, rowSpan: 2 });
    });
  });

  describe('pinCard / unpinCard', () => {
    it('pins a card', () => {
      const card = mockCard({ id: 'card-1', pinned: false });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().pinCard('card-1');
      expect(useSessionStore.getState().cards[0].pinned).toBe(true);
    });

    it('unpins a card', () => {
      const card = mockCard({ id: 'card-1', pinned: true });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().unpinCard('card-1');
      expect(useSessionStore.getState().cards[0].pinned).toBe(false);
    });
  });

  describe('setActiveCard', () => {
    it('sets the active card id', () => {
      useSessionStore.getState().setActiveCard('card-1');
      expect(useSessionStore.getState().activeCardId).toBe('card-1');
    });

    it('clears the active card id with null', () => {
      useSessionStore.setState({ activeCardId: 'card-1' });
      useSessionStore.getState().setActiveCard(null);
      expect(useSessionStore.getState().activeCardId).toBeNull();
    });
  });

  describe('toggleStatsPanel', () => {
    it('toggles stats panel collapsed state', () => {
      expect(useSessionStore.getState().statsPanelCollapsed).toBe(false);
      useSessionStore.getState().toggleStatsPanel();
      expect(useSessionStore.getState().statsPanelCollapsed).toBe(true);
      useSessionStore.getState().toggleStatsPanel();
      expect(useSessionStore.getState().statsPanelCollapsed).toBe(false);
    });
  });

  describe('bookmarks', () => {
    it('saves a bookmark with current state', () => {
      const card = mockCard({ id: 'card-1' });
      useSessionStore.setState({
        cards: [card],
        chatThread: [
          { id: 'msg-1', role: 'user', content: 'test', timestamp: Date.now() },
        ],
      });

      useSessionStore.getState().saveBookmark('My Bookmark');

      const state = useSessionStore.getState();
      expect(state.bookmarks).toHaveLength(1);
      expect(state.bookmarks[0].name).toBe('My Bookmark');
      expect(state.bookmarks[0].cards).toHaveLength(1);
      expect(state.bookmarks[0].chatThread).toHaveLength(1);
    });

    it('limits bookmark name to 100 characters', () => {
      const longName = 'A'.repeat(150);
      useSessionStore.getState().saveBookmark(longName);

      const state = useSessionStore.getState();
      expect(state.bookmarks[0].name).toHaveLength(100);
    });

    it('limits bookmarks to 50', () => {
      for (let i = 0; i < 55; i++) {
        useSessionStore.getState().saveBookmark(`Bookmark ${i}`);
      }
      expect(useSessionStore.getState().bookmarks).toHaveLength(50);
    });

    it('loads a bookmark restoring cards and chat', () => {
      const card = mockCard({ id: 'saved-card' });
      const chatMsg = { id: 'msg-1', role: 'user' as const, content: 'saved', timestamp: 1000 };

      useSessionStore.setState({
        bookmarks: [
          {
            id: 'bm-1',
            name: 'Saved Session',
            savedAt: Date.now(),
            chatThread: [chatMsg],
            cards: [card],
          },
        ],
        cards: [],
        chatThread: [],
      });

      useSessionStore.getState().loadBookmark('bm-1');

      const state = useSessionStore.getState();
      expect(state.cards).toHaveLength(1);
      expect(state.cards[0].id).toBe('saved-card');
      expect(state.chatThread).toHaveLength(1);
      expect(state.chatThread[0].content).toBe('saved');
    });

    it('deletes a bookmark by id', () => {
      useSessionStore.setState({
        bookmarks: [
          { id: 'bm-1', name: 'A', savedAt: 1, chatThread: [], cards: [] },
          { id: 'bm-2', name: 'B', savedAt: 2, chatThread: [], cards: [] },
        ],
      });

      useSessionStore.getState().deleteBookmark('bm-1');

      const state = useSessionStore.getState();
      expect(state.bookmarks).toHaveLength(1);
      expect(state.bookmarks[0].id).toBe('bm-2');
    });
  });

  describe('startNewChat', () => {
    it('clears cards and chat thread', () => {
      useSessionStore.setState({
        cards: [mockCard()],
        chatThread: [
          { id: 'msg-1', role: 'user', content: 'hello', timestamp: Date.now() },
        ],
      });

      useSessionStore.getState().startNewChat();

      const state = useSessionStore.getState();
      expect(state.cards).toHaveLength(0);
      expect(state.chatThread).toHaveLength(0);
    });

    it('saves current thread to threads list', () => {
      useSessionStore.setState({
        chatThread: [
          { id: 'msg-1', role: 'user', content: 'first query', timestamp: Date.now() },
          { id: 'msg-2', role: 'system', content: 'response', timestamp: Date.now() },
        ],
        threads: [],
      });

      useSessionStore.getState().startNewChat();

      const state = useSessionStore.getState();
      expect(state.threads).toHaveLength(1);
      expect(state.threads[0].firstMessage).toBe('first query');
      expect(state.threads[0].messageCount).toBe(2);
    });
  });

  describe('submitQuery', () => {
    it('does nothing for whitespace-only input', async () => {
      await useSessionStore.getState().submitQuery('   ');

      const state = useSessionStore.getState();
      expect(state.chatThread).toHaveLength(0);
      expect(state.loading).toBe(false);
    });

    it('adds user message and sets loading on submit', async () => {
      // Mock queryBackend to never resolve during this test
      vi.mock('../api/queryApi', () => ({
        queryBackend: () =>
          new Promise(() => {
            /* never resolves */
          }),
      }));

      // We'll test the synchronous part by checking immediately
      const promise = useSessionStore.getState().submitQuery('test query');

      // Wait a tick for the state to update
      await new Promise((r) => setTimeout(r, 10));

      const state = useSessionStore.getState();
      expect(state.chatThread.length).toBeGreaterThanOrEqual(1);
      expect(state.chatThread[0].role).toBe('user');
      expect(state.chatThread[0].content).toBe('test query');

      // Clean up - unblock the mock
      vi.restoreAllMocks();
      // The promise will hang but test will end
      void promise;
    });
  });

  describe('localStorage error handling', () => {
    it('handles corrupted localStorage data gracefully', () => {
      localStorage.setItem('cbi-session', 'not valid json {{{');

      // The store should still initialize properly
      // Re-create store state to trigger hydration
      const state = useSessionStore.getState();
      expect(state.cards).toBeDefined();
      expect(Array.isArray(state.cards)).toBe(true);
    });

    it('handles quota exceeded without losing in-memory state', () => {
      const card = mockCard({ id: 'card-1' });
      useSessionStore.setState({ cards: [card] });

      // Mock localStorage.setItem to throw QuotaExceededError
      const originalSetItem = localStorage.setItem.bind(localStorage);
      const error = new DOMException('quota exceeded', 'QuotaExceededError');
      vi.spyOn(localStorage, 'setItem').mockImplementation(() => {
        throw error;
      });

      // Trigger a state change that would persist
      useSessionStore.getState().pinCard('card-1');

      // In-memory state should still be correct
      const state = useSessionStore.getState();
      expect(state.cards[0].pinned).toBe(true);

      // Restore
      vi.spyOn(localStorage, 'setItem').mockImplementation(originalSetItem);
    });
  });
});
