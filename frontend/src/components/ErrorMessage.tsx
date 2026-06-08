/**
 * ErrorMessage component.
 *
 * Renders error messages as left-aligned blocks in the chat thread with:
 * - 422 errors: displays `error_message` from backend response; user prompt preserved in input
 * - 503/504 errors: displays service unavailability message with retry button
 * - Timeout (408) errors: displays timeout message with retry button
 * - Retry button re-sends identical `POST /query` request with same `query_text`
 *
 * Requirements: 9.3, 9.4, 9.5
 */

import { useCallback } from 'react';
import { useSessionStore } from '../store/sessionStore';
import type { ChatMessage } from '../types';

export interface ErrorMessageProps {
  message: ChatMessage;
}

/**
 * Formats a timestamp into a short time string (HH:mm).
 */
function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/**
 * ErrorMessage — left-aligned error block in the chat thread.
 *
 * Displays the error content with appropriate styling and an optional retry button
 * for retryable errors (503, 504, 408 timeout).
 */
export function ErrorMessage({ message }: ErrorMessageProps) {
  const submitQuery = useSessionStore((s) => s.submitQuery);

  const isRetryable =
    message.statusCode === 503 ||
    message.statusCode === 504 ||
    message.statusCode === 408;

  const handleRetry = useCallback(() => {
    if (message.originalQuery) {
      submitQuery(message.originalQuery);
    }
  }, [message.originalQuery, submitQuery]);

  const statusLabel =
    message.statusCode === 422
      ? 'Query Error'
      : message.statusCode === 503 || message.statusCode === 504
        ? 'Service Unavailable'
        : message.statusCode === 408
          ? 'Request Timeout'
          : 'Error';

  return (
    <div className="flex justify-start" aria-label="Error message">
      <div className="max-w-[70%]">
        <div
          role="alert"
          aria-live="polite"
          className="rounded-2xl rounded-bl-sm border border-red-200 bg-red-50 px-4 py-3 shadow-card"
        >
          <div className="flex items-start gap-2.5">
            {/* Error icon */}
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5 flex-shrink-0 mt-0.5 text-status-error"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>

            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-red-800 uppercase tracking-wide">
                {statusLabel}
              </p>
              <p className="mt-1 text-sm text-red-700 leading-relaxed whitespace-pre-wrap break-words">
                {message.content}
              </p>

              {/* Retry button for 503, 504, and timeout (408) errors */}
              {isRetryable && message.originalQuery && (
                <button
                  type="button"
                  onClick={handleRetry}
                  className="mt-2.5 inline-flex items-center gap-1.5 rounded-lg bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 hover:bg-red-200 transition-colors focus:outline-none focus:ring-2 focus:ring-red-300"
                  aria-label="Retry query"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-3.5 w-3.5"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                    />
                  </svg>
                  Retry
                </button>
              )}

              <time className="block mt-1.5 text-xs text-red-400">
                {formatTime(message.timestamp)}
              </time>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
