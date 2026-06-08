/**
 * ChatThread component.
 *
 * Displays a vertical scrolling conversational thread with:
 * - User messages as right-aligned blue bubbles with white text
 * - System responses as left-aligned blocks with inline VisualizationCards
 * - Error messages as left-aligned with error styling and optional retry button
 * - Auto-scroll to newest message on new response
 * - Empty state when no messages: centered prompt to submit a query
 * - Streaming/typing indicator as left-aligned placeholder while loading
 *
 * Requirements: 1.5, 1.8, 2.6, 2.7, 2.8, 9.3, 9.4, 9.5
 */

import { useEffect, useRef } from 'react';
import { useSessionStore } from '../store/sessionStore';
import { DraggableCard } from './DraggableCard';
import { ErrorMessage } from './ErrorMessage';
import type { ChatMessage } from '../types';

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

/** User message — right-aligned blue bubble with white text */
function UserMessageBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end" aria-label="User message">
      <div className="max-w-[70%] rounded-2xl rounded-br-sm bg-bubble-user px-4 py-2.5 shadow-card">
        <p className="text-sm text-text-inverse leading-relaxed whitespace-pre-wrap break-words">
          {message.content}
        </p>
        <time className="block mt-1 text-xs text-blue-200 text-right">
          {formatTime(message.timestamp)}
        </time>
      </div>
    </div>
  );
}

/** System response — left-aligned block containing the VisualizationCard inline */
function SystemResponseBlock({ message, index }: { message: ChatMessage; index: number }) {
  const cards = useSessionStore((s) => s.cards);
  const card = message.cardId ? cards[message.cardId] : undefined;

  return (
    <div className="flex justify-start" aria-label="System response">
      <div className="max-w-[85%] w-full">
        {card ? (
          <DraggableCard card={card} index={index} />
        ) : (
          <div className="rounded-2xl rounded-bl-sm bg-bubble-system border border-border-default px-4 py-2.5 shadow-card">
            <p className="text-sm text-text-primary leading-relaxed whitespace-pre-wrap break-words">
              {message.content}
            </p>
            <time className="block mt-1 text-xs text-text-muted">
              {formatTime(message.timestamp)}
            </time>
          </div>
        )}
      </div>
    </div>
  );
}



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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Formats a timestamp into a short time string (HH:mm) */
function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ChatThread() {
  const chatThread = useSessionStore((s) => s.chatThread);
  const loading = useSessionStore((s) => s.loading);

  // Auto-scroll ref
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive or loading state changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatThread.length, loading]);

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

  return (
    <div
      className="flex flex-1 min-h-0 flex-col overflow-y-auto px-4 py-6 gap-4"
      aria-label="Chat thread"
    >
      {chatThread.map((message, idx) => {
        switch (message.role) {
          case 'user':
            return <UserMessageBubble key={message.id} message={message} />;
          case 'system':
            return <SystemResponseBlock key={message.id} message={message} index={idx} />;
          case 'error':
            return <ErrorMessage key={message.id} message={message} />;
          default:
            return null;
        }
      })}

      {/* Typing indicator while loading */}
      {loading && <TypingIndicator />}

      {/* Scroll anchor */}
      <div ref={bottomRef} aria-hidden="true" />
    </div>
  );
}
