import { describe, it, expect } from 'vitest';
import { formatLatency, formatTimestamp } from './formatters';

describe('formatLatency', () => {
  it('formats zero latency', () => {
    expect(formatLatency(0)).toBe('↯ 0ms');
  });

  it('formats typical latency values', () => {
    expect(formatLatency(234)).toBe('↯ 234ms');
    expect(formatLatency(1500)).toBe('↯ 1500ms');
  });

  it('formats large latency values', () => {
    expect(formatLatency(60000)).toBe('↯ 60000ms');
  });
});

describe('formatTimestamp', () => {
  const now = new Date('2025-06-15T12:00:00Z');

  describe('relative time (< 24 hours)', () => {
    it('formats as "just now" for sub-second differences', () => {
      const date = new Date(now.getTime() - 500);
      expect(formatTimestamp(date, now)).toBe('just now');
    });

    it('formats seconds ago', () => {
      const date = new Date(now.getTime() - 30 * 1000);
      expect(formatTimestamp(date, now)).toBe('30 seconds ago');
    });

    it('formats singular second', () => {
      const date = new Date(now.getTime() - 1000);
      expect(formatTimestamp(date, now)).toBe('1 second ago');
    });

    it('formats minutes ago', () => {
      const date = new Date(now.getTime() - 5 * 60 * 1000);
      expect(formatTimestamp(date, now)).toBe('5 minutes ago');
    });

    it('formats singular minute', () => {
      const date = new Date(now.getTime() - 60 * 1000);
      expect(formatTimestamp(date, now)).toBe('1 minute ago');
    });

    it('formats hours ago', () => {
      const date = new Date(now.getTime() - 3 * 60 * 60 * 1000);
      expect(formatTimestamp(date, now)).toBe('3 hours ago');
    });

    it('formats singular hour', () => {
      const date = new Date(now.getTime() - 60 * 60 * 1000);
      expect(formatTimestamp(date, now)).toBe('1 hour ago');
    });

    it('formats 23 hours ago as relative', () => {
      const date = new Date(now.getTime() - 23 * 60 * 60 * 1000);
      expect(formatTimestamp(date, now)).toBe('23 hours ago');
    });
  });

  describe('absolute time (>= 24 hours)', () => {
    it('formats as YYYY-MM-DD HH:mm at exactly 24 hours', () => {
      const date = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      const result = formatTimestamp(date, now);
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    });

    it('formats an old date correctly', () => {
      const date = new Date('2024-03-05T09:30:00');
      const result = formatTimestamp(date, now);
      expect(result).toBe('2024-03-05 09:30');
    });

    it('pads single-digit month and day', () => {
      const date = new Date('2024-01-02T08:05:00');
      const result = formatTimestamp(date, now);
      expect(result).toBe('2024-01-02 08:05');
    });
  });

  describe('edge cases', () => {
    it('formats future dates as absolute time', () => {
      const date = new Date(now.getTime() + 60 * 60 * 1000);
      const result = formatTimestamp(date, now);
      // Future dates have negative diff, so they go to absolute format
      expect(result).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
    });
  });
});
