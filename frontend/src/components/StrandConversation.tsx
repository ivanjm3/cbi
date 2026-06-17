/**
 * StrandConversation component — Multi-turn conversation panel for visualization cards.
 *
 * Behaves exactly like the main ChatInput bar but:
 * - State stored via strands (not global chatThread)
 * - Collapsible message history above the input
 * - Auto-creates strand on first submit
 *
 * Requirements: 10.6 (multi-turn conversation on cards)
 */

import { useCallback, useRef, useState, useEffect } from 'react';
import type { ConversationStrand, ChatMessage } from '../types';
import { useSessionStore } from '../store/sessionStore';

export interface StrandConversationProps {
  cardId: string;
  strand: ConversationStrand | null;
  isLoading?: boolean;
}

function MessageItem({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-2 mb-3 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] px-3 py-2 rounded-lg text-sm ${
          isUser
            ? 'bg-accent-primary text-white rounded-br-none'
            : 'bg-bg-input text-text-primary rounded-bl-none'
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        <p className="text-xs mt-1 opacity-70">
          {new Date(message.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
}

export function StrandConversation({
  cardId,
  strand: strandProp,
  isLoading,
}: StrandConversationProps) {
  const createStrand = useSessionStore((s) => s.createStrand);
  const submitFollowUpQuery = useSessionStore((s) => s.submitFollowUpQuery);
  const cancelQuery = useSessionStore((s) => s.cancelQuery);

  // Subscribe to strands from store directly to get live updates
  const strandFromStore = useSessionStore((s) => {
    const found = Object.values(s.strands).find((st) => st.cardId === cardId);
    return found || null;
  });

  const currentStrand = strandFromStore || strandProp;

  const [input, setInput] = useState('');
  const [chatOpen, setChatOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when messages update
  useEffect(() => {
    if (chatOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [currentStrand?.messages?.length, chatOpen]);

  // Auto-open chat when messages arrive
  useEffect(() => {
    if (currentStrand && currentStrand.messages.length > 0 && !chatOpen) {
      setChatOpen(true);
    }
  }, [currentStrand?.messages?.length]);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      const trimmed = input.trim();
      if (!trimmed || isLoading) return;

      setInput('');

      let strandId = currentStrand?.id;
      if (!strandId) {
        strandId = createStrand(cardId);
      }

      if (!chatOpen) setChatOpen(true);

      await submitFollowUpQuery(strandId, trimmed);

      setTimeout(() => inputRef.current?.focus(), 100);
    },
    [input, isLoading, currentStrand, cardId, chatOpen, createStrand, submitFollowUpQuery],
  );

  const handleCancel = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      cancelQuery();
    },
    [cancelQuery],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter' && !e.shiftKey && !isLoading) {
        e.preventDefault();
        const trimmed = input.trim();
        if (!trimmed) return;
        setInput('');

        let strandId = currentStrand?.id;
        if (!strandId) {
          strandId = createStrand(cardId);
        }
        if (!chatOpen) setChatOpen(true);
        submitFollowUpQuery(strandId, trimmed);
        setTimeout(() => inputRef.current?.focus(), 100);
      }
    },
    [input, isLoading, currentStrand, cardId, chatOpen, createStrand, submitFollowUpQuery],
  );

  const canSubmit = !!input.trim() && !isLoading;
  const hasMessages = currentStrand && currentStrand.messages.length > 0;

  return (
    <div className="mt-3 pt-3">
      {/* Collapsible chat history */}
      {hasMessages && (
        <div className="mb-3">
          <button
            type="button"
            onClick={() => setChatOpen(!chatOpen)}
            className="flex items-center gap-1.5 text-xs text-text-muted hover:text-text-secondary transition-colors mb-2"
          >
            <svg
              className="h-3 w-3 transition-transform"
              style={{ transform: chatOpen ? 'rotate(90deg)' : 'rotate(0deg)' }}
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M6 4L10 8L6 12" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <span>Chat ({currentStrand!.messages.length})</span>
          </button>

          {chatOpen && (
            <div className="max-h-60 overflow-y-auto rounded-lg bg-bg-input/30 p-3">
              {currentStrand!.messages.map((msg) => (
                <MessageItem key={msg.id} message={msg} />
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      )}

      {/* Query bar — identical behavior to main ChatInput */}
      <form
        onSubmit={isLoading ? handleCancel : handleSubmit}
        className="flex items-center gap-2 rounded-xl border border-border-default bg-bg-secondary/95 px-3 py-2"
        aria-label="Follow-up query input"
      >
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a follow-up question..."
          maxLength={500}
          disabled={isLoading}
          autoComplete="off"
          spellCheck="true"
          aria-label="Follow-up query"
          className="flex-1 rounded-lg border border-border-default bg-bg-input px-3 py-1.5 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary disabled:opacity-50"
        />

        {/* Submit or Cancel button */}
        {isLoading ? (
          <button
            type="submit"
            aria-label="Cancel query"
            className="flex-shrink-0 rounded-lg bg-status-error px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-status-error/80 focus:outline-none focus:ring-2 focus:ring-status-error focus:ring-offset-1"
          >
            <svg viewBox="0 0 24 24" fill="currentColor" className="h-4 w-4" aria-hidden="true">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSubmit}
            aria-label="Submit follow-up"
            className="flex-shrink-0 rounded-lg bg-accent-primary px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4" aria-hidden="true">
              <path d="m22 2-7 20-4-9-9-4Z" />
              <path d="M22 2 11 13" />
            </svg>
          </button>
        )}
      </form>
    </div>
  );
}
