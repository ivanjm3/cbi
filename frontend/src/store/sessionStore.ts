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
  ConversationStrand,
  ChartType,
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
  strands: Record<string, ConversationStrand>;
  activeStrandId: string | null;
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
      strands: {},
      activeStrandId: null,
      chatHistory: [],
      savedPrompts: loadSavedPromptsFromStorage(),
      sidebarCollapsed: false,
      traceabilityPanelVisible: false,
      statsPanelCollapsed: false,
      loading: false,
      strandLoading: {},
      storageError: null,

      // ----- Transient state for query cancellation (not persisted) -----
      // Module-level refs to track active query for cancellation
      _activeAbortController: null as AbortController | null,
      _activeCorrelationId: null as string | null,

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

        const state = get();

        // Create abort controller and correlation ID for this query
        const { generateCorrelationId } = await import('../api/queryApi');
        const abortController = new AbortController();
        const correlationId = generateCorrelationId();

        // Auto-update the current thread's entry in chat history
        // If this is the FIRST message in the thread, create a history entry
        if (state.chatThread.length === 0) {
          const threadId = generateId();
          const summary: ThreadSummary = {
            id: threadId,
            firstMessage: queryText.length > 60 ? queryText.slice(0, 60) + '…' : queryText,
            lastActivity: Date.now(),
            messageCount: 1,
            chatThread: [userMessage],
            cards: Object.values(state.cards),
          };
          set({
            loading: true,
            chatThread: [userMessage],
            chatHistory: [summary, ...state.chatHistory].slice(0, MAX_CHAT_HISTORY),
            _activeAbortController: abortController,
            _activeCorrelationId: correlationId,
          });
        } else {
          set({
            loading: true,
            chatThread: [...state.chatThread, userMessage],
            _activeAbortController: abortController,
            _activeCorrelationId: correlationId,
          });
        }

        try {
          const result = await queryBackend(queryText, correlationId, abortController.signal);

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
              content: renderedOutput.description ?? 'Response received.',
              cardId,
              timestamp: Date.now(),
            };

            const state = get();
            set({
              cards: { ...state.cards, [cardId]: newCard },
              chatThread: [...state.chatThread, systemMessage],
              activeCardId: cardId,
              loading: false,
              _activeAbortController: null,
              _activeCorrelationId: null,
            });

            // Sync current thread to its history entry
            const updatedState = get();
            const historyIdx = updatedState.chatHistory.findIndex(
              (h) => h.chatThread[0]?.id === updatedState.chatThread[0]?.id
            );
            if (historyIdx >= 0) {
              const updatedHistory = [...updatedState.chatHistory];
              updatedHistory[historyIdx] = {
                ...updatedHistory[historyIdx],
                lastActivity: Date.now(),
                messageCount: updatedState.chatThread.length,
                chatThread: [...updatedState.chatThread],
                cards: Object.values(updatedState.cards),
              };
              set({ chatHistory: updatedHistory });
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
              _activeAbortController: null,
              _activeCorrelationId: null,
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
            _activeAbortController: null,
            _activeCorrelationId: null,
          });
        }
      },

      cancelQuery: async () => {
        const state = get();
        if (!state._activeAbortController && !state._activeCorrelationId) {
          return; // No active query to cancel
        }

        // Abort the in-flight request
        if (state._activeAbortController) {
          state._activeAbortController.abort();
        }

        // Send cancellation request to backend (if we have a correlation ID)
        if (state._activeCorrelationId) {
          const { cancelQuery: cancelQueryAPI } = await import('../api/queryApi');
          await cancelQueryAPI(state._activeCorrelationId);
        }

        // Reset all strand loading states
        const resetStrandLoading: Record<string, boolean> = {};
        for (const key of Object.keys(state.strandLoading)) {
          resetStrandLoading[key] = false;
        }

        // Reset state
        set({
          loading: false,
          strandLoading: resetStrandLoading,
          _activeAbortController: null,
          _activeCorrelationId: null,
        });

        // Append system message indicating cancellation
        const cancelMessage: ChatMessage = {
          id: generateId(),
          role: 'system',
          content: 'Query cancelled.',
          timestamp: Date.now(),
        };

        set({
          chatThread: [...get().chatThread, cancelMessage],
        });

        // Re-enable input
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

        // Save all cards in the current session (up to 6).
        const allCards = Object.values(state.cards).slice(0, 6);

        if (allCards.length === 0) return; // Nothing to save

        const savedPrompt: SavedPrompt = {
          id: generateId(),
          name: finalName,
          savedAt: Date.now(),
          chatThread: [...state.chatThread],
          cards: allCards,
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
        // Simply reset the active thread. The current thread is already
        // saved in chatHistory (auto-saved on first submit).
        set({
          chatThread: [],
          cards: {},
          activeCardId: null,
          loading: false,
        });
      },

      loadChatThread: (id: string) => {
        const state = get();
        const thread = state.chatHistory.find((t) => t.id === id);
        if (!thread) return;

        // Load the selected thread
        const cardsRecord: Record<string, CardState> = {};
        for (const card of thread.cards) {
          cardsRecord[card.id] = card;
        }

        set({
          chatThread: [...thread.chatThread],
          cards: cardsRecord,
          activeCardId: null,
          loading: false,
        });
      },

      deleteChatThread: (id: string) => {
        const state = get();
        set({
          chatHistory: state.chatHistory.filter((t) => t.id !== id),
        });
      },

      deleteChatThreads: (ids: string[]) => {
        const state = get();
        const idsSet = new Set(ids);
        set({
          chatHistory: state.chatHistory.filter((t) => !idsSet.has(t.id)),
        });
      },

      clearAllChatHistory: () => {
        set({
          chatHistory: [],
        });
      },

      renameChatThread: (id: string, newName: string) => {
        const state = get();
        set({
          chatHistory: state.chatHistory.map((t) =>
            t.id === id ? { ...t, firstMessage: newName.slice(0, 100) } : t
          ),
        });
      },

      clearStorageError: () => {
        set({ storageError: null });
      },

      createStrand: (cardId: string) => {
        const strandId = generateId();
        const state = get();
        const card = state.cards[cardId];
        if (!card || !card.renderedOutput) return strandId;

        const strandRawData = card.renderedOutput.raw_data != null ? card.renderedOutput.raw_data : undefined;
        const strand: ConversationStrand = {
          id: strandId,
          cardId,
          messages: [],
          context: {
            query: card.query,
            rawData: strandRawData,
            metadata: card.renderedOutput.metadata,
          },
          createdAt: Date.now(),
          updatedAt: Date.now(),
        };

        set({
          strands: { ...state.strands, [strandId]: strand },
          activeStrandId: strandId,
        });

        return strandId;
      },

      deleteStrand: (strandId: string) => {
        const state = get();
        const { [strandId]: _, ...remainingStrands } = state.strands;
        const { [strandId]: __, ...remainingLoading } = state.strandLoading;
        set({
          strands: remainingStrands,
          strandLoading: remainingLoading,
          activeStrandId: state.activeStrandId === strandId ? null : state.activeStrandId,
        });
      },

      changeCardVisualizationType: async (cardId: string, newType: ChartType | 'text') => {
        const state = get();
        const card = state.cards[cardId];
        if (!card) return;

        // ✅ CHECK CACHE FIRST — don't re-process if we already have this type
        const cached = card.renderCache?.[newType];
        if (cached) {
          set({
            cards: {
              ...state.cards,
              [cardId]: {
                ...card,
                selectedVisualizationType: newType,
                renderedOutput: cached,
              },
            },
          });
          return;
        }

        set({ loading: true });

        try {
          const { convertChartType } = await import('../api/queryApi');
          
          // Get raw data for re-rendering — use raw_data first, fallback to chart_data
          const rawData = card.renderedOutput.raw_data || card.renderedOutput.chart_data;
          if (!rawData) {
            // Fallback: re-submit original query with chart type hint
            const { queryBackend } = await import('../api/queryApi');
            const result = await queryBackend(
              `${card.query} (show as ${newType})`,
            );
            if (result.ok) {
              const updatedCache = { ...(card.renderCache || {}), [newType]: result.data };
              set({
                cards: {
                  ...get().cards,
                  [cardId]: {
                    ...card,
                    selectedVisualizationType: newType,
                    renderedOutput: result.data,
                    renderCache: updatedCache,
                  },
                },
                loading: false,
              });
            } else {
              set({ loading: false });
            }
            return;
          }

          const result = await convertChartType(rawData, newType, card.query);

          if (result.ok) {
            // Cache the result for future switches
            const updatedCache = { ...(card.renderCache || {}), [newType]: result.data };
            set({
              cards: {
                ...get().cards,
                [cardId]: {
                  ...card,
                  selectedVisualizationType: newType,
                  renderedOutput: result.data,
                  renderCache: updatedCache,
                },
              },
              loading: false,
            });
          } else {
            set({ loading: false });
          }
        } catch (err) {
          console.error('Chart conversion error:', err);
          set({ loading: false });
        }
      },

      submitFollowUpQuery: async (strandId: string, followUpQuery: string) => {
        if (!followUpQuery.trim()) return;

        const state = get();
        const strand = state.strands[strandId];
        if (!strand) return;

        const userMessage: ChatMessage = {
          id: generateId(),
          role: 'user',
          content: followUpQuery,
          timestamp: Date.now(),
          strandId,
        };

        // Add follow-up message to strand immediately
        const updatedStrand: ConversationStrand = {
          ...strand,
          messages: [...strand.messages, userMessage],
          updatedAt: Date.now(),
        };

        set({
          strandLoading: { ...state.strandLoading, [strandId]: true },
          strands: { ...state.strands, [strandId]: updatedStrand },
        });

        // Check if user is asking for a visualization change
        const chartTypeKeywords: Record<string, ChartType | 'text'> = {
          'as a bar chart': 'bar', 'as bar chart': 'bar', 'as a bar': 'bar', 'bar chart': 'bar',
          'as a line chart': 'line', 'as line chart': 'line', 'as a line': 'line', 'line chart': 'line',
          'as a scatter': 'scatter', 'scatter plot': 'scatter',
          'as a pie chart': 'pie', 'as pie chart': 'pie', 'pie chart': 'pie', 'as a pie': 'pie',
          'as a table': 'table', 'as table': 'table',
          'as text': 'text', 'as a text': 'text',
        };

        // Check for chart modification keywords (add legend, change title, etc.)
        const chartModificationKeywords = [
          'add a legend', 'add legend', 'show legend', 'hide legend',
          'add a title', 'add title', 'change title', 'set title',
          'add label', 'add labels', 'change label', 'change labels',
          'change color', 'change colours', 'make it', 'update the',
          'add annotation', 'add text', 'write', 'display on',
          'remove', 'hide', 'show grid', 'hide grid',
          'add axis', 'change axis', 'rotate',
        ];

        const queryLower = followUpQuery.toLowerCase();
        let detectedChartType: ChartType | 'text' | null = null;
        for (const [keyword, chartType] of Object.entries(chartTypeKeywords)) {
          if (queryLower.includes(keyword)) {
            detectedChartType = chartType;
            break;
          }
        }

        const isChartModification = chartModificationKeywords.some((kw) => queryLower.includes(kw));

        // Build full conversation history for context
        const conversationHistory = updatedStrand.messages
          .map((m) => `${m.role === 'user' ? 'User' : 'System'}: ${m.content}`)
          .join('\n');

        // If it's a visualization request OR chart modification, route through viz pipeline
        if ((detectedChartType || isChartModification) && strand.cardId) {
          try {
            const abortController = new AbortController();
            set({ _activeAbortController: abortController });

            const card = get().cards[strand.cardId];

            // Build context-rich query with full conversation history
            const contextParts = [
              `Original query: "${strand.context.query}"`,
              conversationHistory ? `\nConversation so far:\n${conversationHistory}` : '',
              `\nLatest request: ${followUpQuery}`,
              detectedChartType ? `\n(MUST show as ${detectedChartType} chart)` : '',
            ];
            const contextualChartQuery = contextParts.filter(Boolean).join('');

            const { queryBackend } = await import('../api/queryApi');
            const result = await queryBackend(contextualChartQuery, undefined, abortController.signal);

            if (result.ok) {
              const currentCards = get().cards;
              if (card) {
                const newOutput = result.data;
                const updatedCard = {
                  ...card,
                  renderedOutput: newOutput,
                  ...(detectedChartType ? { selectedVisualizationType: detectedChartType } : {}),
                  renderCache: detectedChartType
                    ? { ...(card.renderCache || {}), [detectedChartType]: newOutput }
                    : card.renderCache,
                };
                set({ cards: { ...currentCards, [strand.cardId]: updatedCard } });
              }

              const systemMessage: ChatMessage = {
                id: generateId(),
                role: 'system',
                content: result.data.description || `Visualization updated.`,
                timestamp: Date.now(),
                strandId,
              };

              const finalStrand = get().strands[strandId];
              if (finalStrand) {
                set({
                  strands: {
                    ...get().strands,
                    [strandId]: {
                      ...finalStrand,
                      messages: [...finalStrand.messages, systemMessage],
                      updatedAt: Date.now(),
                    },
                  },
                  strandLoading: { ...get().strandLoading, [strandId]: false },
                  _activeAbortController: null,
                });
              }
              return;
            }
          } catch (err) {
            console.warn('Chart/modification request failed, falling back:', err);
          }
        }

        try {
          // Normal follow-up: include full conversation context
          const contextualQuery = `
Original query: "${strand.context.query}"
${conversationHistory ? `\nConversation history:\n${conversationHistory}\n` : ''}
Follow-up question: ${followUpQuery}

Answer the follow-up question. Use the conversation context to understand what "this", "that", "it" refers to.
          `.trim();

          // Create abort controller for cancellation support
          const abortController = new AbortController();
          set({ _activeAbortController: abortController });

          // Use the existing queryBackend endpoint
          const { queryBackend } = await import('../api/queryApi');
          const result = await queryBackend(contextualQuery, undefined, abortController.signal);

          if (result.ok) {
            const followUpResponse = result.data;

            // Create system message with the follow-up response
            const systemMessage: ChatMessage = {
              id: generateId(),
              role: 'system',
              content: followUpResponse?.description ?? followUpResponse?.text_content ?? 'Response received.',
              timestamp: Date.now(),
              strandId,
            };

            // Update strand with response
            const finalStrand = get().strands[strandId];
            if (finalStrand) {
              set({
                strands: {
                  ...get().strands,
                  [strandId]: {
                    ...finalStrand,
                    messages: [...finalStrand.messages, systemMessage],
                    updatedAt: Date.now(),
                  },
                },
                strandLoading: { ...get().strandLoading, [strandId]: false },
              });
            }
          } else {
            const errorMessage: ChatMessage = {
              id: generateId(),
              role: 'error',
              content: result.error?.error_message || 'Follow-up query failed. Please try again.',
              timestamp: Date.now(),
              strandId,
              statusCode: result.status,
            };

            const finalStrand = get().strands[strandId];
            if (finalStrand) {
              set({
                strands: {
                  ...get().strands,
                  [strandId]: {
                    ...finalStrand,
                    messages: [...finalStrand.messages, errorMessage],
                    updatedAt: Date.now(),
                  },
                },
                strandLoading: { ...get().strandLoading, [strandId]: false },
              });
            }
          }
        } catch (err) {
          const errorMessage: ChatMessage = {
            id: generateId(),
            role: 'error',
            content: err instanceof Error ? err.message : 'An unexpected error occurred',
            timestamp: Date.now(),
            strandId,
          };

          const finalStrand = get().strands[strandId];
          if (finalStrand) {
            set({
              strands: {
                ...get().strands,
                [strandId]: {
                  ...finalStrand,
                  messages: [...finalStrand.messages, errorMessage],
                  updatedAt: Date.now(),
                },
              },
              strandLoading: { ...get().strandLoading, [strandId]: false },
            });
          }
        }
      },
    }),
    {
      name: SESSION_STORAGE_KEY,
      version: 3,
      storage: createSafeStorage(),
      partialize: (state): PersistedState => ({
        chatThread: state.chatThread,
        cards: state.cards,
        activeCardId: state.activeCardId,
        strands: state.strands,
        activeStrandId: state.activeStrandId,
        chatHistory: state.chatHistory,
        savedPrompts: state.savedPrompts,
        sidebarCollapsed: state.sidebarCollapsed,
        traceabilityPanelVisible: state.traceabilityPanelVisible,
        statsPanelCollapsed: state.statsPanelCollapsed,
      }),
    },
  ),
);
