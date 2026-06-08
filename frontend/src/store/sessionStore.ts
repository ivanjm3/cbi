/**
 * Zustand Session Store with localStorage persistence.
 *
 * Manages chat thread, visualization cards, sidebar, panels, and saved prompts.
 * Persists to localStorage with graceful error handling for quota and corruption.
 *
 * Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
 */

import { create } from 'zustand';
import { persist, type PersistStorage, type StorageValue } from 'zustand/middleware';
import type {
  SessionState,
  CardState,
  ChatMessage,
  ThreadSummary,
  SavedPrompt,
  TransparencyData,
} from '../types';
import { queryBackend } from '../api/queryApi';
import { parseUserRequestedChartType } from '../utils/chartSelector';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SESSION_STORAGE_KEY = 'cbi-session';
const SAVED_PROMPTS_STORAGE_KEY = 'cbi-saved-prompts';
const MAX_SAVED_PROMPTS = 50;
const MAX_CHAT_HISTORY = 50;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateId(): string {
  return crypto.randomUUID();
}

// ---------------------------------------------------------------------------
// localStorage error-safe storage adapter
// ---------------------------------------------------------------------------

function getStorage(): Storage | null {
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      return window.localStorage;
    }
  } catch {
    // SecurityError in some browsers when cookies are disabled
  }
  return null;
}

/**
 * Persisted state subset — excludes actions and transient flags like `loading`.
 */
type PersistedState = {
  chatThread: ChatMessage[];
  cards: Record<string, CardState>;
  activeCardId: string | null;
  chatHistory: ThreadSummary[];
  savedPrompts: SavedPrompt[];
  sidebarCollapsed: boolean;
  traceabilityPanelVisible: boolean;
  statsPanelCollapsed: boolean;
};

/**
 * Custom storage adapter that handles quota exceeded and corrupted data errors.
 */
function createSafeStorage(): PersistStorage<PersistedState> {
  return {
    getItem(name: string): StorageValue<PersistedState> | null {
      const storage = getStorage();
      if (!storage) return null;
      try {
        const raw = storage.getItem(name);
        if (raw === null) return null;
        const parsed = JSON.parse(raw);
        return parsed as StorageValue<PersistedState>;
      } catch (e) {
        console.warn(
          `[cbi-store] Corrupted localStorage data for key "${name}". Starting fresh.`,
          e,
        );
        try {
          storage.removeItem(name);
        } catch {
          // Ignore removal failures
        }
        return null;
      }
    },
    setItem(name: string, value: StorageValue<PersistedState>): void {
      const storage = getStorage();
      if (!storage) return;
      try {
        storage.setItem(name, JSON.stringify(value));
      } catch (e: unknown) {
        if (
          e instanceof DOMException &&
          (e.name === 'QuotaExceededError' || e.code === 22)
        ) {
          console.warn(
            '[cbi-store] localStorage quota exceeded. Continuing with in-memory state.',
          );
        } else {
          console.warn('[cbi-store] Failed to write to localStorage.', e);
        }
      }
    },
    removeItem(name: string): void {
      const storage = getStorage();
      if (!storage) return;
      try {
        storage.removeItem(name);
      } catch (e) {
        console.warn('[cbi-store] Failed to remove localStorage key.', e);
      }
    },
  };
}

// ---------------------------------------------------------------------------
// Saved Prompts localStorage helpers (separate key)
// ---------------------------------------------------------------------------

function loadSavedPromptsFromStorage(): SavedPrompt[] {
  const storage = getStorage();
  if (!storage) return [];
  try {
    const raw = storage.getItem(SAVED_PROMPTS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch (e) {
    console.warn('[cbi-store] Corrupted saved prompts data. Starting fresh.', e);
    try {
      storage.removeItem(SAVED_PROMPTS_STORAGE_KEY);
    } catch {
      // Ignore
    }
    return [];
  }
}

/**
 * Persist saved prompts to localStorage.
 * Returns `true` on success, or throws an error string on quota exceeded.
 */
function saveSavedPromptsToStorage(prompts: SavedPrompt[]): void {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.setItem(SAVED_PROMPTS_STORAGE_KEY, JSON.stringify(prompts));
  } catch (e: unknown) {
    if (
      e instanceof DOMException &&
      (e.name === 'QuotaExceededError' || e.code === 22)
    ) {
      throw new Error(
        'Storage quota exceeded. Try deleting older saved prompts to free space.',
      );
    } else {
      throw new Error('Failed to save prompts to localStorage.');
    }
  }
}

// ---------------------------------------------------------------------------
// Store creation
// ---------------------------------------------------------------------------

export const useSessionStore = create<SessionState>()(
  persist(
    (set, get) => ({
      // ----- Initial state -----
      chatThread: [],
      cards: {},
      activeCardId: null,
      chatHistory: [],
      savedPrompts: loadSavedPromptsFromStorage(),
      sidebarCollapsed: false,
      traceabilityPanelVisible: false,
      statsPanelCollapsed: false,
      loading: false,
      storageError: null,

      // ----- Actions -----

      submitQuery: async (queryText: string) => {
        // Prevent whitespace-only queries
        if (!queryText.trim()) return;

        const userMessage: ChatMessage = {
          id: generateId(),
          role: 'user',
          content: queryText,
          timestamp: Date.now(),
        };

        set({ loading: true, chatThread: [...get().chatThread, userMessage] });

        try {
          const result = await queryBackend(queryText);

          if (result.ok) {
            const renderedOutput = result.data;
            const cardId = generateId();

            // Parse user-requested chart type from the query
            const userRequestedChartType = parseUserRequestedChartType(queryText);

            // Build transparency data from metadata
            const metadata = renderedOutput.metadata;
            const transparencyData: TransparencyData = {
              queryRewrite: renderedOutput.description ?? null,
              structuredIntent: metadata
                ? {
                    query_id: metadata.query_id,
                    query_type: metadata.query_type,
                    entity_refs: metadata.entity_refs ?? [],
                    routing_metadata: metadata.routing_metadata ?? {},
                    timestamp: metadata.timestamp ?? new Date().toISOString(),
                  }
                : null,
              apiCallSummary: metadata?.data_sources
                ? {
                    agents: metadata.data_sources.map((ds) => ({
                      id: ds,
                      dataSources: [ds],
                      status: 'success' as const,
                    })),
                  }
                : null,
            };

            const newCard: CardState = {
              id: cardId,
              query: queryText,
              userRequestedChartType,
              renderedOutput,
              transparencyData,
              pinned: false,
              width: '100%',
              createdAt: Date.now(),
            };

            const systemMessage: ChatMessage = {
              id: generateId(),
              role: 'system',
              content: renderedOutput.description,
              cardId,
              timestamp: Date.now(),
            };

            const state = get();
            set({
              cards: { ...state.cards, [cardId]: newCard },
              chatThread: [...state.chatThread, systemMessage],
              activeCardId: cardId,
              loading: false,
            });
          } else {
            // API error
            const errorMessage: ChatMessage = {
              id: generateId(),
              role: 'error',
              content:
                result.error?.error_message ??
                `Request failed with status ${result.status}`,
              timestamp: Date.now(),
              statusCode: result.status,
              originalQuery: queryText,
            };

            set({
              chatThread: [...get().chatThread, errorMessage],
              loading: false,
            });
          }
        } catch (err: unknown) {
          const errorMessage: ChatMessage = {
            id: generateId(),
            role: 'error',
            content:
              err instanceof Error
                ? err.message
                : 'An unexpected error occurred',
            timestamp: Date.now(),
            originalQuery: queryText,
          };

          set({
            chatThread: [...get().chatThread, errorMessage],
            loading: false,
          });
        }
      },

      setActiveCard: (id: string | null) => {
        set({ activeCardId: id });
      },

      pinCard: (id: string) => {
        const state = get();
        const card = state.cards[id];
        if (!card) return;
        set({
          cards: { ...state.cards, [id]: { ...card, pinned: true } },
        });
      },

      unpinCard: (id: string) => {
        const state = get();
        const card = state.cards[id];
        if (!card) return;
        set({
          cards: { ...state.cards, [id]: { ...card, pinned: false } },
        });
      },

      resizeCard: (id: string, width: '50%' | '100%') => {
        const state = get();
        const card = state.cards[id];
        if (!card) return;
        set({
          cards: { ...state.cards, [id]: { ...card, width } },
        });
      },

      reorderCard: (id: string, newIndex: number) => {
        const state = get();
        // Find the system message associated with this card
        const chatThread = [...state.chatThread];
        const currentIndex = chatThread.findIndex(
          (msg) => msg.cardId === id,
        );
        if (currentIndex === -1) return;

        // Clamp newIndex to valid range
        const clampedIndex = Math.max(
          0,
          Math.min(newIndex, chatThread.length - 1),
        );
        if (clampedIndex === currentIndex) return;

        // Check if target position is a pinned card — reject if so
        const targetMsg = chatThread[clampedIndex];
        if (targetMsg?.cardId && state.cards[targetMsg.cardId]?.pinned) {
          return; // Reject drop on pinned card position
        }

        // Remove the message from its current position and insert at new position
        const [message] = chatThread.splice(currentIndex, 1);
        chatThread.splice(clampedIndex, 0, message);

        set({ chatThread });
      },

      toggleSidebar: () => {
        set({ sidebarCollapsed: !get().sidebarCollapsed });
      },

      toggleTraceabilityPanel: () => {
        set({ traceabilityPanelVisible: !get().traceabilityPanelVisible });
      },

      toggleStatsPanel: () => {
        set({ statsPanelCollapsed: !get().statsPanelCollapsed });
      },

      saveSavedPrompt: (name: string) => {
        const state = get();
        const finalName = name.slice(0, 100);

        const savedPrompt: SavedPrompt = {
          id: generateId(),
          name: finalName,
          savedAt: Date.now(),
          chatThread: [...state.chatThread],
          cards: Object.values(state.cards),
        };

        const newSavedPrompts = [savedPrompt, ...state.savedPrompts].slice(
          0,
          MAX_SAVED_PROMPTS,
        );

        try {
          saveSavedPromptsToStorage(newSavedPrompts);
          set({ savedPrompts: newSavedPrompts, storageError: null });
        } catch (e: unknown) {
          const errorMsg =
            e instanceof Error
              ? e.message
              : 'Unable to save session. Storage may be full — try deleting older saved prompts to free space.';
          set({ storageError: errorMsg });
        }
      },

      loadSavedPrompt: (id: string) => {
        const state = get();
        const prompt = state.savedPrompts.find((p) => p.id === id);
        if (!prompt) return;

        // Restore session from saved prompt
        const cardsRecord: Record<string, CardState> = {};
        for (const card of prompt.cards) {
          cardsRecord[card.id] = card;
        }

        set({
          chatThread: [...prompt.chatThread],
          cards: cardsRecord,
          activeCardId: null,
          loading: false,
        });
      },

      deleteSavedPrompt: (id: string) => {
        const state = get();
        const newSavedPrompts = state.savedPrompts.filter((p) => p.id !== id);
        set({ savedPrompts: newSavedPrompts });
        saveSavedPromptsToStorage(newSavedPrompts);
      },

      startNewChat: () => {
        const state = get();
        // Save current thread as history if it has messages
        const newHistory = [...state.chatHistory];
        if (state.chatThread.length > 0) {
          const firstUserMsg = state.chatThread.find(
            (m) => m.role === 'user',
          );
          const summary: ThreadSummary = {
            id: generateId(),
            firstMessage:
              firstUserMsg?.content ?? 'New conversation',
            lastActivity: Date.now(),
            messageCount: state.chatThread.length,
          };
          newHistory.unshift(summary);
          if (newHistory.length > MAX_CHAT_HISTORY) newHistory.pop();
        }

        set({
          chatThread: [],
          cards: {},
          activeCardId: null,
          chatHistory: newHistory,
          loading: false,
        });
      },

      clearStorageError: () => {
        set({ storageError: null });
      },
    }),
    {
      name: SESSION_STORAGE_KEY,
      version: 2,
      storage: createSafeStorage(),
      partialize: (state): PersistedState => ({
        chatThread: state.chatThread,
        cards: state.cards,
        activeCardId: state.activeCardId,
        chatHistory: state.chatHistory,
        savedPrompts: state.savedPrompts,
        sidebarCollapsed: state.sidebarCollapsed,
        traceabilityPanelVisible: state.traceabilityPanelVisible,
        statsPanelCollapsed: state.statsPanelCollapsed,
      }),
    },
  ),
);
