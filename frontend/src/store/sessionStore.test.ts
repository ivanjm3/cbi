/**
 * Unit tests for Saved Prompt save/load/delete logic in the session store.
 *
 * Validates: Requirements 8.1, 8.3, 8.4, 8.5, 8.6
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useSessionStore } from './sessionStore';
import type { CardState, ChatMessage, SavedPrompt } from '../types';

// ---------------------------------------------------------------------------
// localStorage mock (jsdom may not provide it in all node versions)
// ---------------------------------------------------------------------------

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
    get length() { return Object.keys(store).length; },
    key: (index: number) => Object.keys(store)[index] ?? null,
  };
})();

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock, writable: true });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeUserMessage(content = 'test query'): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'user',
    content,
    timestamp: Date.now(),
  };
}

function makeSystemMessage(cardId: string): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'system',
    content: 'Result',
    cardId,
    timestamp: Date.now(),
  };
}

function makeCard(overrides: Partial<CardState> = {}): CardState {
  const id = overrides.id ?? crypto.randomUUID();
  return {
    id,
    query: 'test query',
    renderedOutput: {
      output_type: 'chart',
      chart_type: 'bar',
      chart_data: { labels: ['a', 'b'], datasets: [{ data: [1, 2] }] },
      description: 'Test chart',
      metadata: {
        query_id: crypto.randomUUID(),
        query_type: 'aggregation',
        latency_ms: 200,
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Session Store – Saved Prompts', () => {
  beforeEach(() => {
    // Clear localStorage mock
    localStorageMock.clear();
    // Reset store to clean state
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
      storageError: null,
    });
  });

  afterEach(() => {
    localStorageMock.clear();
  });

  describe('saveSavedPrompt (Requirement 8.1)', () => {
    it('serializes current state into a SavedPrompt with given name', () => {
      const card = makeCard();
      const userMsg = makeUserMessage('show revenue');
      const sysMsg = makeSystemMessage(card.id);

      useSessionStore.setState({
        chatThread: [userMsg, sysMsg],
        cards: { [card.id]: card },
      });

      useSessionStore.getState().saveSavedPrompt('Revenue Analysis');

      const { savedPrompts } = useSessionStore.getState();
      expect(savedPrompts).toHaveLength(1);
      expect(savedPrompts[0].name).toBe('Revenue Analysis');
      expect(savedPrompts[0].chatThread).toHaveLength(2);
      expect(savedPrompts[0].cards).toHaveLength(1);
      expect(savedPrompts[0].cards[0].id).toBe(card.id);
      expect(savedPrompts[0].savedAt).toBeGreaterThan(0);
      expect(savedPrompts[0].id).toBeTruthy();
    });

    it('truncates name to 100 characters', () => {
      const longName = 'A'.repeat(150);
      useSessionStore.getState().saveSavedPrompt(longName);

      const { savedPrompts } = useSessionStore.getState();
      expect(savedPrompts[0].name).toHaveLength(100);
    });

    it('limits saved prompts to 50 entries', () => {
      // Add 50 prompts
      for (let i = 0; i < 50; i++) {
        useSessionStore.getState().saveSavedPrompt(`Prompt ${i}`);
      }
      expect(useSessionStore.getState().savedPrompts).toHaveLength(50);

      // Adding one more should keep at 50
      useSessionStore.getState().saveSavedPrompt('Prompt 51');
      const { savedPrompts } = useSessionStore.getState();
      expect(savedPrompts).toHaveLength(50);
      // Most recent is first
      expect(savedPrompts[0].name).toBe('Prompt 51');
    });

    it('persists to localStorage under cbi-saved-prompts key', () => {
      useSessionStore.getState().saveSavedPrompt('Persisted');

      const raw = localStorageMock.getItem('cbi-saved-prompts');
      expect(raw).not.toBeNull();
      const parsed = JSON.parse(raw!);
      expect(parsed).toHaveLength(1);
      expect(parsed[0].name).toBe('Persisted');
    });

    it('preserves pin state in saved cards', () => {
      const card = makeCard({ pinned: true });
      useSessionStore.setState({
        chatThread: [makeUserMessage()],
        cards: { [card.id]: card },
      });

      useSessionStore.getState().saveSavedPrompt('Pinned Session');

      const { savedPrompts } = useSessionStore.getState();
      expect(savedPrompts[0].cards[0].pinned).toBe(true);
    });
  });

  describe('loadSavedPrompt (Requirement 8.3)', () => {
    it('restores session state from saved prompt without API calls', () => {
      const card = makeCard();
      const savedMsg = makeUserMessage('saved query');
      const savedPrompt: SavedPrompt = {
        id: 'sp-1',
        name: 'Load Me',
        savedAt: Date.now() - 1000,
        chatThread: [savedMsg],
        cards: [card],
      };

      useSessionStore.setState({
        savedPrompts: [savedPrompt],
        chatThread: [makeUserMessage('current work')],
        cards: {},
      });

      useSessionStore.getState().loadSavedPrompt('sp-1');

      const state = useSessionStore.getState();
      expect(state.chatThread).toHaveLength(1);
      expect(state.chatThread[0].content).toBe('saved query');
      expect(state.cards[card.id]).toBeDefined();
      expect(state.cards[card.id].query).toBe('test query');
      expect(state.activeCardId).toBeNull();
      expect(state.loading).toBe(false);
    });

    it('does nothing when the saved prompt ID is not found', () => {
      const originalThread = [makeUserMessage('original')];
      useSessionStore.setState({
        chatThread: originalThread,
        savedPrompts: [],
      });

      useSessionStore.getState().loadSavedPrompt('nonexistent-id');

      expect(useSessionStore.getState().chatThread).toEqual(originalThread);
    });

    it('restores multiple cards correctly', () => {
      const card1 = makeCard({ pinned: true });
      const card2 = makeCard({ width: '50%' });
      const savedPrompt: SavedPrompt = {
        id: 'sp-2',
        name: 'Multi-card',
        savedAt: Date.now(),
        chatThread: [makeUserMessage(), makeSystemMessage(card1.id), makeSystemMessage(card2.id)],
        cards: [card1, card2],
      };

      useSessionStore.setState({ savedPrompts: [savedPrompt] });
      useSessionStore.getState().loadSavedPrompt('sp-2');

      const state = useSessionStore.getState();
      expect(Object.keys(state.cards)).toHaveLength(2);
      expect(state.cards[card1.id].pinned).toBe(true);
      expect(state.cards[card2.id].width).toBe('50%');
    });
  });

  describe('deleteSavedPrompt (Requirement 8.5)', () => {
    it('removes the prompt from state', () => {
      const prompt: SavedPrompt = {
        id: 'del-1',
        name: 'Delete Me',
        savedAt: Date.now(),
        chatThread: [],
        cards: [],
      };
      useSessionStore.setState({ savedPrompts: [prompt] });

      useSessionStore.getState().deleteSavedPrompt('del-1');

      expect(useSessionStore.getState().savedPrompts).toHaveLength(0);
    });

    it('removes the prompt from localStorage', () => {
      const prompt: SavedPrompt = {
        id: 'del-2',
        name: 'Delete From Storage',
        savedAt: Date.now(),
        chatThread: [],
        cards: [],
      };
      useSessionStore.setState({ savedPrompts: [prompt] });
      // Initially persist
      localStorageMock.setItem('cbi-saved-prompts', JSON.stringify([prompt]));

      useSessionStore.getState().deleteSavedPrompt('del-2');

      const raw = localStorageMock.getItem('cbi-saved-prompts');
      const parsed = JSON.parse(raw!);
      expect(parsed).toHaveLength(0);
    });

    it('does not affect other saved prompts', () => {
      const p1: SavedPrompt = { id: 'keep', name: 'Keep', savedAt: Date.now(), chatThread: [], cards: [] };
      const p2: SavedPrompt = { id: 'remove', name: 'Remove', savedAt: Date.now(), chatThread: [], cards: [] };
      useSessionStore.setState({ savedPrompts: [p1, p2] });

      useSessionStore.getState().deleteSavedPrompt('remove');

      const { savedPrompts } = useSessionStore.getState();
      expect(savedPrompts).toHaveLength(1);
      expect(savedPrompts[0].id).toBe('keep');
    });
  });

  describe('localStorage quota exceeded (Requirement 8.6)', () => {
    it('sets storageError when quota is exceeded on save', () => {
      // Override setItem to throw QuotaExceededError for the saved prompts key
      const originalSetItem = localStorageMock.setItem;
      localStorageMock.setItem = (key: string, value: string) => {
        if (key === 'cbi-saved-prompts') {
          const error = new DOMException('quota exceeded', 'QuotaExceededError');
          throw error;
        }
        originalSetItem.call(localStorageMock, key, value);
      };

      useSessionStore.getState().saveSavedPrompt('Will Fail');

      const state = useSessionStore.getState();
      expect(state.storageError).toContain('Storage quota exceeded');
      // The current session state is not lost
      expect(state.chatThread).toBeDefined();

      // Restore
      localStorageMock.setItem = originalSetItem;
    });

    it('clearStorageError resets the error', () => {
      useSessionStore.setState({ storageError: 'Some error' });

      useSessionStore.getState().clearStorageError();

      expect(useSessionStore.getState().storageError).toBeNull();
    });
  });
});
