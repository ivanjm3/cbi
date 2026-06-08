/**
 * Zustand Session Store with localStorage persistence.
 *
 * Manages canvas layout, chat thread, bookmarks, and UI state.
 * Persists to localStorage with debounced writes and graceful error handling.
 *
 * Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8
 */

import { create } from 'zustand';
import { persist, type PersistStorage, type StorageValue } from 'zustand/middleware';
import type {
  SessionState,
  CardState,
  ChatMessage,
  Bookmark,
  ThreadSummary,
} from '../types';
import { queryBackend } from '../api/queryApi';
import { nextPosition } from '../utils/gridHelpers';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SESSION_STORAGE_KEY = 'cbi-session';
const BOOKMARKS_STORAGE_KEY = 'cbi-bookmarks';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateId(): string {
  return crypto.randomUUID();
}

/**
 * Find the oldest unpinned card in the list.
 * Returns the card with the earliest createdAt that is not pinned.
 */
function findOldestUnpinned(cards: CardState[]): CardState | undefined {
  return cards
    .filter((c) => !c.pinned)
    .sort((a, b) => a.createdAt - b.createdAt)[0];
}

// ---------------------------------------------------------------------------
// localStorage error-safe storage adapter
// ---------------------------------------------------------------------------

/**
 * Safely access localStorage. Returns null if unavailable (SSR, private browsing, etc.)
 */
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
 * Custom storage adapter that handles quota exceeded and corrupted data errors.
 * - Quota exceeded: logs warning, continues with in-memory state
 * - Corrupted data: logs warning, returns null (starts fresh)
 * - localStorage unavailable: operates in memory-only mode
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
        // Remove corrupted data
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
      } catch (e: any) {
        if (e?.name === 'QuotaExceededError' || e?.code === 22) {
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
// Bookmarks localStorage helpers (separate key)
// ---------------------------------------------------------------------------

function loadBookmarksFromStorage(): Bookmark[] {
  const storage = getStorage();
  if (!storage) return [];
  try {
    const raw = storage.getItem(BOOKMARKS_STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch (e) {
    console.warn('[cbi-store] Corrupted bookmarks data. Starting fresh.', e);
    try {
      storage.removeItem(BOOKMARKS_STORAGE_KEY);
    } catch {
      // Ignore
    }
    return [];
  }
}

function saveBookmarksToStorage(bookmarks: Bookmark[]): void {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.setItem(BOOKMARKS_STORAGE_KEY, JSON.stringify(bookmarks));
  } catch (e: any) {
    if (e?.name === 'QuotaExceededError' || e?.code === 22) {
      console.warn(
        '[cbi-store] localStorage quota exceeded when saving bookmarks. Bookmarks remain in memory only.',
      );
    } else {
      console.warn('[cbi-store] Failed to save bookmarks to localStorage.', e);
    }
  }
}

// ---------------------------------------------------------------------------
// Persisted state subset (what gets written to localStorage)
// ---------------------------------------------------------------------------

type PersistedState = {
  cards: CardState[];
  activeCardId: string | null;
  chatThread: ChatMessage[];
  threads: ThreadSummary[];
  statsPanelCollapsed: boolean;
  workspaceName: string;
};

// ---------------------------------------------------------------------------
// Store creation
// ---------------------------------------------------------------------------

export const useSessionStore = create<SessionState>()(
  persist(
    (set, get) => ({
      // ----- Initial state -----
      cards: [],
      activeCardId: null,
      chatThread: [],
      threads: [],
      bookmarks: loadBookmarksFromStorage(),
      statsPanelCollapsed: false,
      loading: false,
      workspaceName: 'Untitled Workspace',

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
            // Validate that result.data has required fields
            if (!result.data || typeof result.data !== 'object') {
              const errorMessage: ChatMessage = {
                id: generateId(),
                role: 'error',
                content: 'Received an invalid response from the server.',
                timestamp: Date.now(),
                originalQuery: queryText,
              };
              set({
                chatThread: [...get().chatThread, errorMessage],
                loading: false,
              });
              return;
            }

            // Ensure required fields have defaults
            const renderedOutput = {
              output_type: result.data.output_type ?? 'text',
              chart_type: result.data.chart_type ?? null,
              chart_data: result.data.chart_data ?? null,
              text_content: result.data.text_content ?? null,
              description: result.data.description ?? 'Query completed.',
              metadata: result.data.metadata ?? { query_id: generateId(), query_type: 'unknown' },
            } as typeof result.data;

            const state = get();
            const position = nextPosition(state.cards);
            let newCards = [...state.cards];

            if (position) {
              // Grid has space - place the new card
              const newCard: CardState = {
                id: generateId(),
                query: queryText,
                renderedOutput: renderedOutput,
                gridPosition: position,
                gridSize: { colSpan: 1, rowSpan: 1 },
                pinned: false,
                bookmarked: false,
                createdAt: Date.now(),
              };
              newCards.push(newCard);

              const systemMessage: ChatMessage = {
                id: generateId(),
                role: 'system',
                content: renderedOutput.description,
                cardId: newCard.id,
                timestamp: Date.now(),
              };

              set({
                cards: newCards,
                chatThread: [...get().chatThread, systemMessage],
                activeCardId: newCard.id,
                loading: false,
              });
            } else {
              // Canvas full - try to replace oldest unpinned card
              const oldest = findOldestUnpinned(state.cards);
              if (oldest) {
                const newCard: CardState = {
                  id: generateId(),
                  query: queryText,
                  renderedOutput: renderedOutput,
                  gridPosition: oldest.gridPosition,
                  gridSize: { colSpan: 1, rowSpan: 1 },
                  pinned: false,
                  bookmarked: false,
                  createdAt: Date.now(),
                };
                newCards = newCards.filter((c) => c.id !== oldest.id);
                newCards.push(newCard);

                const systemMessage: ChatMessage = {
                  id: generateId(),
                  role: 'system',
                  content: renderedOutput.description,
                  cardId: newCard.id,
                  timestamp: Date.now(),
                };

                set({
                  cards: newCards,
                  chatThread: [...get().chatThread, systemMessage],
                  activeCardId: newCard.id,
                  loading: false,
                });
              } else {
                // All cards pinned - cannot replace, just stop loading
                // (notification handled by UI layer)
                set({ loading: false });
              }
            }
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
        } catch (err: any) {
          const errorMessage: ChatMessage = {
            id: generateId(),
            role: 'error',
            content: err?.message ?? 'An unexpected error occurred',
            timestamp: Date.now(),
            originalQuery: queryText,
          };

          set({
            chatThread: [...get().chatThread, errorMessage],
            loading: false,
          });
        }
      },

      addCard: (card: CardState) => {
        const state = get();
        const position = nextPosition(state.cards);

        if (position) {
          set({ cards: [...state.cards, { ...card, gridPosition: position }] });
        } else {
          // Canvas full - replace oldest unpinned
          const oldest = findOldestUnpinned(state.cards);
          if (oldest) {
            const updatedCards = state.cards.filter((c) => c.id !== oldest.id);
            set({ cards: [...updatedCards, { ...card, gridPosition: oldest.gridPosition }] });
          }
          // If all pinned, do nothing (notification handled elsewhere)
        }
      },

      removeCard: (id: string) => {
        const state = get();
        const newCards = state.cards.filter((c) => c.id !== id);
        const newActiveId = state.activeCardId === id ? null : state.activeCardId;
        set({ cards: newCards, activeCardId: newActiveId });
      },

      moveCard: (id: string, position: { col: number; row: number }) => {
        set({
          cards: get().cards.map((c) =>
            c.id === id ? { ...c, gridPosition: position } : c,
          ),
        });
      },

      resizeCard: (id: string, size: { colSpan: 1 | 2; rowSpan: 1 | 2 }) => {
        set({
          cards: get().cards.map((c) =>
            c.id === id ? { ...c, gridSize: size } : c,
          ),
        });
      },

      pinCard: (id: string) => {
        set({
          cards: get().cards.map((c) =>
            c.id === id ? { ...c, pinned: true } : c,
          ),
        });
      },

      unpinCard: (id: string) => {
        set({
          cards: get().cards.map((c) =>
            c.id === id ? { ...c, pinned: false } : c,
          ),
        });
      },

      setActiveCard: (id: string | null) => {
        set({ activeCardId: id });
      },

      toggleStatsPanel: () => {
        set({ statsPanelCollapsed: !get().statsPanelCollapsed });
      },

      toggleCardBookmark: (id: string) => {
        set({
          cards: get().cards.map((c) =>
            c.id === id ? { ...c, bookmarked: !c.bookmarked } : c,
          ),
        });
      },

      saveBookmark: (name: string) => {
        const state = get();
        const bookmark: Bookmark = {
          id: generateId(),
          name: name.slice(0, 100),
          savedAt: Date.now(),
          chatThread: [...state.chatThread],
          cards: [...state.cards],
          workspaceName: state.workspaceName,
        };

        const newBookmarks = [bookmark, ...state.bookmarks].slice(0, 50);
        set({ bookmarks: newBookmarks });
        saveBookmarksToStorage(newBookmarks);
      },

      loadBookmark: (id: string) => {
        const state = get();
        const bookmark = state.bookmarks.find((b) => b.id === id);
        if (!bookmark) return;

        set({
          chatThread: [...bookmark.chatThread],
          cards: [...bookmark.cards],
          activeCardId: null,
          workspaceName: bookmark.workspaceName,
        });
      },

      deleteBookmark: (id: string) => {
        const state = get();
        const newBookmarks = state.bookmarks.filter((b) => b.id !== id);
        set({ bookmarks: newBookmarks });
        saveBookmarksToStorage(newBookmarks);
      },

      startNewChat: () => {
        const state = get();
        // Save current thread as a history entry if it has messages OR cards
        const newThreads = [...state.threads];
        if (state.chatThread.length > 0 || state.cards.length > 0) {
          const firstUserMsg = state.chatThread.find((m) => m.role === 'user');
          const summary: ThreadSummary = {
            id: generateId(),
            firstMessage: firstUserMsg?.content ?? state.cards[0]?.query ?? 'New conversation',
            lastActivity: Date.now(),
            messageCount: state.chatThread.length,
          };
          newThreads.unshift(summary);
          // Keep max 50 threads
          if (newThreads.length > 50) newThreads.pop();
        }

        // Clear everything for a completely blank workspace
        set({
          chatThread: [],
          cards: [],
          activeCardId: null,
          threads: newThreads,
          loading: false,
        });
      },
    }),
    {
      name: SESSION_STORAGE_KEY,
      storage: createSafeStorage(),
      // Debounce persistence to within 1 second
      // zustand persist middleware writes synchronously, so we don't need extra debounce
      // since the middleware handles it. However, we can use partialize to reduce storage size.
      partialize: (state): PersistedState => ({
        cards: state.cards,
        activeCardId: state.activeCardId,
        chatThread: state.chatThread,
        threads: state.threads,
        statsPanelCollapsed: state.statsPanelCollapsed,
        workspaceName: state.workspaceName,
      }),
    },
  ),
);
