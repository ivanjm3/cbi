/**
 * ErrorCard component.
 *
 * Renders inline error messages in the conversational thread:
 * - HTTP 422: shows error_message from response; preserves prompt
 * - HTTP 503/504: shows service unavailability with retry button
 * - Timeout (408): shows timeout message with retry button
 *
 * Requirements: 9.3, 9.4, 9.5
 */

import { useCallback } from 'react';
import { useSessionStore } from '../store/sessionStore';

export interface ErrorCardProps {
  /** The error message to display */
  message: string;
  /** HTTP status code (422, 503, 504, 408) */
  statusCode?: number;
  /** The original query text, used for retry */
  originalQuery?: string;
}

export function ErrorCard({ message, statusCode, originalQuery }: ErrorCardProps) {
  const submitQuery = useSessionStore((s) => s.submitQuery);

  const isRetryable =
    statusCode === 503 || statusCode === 504 || statusCode === 408;

  const handleRetry = useCallback(() => {
    if (originalQuery) {
      submitQuery(originalQuery);
    }
  }, [originalQuery, submitQuery]);

  const statusLabel =
    statusCode === 422
      ? 'Query Error'
      : statusCode === 503 || statusCode === 504
        ? 'Service Unavailable'
        : statusCode === 408
          ? 'Request Timeout'
          : 'Error';

  return (
    <div
      role="alert"
      aria-live="polite"
      className="rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-4"
    >
      <div className="flex items-start gap-3">
        {/* Error icon */}
        <div className="flex-shrink-0 mt-0.5">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5 text-red-500 dark:text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
        </div>

        {/* Error content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-red-800 dark:text-red-300">
            {statusLabel}
          </p>
          <p className="mt-1 text-sm text-red-700 dark:text-red-400">
            {message}
          </p>

          {/* Retry button for retryable errors */}
          {isRetryable && originalQuery && (
            <button
              type="button"
              onClick={handleRetry}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md bg-red-100 dark:bg-red-900/40 px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/60 transition-colors"
              aria-label="Retry query"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-3.5 w-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
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
        </div>
      </div>
    </div>
  );
}
