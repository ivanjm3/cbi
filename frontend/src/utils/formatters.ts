/**
 * Utility formatters for latency badges and timestamps.
 * Requirements: 7.6, 8.2
 */

/**
 * Formats a latency value as a badge string.
 * Property 8: For any non-negative integer N, produces `↯ {N}ms`.
 */
export function formatLatency(n: number): string {
  return `↯ ${n}ms`;
}

/**
 * Formats a timestamp as either a relative time string (if <24h ago)
 * or an absolute "YYYY-MM-DD HH:mm" string (if >=24h ago).
 * Property 10: Timestamp display formatting.
 *
 * @param date - The timestamp to format (Date object or milliseconds since epoch)
 * @param now - Optional reference time for testing (defaults to current time)
 */
export function formatTimestamp(date: Date | number, now?: Date | number): string {
  const timestamp = date instanceof Date ? date.getTime() : date;
  const reference = now instanceof Date ? now.getTime() : (now ?? Date.now());
  const elapsedMs = reference - timestamp;

  const TWENTY_FOUR_HOURS = 24 * 60 * 60 * 1000;

  if (elapsedMs < TWENTY_FOUR_HOURS) {
    return formatRelative(elapsedMs);
  }

  return formatAbsolute(new Date(timestamp));
}

function formatRelative(elapsedMs: number): string {
  const seconds = Math.floor(elapsedMs / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);

  if (seconds < 60) {
    return 'just now';
  }

  if (minutes < 60) {
    return minutes === 1 ? '1 minute ago' : `${minutes} minutes ago`;
  }

  return hours === 1 ? '1 hour ago' : `${hours} hours ago`;
}

function formatAbsolute(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const mins = String(date.getMinutes()).padStart(2, '0');

  return `${year}-${month}-${day} ${hours}:${mins}`;
}
