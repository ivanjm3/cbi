/**
 * Utility formatters for latency badges and timestamps.
 * Requirements: 7.6, 8.2
 */

/**
 * Formats a latency value in milliseconds as a badge string.
 * @param n - Non-negative integer representing milliseconds
 * @returns Formatted string like "↯ 234ms"
 *
 * Validates: Requirements 7.6
 */
export function formatLatency(n: number): string {
  return `↯ ${n}ms`;
}

/**
 * Formats a timestamp as relative time if less than 24 hours ago,
 * or as "YYYY-MM-DD HH:mm" for older timestamps.
 * @param date - The date to format
 * @param now - Optional reference "now" time for testing (defaults to current time)
 * @returns Formatted time string
 *
 * Validates: Requirements 8.2
 */
export function formatTimestamp(date: Date, now: Date = new Date()): string {
  const diffMs = now.getTime() - date.getTime();
  const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000;

  if (diffMs < TWENTY_FOUR_HOURS_MS && diffMs >= 0) {
    return formatRelativeTime(diffMs);
  }

  return formatAbsoluteTime(date);
}

/**
 * Formats a millisecond difference as a human-readable relative time string.
 */
function formatRelativeTime(diffMs: number): string {
  const seconds = Math.floor(diffMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (hours >= 1) {
    return hours === 1 ? '1 hour ago' : `${hours} hours ago`;
  }
  if (minutes >= 1) {
    return minutes === 1 ? '1 minute ago' : `${minutes} minutes ago`;
  }
  if (seconds >= 1) {
    return seconds === 1 ? '1 second ago' : `${seconds} seconds ago`;
  }
  return 'just now';
}

/**
 * Formats a date as "YYYY-MM-DD HH:mm".
 */
function formatAbsoluteTime(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const mins = String(date.getMinutes()).padStart(2, '0');

  return `${year}-${month}-${day} ${hours}:${mins}`;
}
