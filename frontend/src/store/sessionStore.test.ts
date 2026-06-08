/**
 * Unit tests for the zustand Session Store.
 *
 * Tests cover all actions, localStorage error handling, and state management logic.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useSessionStore } from './sessionStore';
import type { CardState, RenderedOutput } from '../types';

// ---------------------------------------------------------------------------
// localStorage mock (jsdom doesn't provide one reliably)
// ---------------------------------------------------------------------------

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value; }),
    removeItem: vi.fn((key: string) => { delete store[key]; }),
    clear: vi.fn(() => { store = {}; }),
    get length() { return Object.keys(store).length; },
    key: vi.fn((index: number) => Object.keys(store)[index] ?? null),
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
});

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeRenderedOutput(overrides?: Partial<RenderedOutput>): RenderedOutput {
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
    },
    ...overrides,
  };
}

function makeCard(overrides?: Partial<CardState>): CardState {
  return {
    id: crypto.randomUUID(),
    query: 'test query',
    renderedOutput: makeRenderedOutput(),
    gridPosition: { col: 0, row: 0 },
    gridSize: { colSpan: 1, rowSpan: 1 },
    pinned: false,
    bookmarked: false,
    createdAt: Date.now(),
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  // Reset store to initial state
  useSessionStore.setState({
    cards: [],
    activeCardId: null,
    chatThread: [],
    threads: [],
    bookmarks: [],
    statsPanelCollapsed: false,
    loading: false,
    workspaceName: 'Untitled Workspace',
  });
  localStorageMock.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SessionStore', () => {
  describe('addCard', () => {
    it('places card in first available position on empty canvas', () => {
      const card = makeCard();
      useSessionStore.getState().addCard(card);
      const cards = useSessionStore.getState().cards;
      expect(cards).toHaveLength(1);
      expect(cards[0].gridPosition).toEqual({ col: 0, row: 0 });
    });

    it('places second card in (1,0) position', () => {
      const card1 = makeCard({ gridPosition: { col: 0, row: 0 } });
      const card2 = makeCard({ id: 'card-2' });
      useSessionStore.setState({ cards: [card1] });
      useSessionStore.getState().addCard(card2);
      const cards = useSessionStore.getState().cards;
      expect(cards).toHaveLength(2);
      expect(cards[1].gridPosition).toEqual({ col: 1, row: 0 });
    });

    it('replaces oldest unpinned card when canvas is full', () => {
      const cards: CardState[] = [
        makeCard({ id: 'c1', gridPosition: { col: 0, row: 0 }, createdAt: 1000 }),
        makeCard({ id: 'c2', gridPosition: { col: 1, row: 0 }, createdAt: 2000 }),
        makeCard({ id: 'c3', gridPosition: { col: 0, row: 1 }, createdAt: 3000 }),
        makeCard({ id: 'c4', gridPosition: { col: 1, row: 1 }, createdAt: 4000 }),
        makeCard({ id: 'c5', gridPosition: { col: 0, row: 2 }, createdAt: 5000 }),
        makeCard({ id: 'c6', gridPosition: { col: 1, row: 2 }, createdAt: 6000 }),
      ];
      useSessionStore.setState({ cards });

      const newCard = makeCard({ id: 'new-card' });
      useSessionStore.getState().addCard(newCard);

      const state = useSessionStore.getState();
      expect(state.cards).toHaveLength(6);
      // Oldest unpinned (c1) should be replaced
      expect(state.cards.find((c) => c.id === 'c1')).toBeUndefined();
      // New card takes c1's position
      const addedCard = state.cards.find((c) => c.id === 'new-card');
      expect(addedCard).toBeDefined();
      expect(addedCard!.gridPosition).toEqual({ col: 0, row: 0 });
    });

    it('does not add card when canvas is full and all cards are pinned', () => {
      const cards: CardState[] = Array.from({ length: 6 }, (_, i) =>
        makeCard({
          id: `c${i}`,
          pinned: true,
          gridPosition: {
            col: i % 2,
            row: Math.floor(i / 2),
          },
        }),
      );
      useSessionStore.setState({ cards });

      const newCard = makeCard({ id: 'new-card' });
      useSessionStore.getState().addCard(newCard);

      // Canvas unchanged
      expect(useSessionStore.getState().cards).toHaveLength(6);
      expect(useSessionStore.getState().cards.find((c) => c.id === 'new-card')).toBeUndefined();
    });
  });

  describe('removeCard', () => {
    it('removes card by id', () => {
      const card = makeCard({ id: 'to-remove' });
      useSessionStore.setState({ cards: [card], activeCardId: 'to-remove' });

      useSessionStore.getState().removeCard('to-remove');

      expect(useSessionStore.getState().cards).toHaveLength(0);
      expect(useSessionStore.getState().activeCardId).toBeNull();
    });

    it('keeps activeCardId if different card removed', () => {
      const card1 = makeCard({ id: 'c1' });
      const card2 = makeCard({ id: 'c2' });
      useSessionStore.setState({ cards: [card1, card2], activeCardId: 'c2' });

      useSessionStore.getState().removeCard('c1');

      expect(useSessionStore.getState().activeCardId).toBe('c2');
    });
  });

  describe('moveCard', () => {
    it('updates card position', () => {
      const card = makeCard({ id: 'move-me', gridPosition: { col: 0, row: 0 } });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().moveCard('move-me', { col: 1, row: 2 });

      const moved = useSessionStore.getState().cards[0];
      expect(moved.gridPosition).toEqual({ col: 1, row: 2 });
    });
  });

  describe('resizeCard', () => {
    it('updates card size', () => {
      const card = makeCard({ id: 'resize-me', gridSize: { colSpan: 1, rowSpan: 1 } });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().resizeCard('resize-me', { colSpan: 2, rowSpan: 2 });

      const resized = useSessionStore.getState().cards[0];
      expect(resized.gridSize).toEqual({ colSpan: 2, rowSpan: 2 });
    });
  });

  describe('pinCard / unpinCard', () => {
    it('pins a card', () => {
      const card = makeCard({ id: 'pin-me', pinned: false });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().pinCard('pin-me');

      expect(useSessionStore.getState().cards[0].pinned).toBe(true);
    });

    it('unpins a card', () => {
      const card = makeCard({ id: 'unpin-me', pinned: true });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().unpinCard('unpin-me');

      expect(useSessionStore.getState().cards[0].pinned).toBe(false);
    });
  });

  describe('setActiveCard', () => {
    it('sets active card id', () => {
      useSessionStore.getState().setActiveCard('card-1');
      expect(useSessionStore.getState().activeCardId).toBe('card-1');
    });

    it('clears active card id', () => {
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

  describe('toggleCardBookmark', () => {
    it('toggles a card bookmarked state', () => {
      const card = makeCard({ id: 'bm-card', bookmarked: false });
      useSessionStore.setState({ cards: [card] });

      useSessionStore.getState().toggleCardBookmark('bm-card');
      expect(useSessionStore.getState().cards[0].bookmarked).toBe(true);

      useSessionStore.getState().toggleCardBookmark('bm-card');
      expect(useSessionStore.getState().cards[0].bookmarked).toBe(false);
    });
  });

  describe('saveBookmark / loadBookmark / deleteBookmark', () => {
    it('saves a bookmark with current state', () => {
      const card = makeCard({ id: 'c1' });
      useSessionStore.setState({
        cards: [card],
        chatThread: [{ id: 'm1', role: 'user', content: 'hello', timestamp: 1000 }],
        workspaceName: 'Test WS',
      });

      useSessionStore.getState().saveBookmark('My Bookmark');

      const bookmarks = useSessionStore.getState().bookmarks;
      expect(bookmarks).toHaveLength(1);
      expect(bookmarks[0].name).toBe('My Bookmark');
      expect(bookmarks[0].cards).toHaveLength(1);
      expect(bookmarks[0].chatThread).toHaveLength(1);
      expect(bookmarks[0].workspaceName).toBe('Test WS');
    });

    it('loads a bookmark restoring state', () => {
      const card = makeCard({ id: 'bm-card' });
      const bookmark = {
        id: 'bm-1',
        name: 'Saved',
        savedAt: Date.now(),
        chatThread: [{ id: 'm1', role: 'user' as const, content: 'saved query', timestamp: 1000 }],
        cards: [card],
        workspaceName: 'Restored WS',
      };
      useSessionStore.setState({ bookmarks: [bookmark] });

      useSessionStore.getState().loadBookmark('bm-1');

      const state = useSessionStore.getState();
      expect(state.cards).toHaveLength(1);
      expect(state.cards[0].id).toBe('bm-card');
      expect(state.chatThread).toHaveLength(1);
      expect(state.workspaceName).toBe('Restored WS');
      expect(state.activeCardId).toBeNull();
    });

    it('deletes a bookmark', () => {
      const bookmark = {
        id: 'bm-del',
        name: 'To Delete',
        savedAt: Date.now(),
        chatThread: [],
        cards: [],
        workspaceName: 'test',
      };
      useSessionStore.setState({ bookmarks: [bookmark] });

      useSessionStore.getState().deleteBookmark('bm-del');

      expect(useSessionStore.getState().bookmarks).toHaveLength(0);
    });

    it('truncates bookmark name to 100 characters', () => {
      const longName = 'A'.repeat(200);
      useSessionStore.getState().saveBookmark(longName);

      const bookmarks = useSessionStore.getState().bookmarks;
      expect(bookmarks[0].name.length).toBe(100);
    });

    it('limits bookmarks to 50', () => {
      // Pre-fill 50 bookmarks
      const existing = Array.from({ length: 50 }, (_, i) => ({
        id: `bm-${i}`,
        name: `Bookmark ${i}`,
        savedAt: i * 1000,
        chatThread: [],
        cards: [],
        workspaceName: 'test',
      }));
      useSessionStore.setState({ bookmarks: existing });

      useSessionStore.getState().saveBookmark('New One');

      const bookmarks = useSessionStore.getState().bookmarks;
      expect(bookmarks).toHaveLength(50);
      expect(bookmarks[0].name).toBe('New One');
    });
  });

  describe('startNewChat', () => {
    it('saves current thread as history and clears state', () => {
      const card1 = makeCard({ id: 'c1', pinned: true });
      const card2 = makeCard({ id: 'c2', pinned: false });
      useSessionStore.setState({
        cards: [card1, card2],
        chatThread: [
          { id: 'm1', role: 'user', content: 'first query', timestamp: 1000 },
          { id: 'm2', role: 'system', content: 'response', timestamp: 2000 },
        ],
        activeCardId: 'c2',
      });

      useSessionStore.getState().startNewChat();

      const state = useSessionStore.getState();
      expect(state.chatThread).toHaveLength(0);
      // Only pinned cards remain
      expect(state.cards).toHaveLength(1);
      expect(state.cards[0].id).toBe('c1');
      expect(state.activeCardId).toBeNull();
      // Thread was saved to history
      expect(state.threads).toHaveLength(1);
      expect(state.threads[0].firstMessage).toBe('first query');
      expect(state.threads[0].messageCount).toBe(2);
    });

    it('does not save empty thread to history', () => {
      useSessionStore.setState({ chatThread: [], threads: [] });

      useSessionStore.getState().startNewChat();

      expect(useSessionStore.getState().threads).toHaveLength(0);
    });

    it('limits thread history to 50 entries', () => {
      const existing = Array.from({ length: 50 }, (_, i) => ({
        id: `t-${i}`,
        firstMessage: `Thread ${i}`,
        lastActivity: i * 1000,
        messageCount: 1,
      }));
      useSessionStore.setState({
        threads: existing,
        chatThread: [{ id: 'm1', role: 'user' as const, content: 'latest', timestamp: Date.now() }],
      });

      useSessionStore.getState().startNewChat();

      const threads = useSessionStore.getState().threads;
      expect(threads).toHaveLength(50);
      expect(threads[0].firstMessage).toBe('latest');
    });
  });

  describe('submitQuery', () => {
    it('prevents whitespace-only submissions', async () => {
      const fetchSpy = vi.spyOn(globalThis, 'fetch');

      await useSessionStore.getState().submitQuery('   \t\n  ');

      expect(fetchSpy).not.toHaveBeenCalled();
      expect(useSessionStore.getState().chatThread).toHaveLength(0);
      expect(useSessionStore.getState().loading).toBe(false);
    });

    it('adds user message to chat thread on submit', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(
          JSON.stringify({
            rendered_output: makeRenderedOutput(),
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      );

      await useSessionStore.getState().submitQuery('show revenue');

      const state = useSessionStore.getState();
      const userMsg = state.chatThread.find((m) => m.role === 'user');
      expect(userMsg).toBeDefined();
      expect(userMsg!.content).toBe('show revenue');
    });

    it('creates a new card on successful response', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(
          JSON.stringify({
            rendered_output: makeRenderedOutput({ description: 'Revenue chart' }),
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      );

      await useSessionStore.getState().submitQuery('show revenue');

      const state = useSessionStore.getState();
      expect(state.cards).toHaveLength(1);
      expect(state.cards[0].query).toBe('show revenue');
      expect(state.loading).toBe(false);
      expect(state.activeCardId).toBe(state.cards[0].id);
    });

    it('adds error message on API failure', async () => {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(
          JSON.stringify({ error_message: 'Could not parse' }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
      );

      await useSessionStore.getState().submitQuery('bad query');

      const state = useSessionStore.getState();
      const errorMsg = state.chatThread.find((m) => m.role === 'error');
      expect(errorMsg).toBeDefined();
      expect(errorMsg!.content).toBe('Could not parse');
      expect(state.loading).toBe(false);
    });

    it('adds error message on network failure', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'));

      await useSessionStore.getState().submitQuery('some query');

      const state = useSessionStore.getState();
      const errorMsg = state.chatThread.find((m) => m.role === 'error');
      expect(errorMsg).toBeDefined();
      expect(errorMsg!.content).toBe('Network error');
      expect(state.loading).toBe(false);
    });
  });

  describe('localStorage error handling', () => {
    it('handles corrupted localStorage data gracefully', () => {
      // Write invalid JSON to localStorage
      localStorageMock.setItem('cbi-session', '{invalid json!!!');
      localStorageMock.getItem.mockReturnValueOnce('{invalid json!!!');

      // The store should still initialize without crashing
      const state = useSessionStore.getState();
      expect(state.cards).toBeDefined();
    });

    it('handles localStorage quota exceeded on save', () => {
      const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

      // Mock setItem to throw quota exceeded
      localStorageMock.setItem.mockImplementationOnce(() => {
        const err = new DOMException('Quota exceeded', 'QuotaExceededError');
        throw err;
      });

      // State change should not throw
      useSessionStore.getState().setActiveCard('test-id');

      // Should have logged a warning about quota exceeded
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('quota exceeded'),
      );
    });
  });
});
