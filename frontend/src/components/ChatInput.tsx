/**
 * ChatInput placeholder component.
 *
 * Provides a basic text input and submit button that calls store.submitQuery.
 * Will be fully implemented in task 6.2 with voice input, character limit, etc.
 *
 * Requirements: 2.1, 2.2, 2.3
 */

import { useState } from 'react';
import { useSessionStore } from '../store/sessionStore';

export function ChatInput() {
  const [input, setInput] = useState('');
  const submitQuery = useSessionStore((s) => s.submitQuery);
  const loading = useSessionStore((s) => s.loading);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading) return;
    submitQuery(trimmed);
    setInput('');
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-center gap-2 border-t border-border-default bg-bg-secondary px-4 py-3"
      aria-label="Chat input"
    >
      <input
        type="text"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        placeholder="Ask a question about your data..."
        maxLength={500}
        disabled={loading}
        className="flex-1 rounded-lg border border-border-default bg-bg-input px-4 py-2 text-base text-text-primary placeholder:text-text-muted focus:border-accent-primary focus:outline-none focus:ring-1 focus:ring-accent-primary disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={loading || !input.trim()}
        className="rounded-lg bg-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        Send
      </button>
    </form>
  );
}
