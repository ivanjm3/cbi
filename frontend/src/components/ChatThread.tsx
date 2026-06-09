/**
 * ChatThread component.
 *
 * Displays visualizations in a grid layout:
 * - 1 graph → 1 column (full width, row 1 col 1)
 * - 2 graphs → 2 columns (row 1 col 1, row 2 col 1)
 * - 3 graphs → row 1: 2 cols, row 2: 1 col (1,1 / 2,1 / 1,2)
 * - 4 graphs → 2x2 grid (1,1 / 2,1 / 1,2 / 2,2)
 * - 5 graphs → row 1: 2 cols, row 2: 2 cols, row 3: 1 col
 * - 6 graphs → 3x2 grid
 * - Max 6 visualizations. Exceeding 6 prompts user to delete one.
 *
 * Also shows error messages and a typing indicator when loading.
 *
 * Requirements: 1.5, 1.8, 2.6, 2.7, 2.8, 9.3, 9.4, 9.5
 */

import { useEffect, useRef, useState } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { DraggableCard } from './DraggableCard';
import { ErrorMessage } from './ErrorMessage';
import type { ChatMessage, CardState } from '../types';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** Typing/streaming indicator — left-aligned placeholder with animated dots */
function TypingIndicator() {
  return (
    <div className="flex justify-start" aria-label="Loading response">
      <div className="rounded-2xl rounded-bl-sm bg-bubble-system border border-border-default px-4 py-3 shadow-card">
        <div className="flex items-center gap-1.5" aria-live="polite" aria-label="System is thinking">
          <span className="w-2 h-2 rounded-full bg-text-muted animate-bounce [animation-delay:0ms]" />
          <span className="w-2 h-2 rounded-full bg-text-muted animate-bounce [animation-delay:150ms]" />
          <span className="w-2 h-2 rounded-full bg-text-muted animate-bounce [animation-delay:300ms]" />
        </div>
      </div>
    </div>
  );
}

/** Empty state — centered prompt to encourage the user to submit a query */
function EmptyState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-12 w-12 text-text-muted"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
        />
      </svg>
      <p className="text-text-secondary text-base text-center">
        Ask a question to get started
      </p>
      <p className="text-text-muted text-sm text-center max-w-md">
        Type a query below to explore your data with natural language
      </p>
    </div>
  );
}

/**
 * Max visualizations exceeded modal.
 * Prompts user to pick one card to delete from the current session.
 */
function MaxVisualizationsModal({
  cards,
  onDelete,
  onCancel,
}: {
  cards: CardState[];
  onDelete: (cardId: string) => void;
  onCancel: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-label="Maximum visualizations reached"
    >
      <div className="mx-4 w-full max-w-md rounded-lg bg-bg-secondary p-6 shadow-panel">
        <h3 className="text-base font-semibold text-text-primary">
          Maximum Visualizations Reached
        </h3>
        <p className="mt-2 text-sm text-text-secondary">
          You can have at most 6 visualizations. Please select one to remove:
        </p>
        <ul className="mt-4 max-h-64 overflow-y-auto space-y-2">
          {cards.map((card) => (
            <li key={card.id}>
              <button
                type="button"
                onClick={() => onDelete(card.id)}
                className="w-full text-left rounded-md border border-border-default px-3 py-2 text-sm hover:bg-red-50 hover:border-status-error transition-colors"
              >
                <p className="font-medium text-text-primary truncate">{card.query}</p>
                <p className="text-xs text-text-muted mt-0.5">
                  {card.renderedOutput.chart_type ?? 'text'} • {new Date(card.createdAt).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                </p>
              </button>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md px-3 py-2 text-sm font-medium text-text-secondary hover:bg-bg-input"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Renders cards in a grid layout:
 * - 1 card: single full-width
 * - 2 cards: two rows, 1 card each (stacked vertically at full width)
 * - 3 cards: row 1 has 2 cards, row 2 has 1 card
 * - 4 cards: 2x2 grid
 * - 5 cards: row 1 has 2, row 2 has 2, row 3 has 1
 * - 6 cards: 3 rows x 2 cols
 */
function VisualizationGrid({
  cardMessages,
}: {
  cardMessages: { message: ChatMessage; index: number; card: CardState }[];
}) {
  const count = cardMessages.length;

  if (count === 0) return null;

  // For 1 or 2 cards: stack vertically at full width
  if (count <= 2) {
    return (
      <div className="flex flex-col gap-4">
        {cardMessages.map(({ message, index, card }) => (
          <div key={message.id} className="w-full">
            <DraggableCard card={card} index={index} />
          </div>
        ))}
      </div>
    );
  }

  // For 3+ cards: arrange in rows of 2
  const rows: { message: ChatMessage; index: number; card: CardState }[][] = [];
  for (let i = 0; i < count; i += 2) {
    rows.push(cardMessages.slice(i, i + 2));
  }

  return (
    <div className="flex flex-col gap-4">
      {rows.map((row, rowIdx) => (
        <div key={rowIdx} className="grid grid-cols-2 gap-4">
          {row.map(({ message, index, card }) => (
            <div key={message.id} className="min-w-0">
              <DraggableCard card={card} index={index} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const MAX_VISUALIZATIONS = 6;

export function ChatThread() {
  const chatThread = useSessionStore((s) => s.chatThread);
  const cards = useSessionStore((s) => s.cards);
  const loading = useSessionStore((s) => s.loading);
  const [showMaxModal, setShowMaxModal] = useState(false);

  // Auto-scroll ref
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive or loading state changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatThread.length, loading]);

  // Check if we exceeded max visualizations
  const allCards = Object.values(cards);
  useEffect(() => {
    if (allCards.length > MAX_VISUALIZATIONS) {
      setShowMaxModal(true);
    }
  }, [allCards.length]);

  const handleDeleteCard = (cardId: string) => {
    // Remove card from store and its associated chat messages
    const state = useSessionStore.getState();
    const newCards = { ...state.cards };
    delete newCards[cardId];
    const newThread = state.chatThread.filter((msg) => msg.cardId !== cardId);
    useSessionStore.setState({ cards: newCards, chatThread: newThread });
    setShowMaxModal(false);
  };

  // Empty state
  if (chatThread.length === 0 && !loading) {
    return (
      <div
        className="flex flex-1 min-h-0 overflow-y-auto"
        aria-label="Chat thread"
      >
        <EmptyState />
      </div>
    );
  }

  // Separate card messages and error messages
  const cardMessages: { message: ChatMessage; index: number; card: CardState }[] = [];
  const errorMessages: { message: ChatMessage; index: number }[] = [];

  chatThread.forEach((message, idx) => {
    if (message.role === 'system' && message.cardId && cards[message.cardId]) {
      cardMessages.push({ message, index: idx, card: cards[message.cardId] });
    } else if (message.role === 'error') {
      errorMessages.push({ message, index: idx });
    }
  });

  return (
    <div
      className="flex flex-1 min-h-0 flex-col overflow-y-auto px-4 py-6 pb-24 gap-4"
      aria-label="Chat thread"
    >
      {/* Visualization Grid */}
      <VisualizationGrid cardMessages={cardMessages} />

      {/* Error messages below the grid */}
      {errorMessages.map(({ message }) => (
        <ErrorMessage key={message.id} message={message} />
      ))}

      {/* Typing indicator while loading */}
      {loading && <TypingIndicator />}

      {/* Scroll anchor */}
      <div ref={bottomRef} aria-hidden="true" />

      {/* Max visualizations modal */}
      {showMaxModal && allCards.length > MAX_VISUALIZATIONS && (
        <MaxVisualizationsModal
          cards={allCards}
          onDelete={handleDeleteCard}
          onCancel={() => setShowMaxModal(false)}
        />
      )}
    </div>
  );
}
