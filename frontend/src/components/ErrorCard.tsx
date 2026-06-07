import type { ChatMessage } from '../types';
import { useSessionStore } from '../store/sessionStore';

interface ErrorCardProps {
  message: ChatMessage;
}

/**
 * Determines if the error is retryable based on the HTTP status code.
 * 503/504 (service unavailable/gateway timeout) and 408 (client timeout) are retryable.
 */
function isRetryable(status?: number): boolean {
  if (!status) return false;
  return status === 503 || status === 504 || status === 408;
}

/**
 * Returns a user-friendly title for the error based on status code.
 */
function getErrorTitle(status?: number): string {
  switch (status) {
    case 422:
      return 'Could not process query';
    case 503:
    case 504:
      return 'Service temporarily unavailable';
    case 408:
      return 'Request timed out';
    default:
      return 'Something went wrong';
  }
}

/**
 * Returns a descriptive subtitle for the error based on status code.
 */
function getErrorSubtitle(status?: number): string {
  switch (status) {
    case 422:
      return 'The server could not interpret your query.';
    case 503:
    case 504:
      return 'The backend service is currently unavailable. Please try again.';
    case 408:
      return 'The request took too long to complete. Please try again.';
    default:
      return 'An unexpected error occurred.';
  }
}

/**
 * ErrorCard - Displays error messages inline in the conversational thread.
 *
 * Behavior per error type:
 * - HTTP 422: Shows `error_message` from response. No retry button. Prompt preserved.
 * - HTTP 503/504: Shows service unavailability message with a retry button.
 * - Timeout (408): Shows timeout message with a retry button.
 * - Other errors: Shows generic message with the error content.
 *
 * The retry button re-sends the identical POST /query request with the same query_text.
 *
 * Requirements: 9.3, 9.4, 9.5
 */
export default function ErrorCard({ message }: ErrorCardProps) {
  const submitQuery = useSessionStore((s) => s.submitQuery);
  const loading = useSessionStore((s) => s.loading);

  const { content, errorStatus, originalQuery } = message;
  const retryable = isRetryable(errorStatus);
  const title = getErrorTitle(errorStatus);
  const subtitle = getErrorSubtitle(errorStatus);

  const handleRetry = () => {
    if (originalQuery && !loading) {
      submitQuery(originalQuery);
    }
  };

  return (
    <div
      data-testid="error-card"
      role="alert"
      className="flex flex-col gap-2 rounded-lg border border-red-200 bg-red-50 p-4"
    >
      {/* Error icon and title */}
      <div className="flex items-center gap-2">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-5 w-5 flex-shrink-0 text-red-500"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <span className="text-sm font-semibold text-red-800">{title}</span>
      </div>

      {/* Error subtitle */}
      <p className="text-sm text-red-700">{subtitle}</p>

      {/* Error message content from backend */}
      {content && (
        <p className="text-sm text-red-600 italic" data-testid="error-message">
          {content}
        </p>
      )}

      {/* Retry button for 503/504 and timeout */}
      {retryable && originalQuery && (
        <div className="mt-1">
          <button
            type="button"
            onClick={handleRetry}
            disabled={loading}
            data-testid="error-retry-button"
            className="inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-3.5 w-3.5"
              aria-hidden="true"
            >
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            Retry
          </button>
        </div>
      )}
    </div>
  );
}
