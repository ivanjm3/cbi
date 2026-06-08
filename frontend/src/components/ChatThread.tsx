/**
 * ChatThread placeholder component.
 *
 * Displays an empty state message. Will be fully implemented in task 6.1
 * with user message bubbles, system responses, and inline visualization cards.
 *
 * Requirements: 1.5, 1.8
 */

export function ChatThread() {
  return (
    <div
      className="flex flex-1 min-h-0 items-center justify-center overflow-y-auto"
      aria-label="Chat thread"
    >
      <p className="text-text-secondary text-base">
        Ask a question to get started
      </p>
    </div>
  );
}
