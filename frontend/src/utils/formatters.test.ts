import { describe, it, expect } from 'vitest';
import { formatLatency, formatTimestamp } from './formatters';

describe('formatLatency', () => {
  it('formats zero latency', () => {
    expect(formatLatency(0)).toBe('↯ 0ms');
  });

  it('formats small latency', () => {
    expect(formatLatency(5)).toBe('↯ 5ms');
  });

  it('formats typical latency', () => {
    expect(formatLatency(2340)).toBe('↯ 2340ms');
  });

  it('formats large latency', () => {
    expect(formatLatency(99999)).toBe('↯ 99999ms');
  });
});

describe('formatTimestamp', () => {
  const NOW = new Date('2025-06-15T12:00:00Z').getTime();

  describe('relative time (<24h)', () => {
    it('returns "just now" for timestamps less than 60 seconds ago', () => {
      const thirtySecsAgo = NOW - 30 * 1000;
      expect(formatTimestamp(thirtySecsAgo, NOW)).toBe('just now');
    });

    it('returns "just now" for zero elapsed time', () => {
      expect(formatTimestamp(NOW, NOW)).toBe('just now');
    });

    it('returns "1 minute ago" for exactly 60 seconds', () => {
      const oneMinAgo = NOW - 60 * 1000;
      expect(formatTimestamp(oneMinAgo, NOW)).toBe('1 minute ago');
    });

    it('returns plural minutes for multiple minutes', () => {
      const fiveMinAgo = NOW - 5 * 60 * 1000;
      expect(formatTimestamp(fiveMinAgo, NOW)).toBe('5 minutes ago');
    });

    it('returns "1 hour ago" for exactly 60 minutes', () => {
      const oneHourAgo = NOW - 60 * 60 * 1000;
      expect(formatTimestamp(oneHourAgo, NOW)).toBe('1 hour ago');
    });

    it('returns plural hours for multiple hours', () => {
      const twoHoursAgo = NOW - 2 * 60 * 60 * 1000;
      expect(formatTimestamp(twoHoursAgo, NOW)).toBe('2 hours ago');
    });

    it('returns relative time for 23 hours ago', () => {
      const twentyThreeHoursAgo = NOW - 23 * 60 * 60 * 1000;
      expect(formatTimestamp(twentyThreeHoursAgo, NOW)).toBe('23 hours ago');
    });
  });

  describe('absolute time (>=24h)', () => {
    it('returns YYYY-MM-DD HH:mm for exactly 24 hours ago', () => {
      const twentyFourHoursAgo = NOW - 24 * 60 * 60 * 1000;
      const result = formatTimestamp(twentyFourHoursAgo, NOW);
      // Should match YYYY-MM-DD HH:mm pattern
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    });

    it('returns correct absolute format for a known date', () => {
      // Use a fixed date and fixed "now" to avoid timezone issues
      const date = new Date('2025-01-10T08:30:00Z');
      const now = new Date('2025-06-15T12:00:00Z');
      const result = formatTimestamp(date, now);
      // The result depends on local timezone, so just verify the format
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    });

    it('returns absolute format for old timestamps', () => {
      const oldDate = NOW - 7 * 24 * 60 * 60 * 1000; // 1 week ago
      const result = formatTimestamp(oldDate, NOW);
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    });
  });

  describe('input types', () => {
    it('accepts Date objects', () => {
      const date = new Date(NOW - 5 * 60 * 1000);
      expect(formatTimestamp(date, NOW)).toBe('5 minutes ago');
    });

    it('accepts numeric timestamps', () => {
      const timestamp = NOW - 5 * 60 * 1000;
      expect(formatTimestamp(timestamp, NOW)).toBe('5 minutes ago');
    });

    it('accepts Date object for now parameter', () => {
      const date = NOW - 5 * 60 * 1000;
      const now = new Date(NOW);
      expect(formatTimestamp(date, now)).toBe('5 minutes ago');
    });

    it('defaults now to current time when omitted', () => {
      // A timestamp from 5 minutes ago should return relative time
      const fiveMinAgo = Date.now() - 5 * 60 * 1000;
      expect(formatTimestamp(fiveMinAgo)).toBe('5 minutes ago');
    });
  });
});
