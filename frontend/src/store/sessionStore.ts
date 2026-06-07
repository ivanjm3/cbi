import { create } from 'zustand';
import { persist, type PersistStorage, type StorageValue } from 'zustand/middleware';
import type {
  CardState,
  SessionState,
  ChatMessage,
  Bookmark,
  ThreadSummary,
} from '../types';
import { GRID_POSITIONS_LTR_TTB, getOccupiedCells, cellKey } from '../types/grid';
import { queryBackend } from '../api/queryApi';

// ─── Helpers ────────────────────────────────────────────────────────────────

function generateId(): string {
  return crypto.randomUUID();
}

/**
 * Find the next available grid position in LTR-TTB order.
 * Returns null if all positions are occupied.
 */
function nextPosition(cards: CardState[]): { col: number; row: number } | null {
  const occupied = new Set<string>();
  for (const card of cards) {
    const cells = getOccupiedCells(
      card.gridPosition.col,
      card.gridPosition.row,
      card.gridSize.colSpan,
      card.gridSize.rowSpan,
    );
    for (const cell of cells) {
      occupied.add(cell);
    }
  }

  for (const pos of GRID_POSITIONS_LTR_TTB) {
    if (!occupied.has(cellKey(pos.col, pos.row))) {
      return { col: pos.col, row: pos.row };
    }
  }
  return null;
}

/**
 * Find the oldest unpinned card by createdAt timestamp.
 */
function findOldestUnpinned(cards: CardState[]): CardState | undefined {
  return cards
    .filter((c) => !c.pinned)
    .sort((a, b) => a.createdAt - b.createdAt)[0];
}

// ─── Persisted State Shape ──────────────────────────────────────────────────

interface PersistedState {
  cards: CardState[];
  activeCardId: string | null;
  chatThread: ChatMessage[];
  threads: ThreadSummary[];
  bookmarks: Bookmark[];
  statsPanelCollapsed: boolean;
}

// ─── Custom localStorage Storage with Error Handling ────────────────────────

/**
 * Check if localStorage is available and functional.
 */
function isLocalStorageAvailable(): boolean {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return false;
    const testKey = '__cbi_storage_test__';
    window.localStorage.setItem(testKey, '1');
    window.localStorage.removeItem(testKey);
    return true;
  } catch {
    return false;
  }
}

/**
 * Custom storage adapter that handles:
 * - localStorage unavailable (private browsing, node environment)
 * - Quota exceeded errors (non-blocking warning)
 * - Corrupted data (fallback to fresh state)
 */
function createSafeStorage(): PersistStorage<PersistedState> {
  return {
    getItem(name: string): StorageValue<PersistedState> | null {
      if (!isLocalStorageAvailable()) return null;
      try {
        const raw = window.localStorage.getItem(name);
        if (raw === null) return null;
        const parsed = JSON.parse(raw) as StorageValue<PersistedState>;
        // Basic validation: state must be an object with cards array
        if (
          parsed &&
          typeof parsed === 'object' &&
          'state' in parsed &&
          parsed.state &&
          Array.isArray(parsed.state.cards)
        ) {
          return parsed;
        }
        // Corrupted structure, discard
        console.warn('[SessionStore] Corrupted localStorage data detected, starting fresh');
        window.localStorage.removeItem(name);
        return null;
      } catch {
        // JSON parse error or other issue - corrupted data
        console.warn('[SessionStore] Failed to parse localStorage data, starting fresh');
        try {
          window.localStorage.removeItem(name);
        } catch {
          // localStorage might be completely unavailable
        }
        return null;
      }
    },
    setItem(name: string, value: StorageValue<PersistedState>): void {
      if (!isLocalStorageAvailable()) return;
      try {
        window.localStorage.setItem(name, JSON.stringify(value));
      } catch (err: unknown) {
        if (
          err instanceof DOMException &&
          (err.name === 'QuotaExceededError' || err.code === 22)
        ) {
          console.warn(
            '[SessionStore] localStorage quota exceeded. Session persistence unavailable.',
          );
          // Emit custom event so UI can display non-blocking warning
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('storage-quota-exceeded', {
                detail: { message: 'Session persistence unavailable — storage quota exceeded' },
              }),
            );
          }
        } else {
          console.warn('[SessionStore] localStorage write failed:', err);
        }
      }
    },
    removeItem(name: string): void {
      if (!isLocalStorageAvailable()) return;
      try {
        window.localStorage.removeItem(name);
      } catch {
        // Silently ignore removal failures
      }
    },
  };
}

// ─── Store ──────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'cbi-session';

// Notification state (non-persisted)
interface StoreExtras {
  canvasFullNotification: boolean;
}

export const useSessionStore = create<SessionState & StoreExtras>()(
  persist(
    (set, get) => ({
      // ─── State ─────────────────────────────────────────────────────────
      cards: [],
      activeCardId: null,
      chatThread: [],
      threads: [],
      bookmarks: [],
      statsPanelCollapsed: false,
      loading: false,
      canvasFullNotification: false,

      // ─── Actions ───────────────────────────────────────────────────────

      submitQuery: async (queryText: string) => {
        const trimmed = queryText.trim();
        if (!trimmed) return;

        // Add user message to chat thread
        const userMessage: ChatMessage = {
          id: generateId(),
          role: 'user',
          content: trimmed,
          timestamp: Date.now(),
        };

        set({ loading: true, canvasFullNotification: false });
        set((state) => ({
          chatThread: [...state.chatThread, userMessage],
        }));

        try {
          const result = await queryBackend(trimmed);

          if (!result.ok) {
            // Add error message to chat thread with metadata for retry
            // Backend sends error_message (422) or message (503/504)
            const errorMessage: ChatMessage = {
              id: generateId(),
              role: 'error',
              content: result.error?.error_message ?? result.error?.message ?? `Request failed with status ${result.status}`,
              timestamp: Date.now(),
              errorStatus: result.status,
              originalQuery: trimmed,
            };
            set((state) => ({
              chatThread: [...state.chatThread, errorMessage],
              loading: false,
            }));
            return;
          }

          if (!result.data) {
            set({ loading: false });
            return;
          }

          // Create new card
          const cardId = generateId();
          const newCard: CardState = {
            id: cardId,
            query: trimmed,
            renderedOutput: result.data,
            gridPosition: { col: 0, row: 0 }, // Will be set below
            gridSize: { colSpan: 1, rowSpan: 1 },
            pinned: false,
            createdAt: Date.now(),
          };

          // Add system message
          const systemMessage: ChatMessage = {
            id: generateId(),
            role: 'system',
            content: result.data.description,
            cardId,
            timestamp: Date.now(),
          };

          set((state) => {
            const position = nextPosition(state.cards);

            if (position) {
              // Space available
              newCard.gridPosition = position;
              return {
                cards: [...state.cards, newCard],
                chatThread: [...state.chatThread, systemMessage],
                activeCardId: cardId,
                loading: false,
              };
            }

            // Canvas is full - try to replace oldest unpinned
            const oldest = findOldestUnpinned(state.cards);
            if (oldest) {
              newCard.gridPosition = oldest.gridPosition;
              return {
                cards: state.cards.map((c) => (c.id === oldest.id ? newCard : c)),
                chatThread: [...state.chatThread, systemMessage],
                activeCardId: cardId,
                loading: false,
              };
            }

            // All cards pinned - show notification
            return {
              chatThread: [...state.chatThread, systemMessage],
              loading: false,
              canvasFullNotification: true,
            };
          });

          // Update threads
          set((state) => {
            const existingThread = state.threads[0];
            if (existingThread) {
              const updatedThreads: ThreadSummary[] = [
                {
                  ...existingThread,
                  lastActivity: Date.now(),
                  messageCount: existingThread.messageCount + 1,
                },
                ...state.threads.slice(1),
              ];
              return { threads: updatedThreads };
            }
            const newThread: ThreadSummary = {
              id: generateId(),
              firstMessage: trimmed,
              lastActivity: Date.now(),
              messageCount: 1,
            };
            return { threads: [newThread, ...state.threads].slice(0, 50) };
          });
        } catch {
          const errorMessage: ChatMessage = {
            id: generateId(),
            role: 'error',
            content: 'An unexpected error occurred. Please try again.',
            timestamp: Date.now(),
            originalQuery: trimmed,
          };
          set((state) => ({
            chatThread: [...state.chatThread, errorMessage],
            loading: false,
          }));
        }
      },

      addCard: (card: CardState) => {
        set((state) => {
          const position = nextPosition(state.cards);

          if (position) {
            const placed = { ...card, gridPosition: position };
            return {
              cards: [...state.cards, placed],
              canvasFullNotification: false,
            };
          }

          // Canvas full - replace oldest unpinned
          const oldest = findOldestUnpinned(state.cards);
          if (oldest) {
            const placed = { ...card, gridPosition: oldest.gridPosition };
            return {
              cards: state.cards.map((c) => (c.id === oldest.id ? placed : c)),
              canvasFullNotification: false,
            };
          }

          // All pinned
          return { canvasFullNotification: true };
        });
      },

      removeCard: (id: string) => {
        set((state) => ({
          cards: state.cards.filter((c) => c.id !== id),
          activeCardId: state.activeCardId === id ? null : state.activeCardId,
          canvasFullNotification: false,
        }));
      },

      moveCard: (id: string, position: { col: number; row: number }) => {
        set((state) => ({
          cards: state.cards.map((c) =>
            c.id === id ? { ...c, gridPosition: position } : c,
          ),
        }));
      },

      resizeCard: (id: string, size: { colSpan: 1 | 2; rowSpan: 1 | 2 }) => {
        set((state) => ({
          cards: state.cards.map((c) =>
            c.id === id ? { ...c, gridSize: size } : c,
          ),
        }));
      },

      pinCard: (id: string) => {
        set((state) => ({
          cards: state.cards.map((c) =>
            c.id === id ? { ...c, pinned: true } : c,
          ),
        }));
      },

      unpinCard: (id: string) => {
        set((state) => ({
          cards: state.cards.map((c) =>
            c.id === id ? { ...c, pinned: false } : c,
          ),
          canvasFullNotification: false,
        }));
      },

      setActiveCard: (id: string | null) => {
        set({ activeCardId: id });
      },

      toggleStatsPanel: () => {
        set((state) => ({
          statsPanelCollapsed: !state.statsPanelCollapsed,
        }));
      },

      saveBookmark: (name: string) => {
        const state = get();
        const bookmark: Bookmark = {
          id: generateId(),
          name: name.slice(0, 100),
          savedAt: Date.now(),
          chatThread: [...state.chatThread],
          cards: [...state.cards],
        };

        // Pre-check: attempt an explicit write to catch quota errors early.
        // The persist middleware will also write, but this gives immediate feedback
        // specifically for bookmark save operations (requirement 8.6).
        if (isLocalStorageAvailable()) {
          try {
            const newBookmarks = [bookmark, ...state.bookmarks].slice(0, 50);
            const testPayload = JSON.stringify(newBookmarks);
            // Test write to a temporary key to detect quota issues
            const testKey = '__cbi_bookmark_quota_test__';
            window.localStorage.setItem(testKey, testPayload);
            window.localStorage.removeItem(testKey);
          } catch (err: unknown) {
            if (
              err instanceof DOMException &&
              (err.name === 'QuotaExceededError' || err.code === 22)
            ) {
              // Dispatch event so SaveSessionButton can show a targeted error
              window.dispatchEvent(
                new CustomEvent('storage-quota-exceeded', {
                  detail: {
                    message:
                      'Storage quota exceeded. Try deleting older bookmarks to free space.',
                  },
                }),
              );
              // Still add to in-memory state so session isn't lost
            }
          }
        }

        set((prev) => ({
          bookmarks: [bookmark, ...prev.bookmarks].slice(0, 50),
        }));
      },

      loadBookmark: (id: string) => {
        const state = get();
        const bookmark = state.bookmarks.find((b) => b.id === id);
        if (!bookmark) return;

        set({
          cards: [...bookmark.cards],
          chatThread: [...bookmark.chatThread],
          activeCardId: null,
          canvasFullNotification: false,
        });
      },

      deleteBookmark: (id: string) => {
        set((state) => ({
          bookmarks: state.bookmarks.filter((b) => b.id !== id),
        }));
      },

      startNewChat: () => {
        const state = get();

        // Save current thread summary if there are messages
        if (state.chatThread.length > 0) {
          const firstUserMsg = state.chatThread.find((m) => m.role === 'user');
          const newThread: ThreadSummary = {
            id: generateId(),
            firstMessage: firstUserMsg?.content ?? 'Untitled thread',
            lastActivity: Date.now(),
            messageCount: state.chatThread.length,
          };

          set((prev) => ({
            threads: [newThread, ...prev.threads].slice(0, 50),
            cards: [],
            chatThread: [],
            activeCardId: null,
            loading: false,
            canvasFullNotification: false,
          }));
        } else {
          set({
            cards: [],
            chatThread: [],
            activeCardId: null,
            loading: false,
            canvasFullNotification: false,
          });
        }
      },
    }),
    {
      name: STORAGE_KEY,
      storage: createSafeStorage(),
      // Debounce persistence - zustand persist writes on every state change,
      // but the storage adapter handles timing. The persist middleware
      // subscribes to state changes and writes within the microtask queue,
      // which satisfies the "within 1 second" requirement.
      partialize: (state): PersistedState => ({
        cards: state.cards,
        activeCardId: state.activeCardId,
        chatThread: state.chatThread,
        threads: state.threads,
        bookmarks: state.bookmarks,
        statsPanelCollapsed: state.statsPanelCollapsed,
      }),
    },
  ),
);
