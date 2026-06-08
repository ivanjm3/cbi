/**
 * Unit tests for the API integration layer.
 * Tests queryBackend and fetchSession with mocked fetch.
 */

import { describe, it, expect, vi, afterEach } from 'vitest';
import { queryBackend, fetchSession, API_BASE } from './queryApi';
import type { RenderedOutput } from '../types';

// Store original fetch
const originalFetch = globalThis.fetch;

afterEach(() => {
  vi.restoreAllMocks();
  globalThis.fetch = originalFetch;
});

describe('queryBackend', () => {
  const mockRenderedOutput: RenderedOutput = {
    output_type: 'chart',
    chart_type: 'bar',
    chart_data: { labels: ['A', 'B'], datasets: [{ data: [1, 2] }] },
    text_content: null,
    description: 'Test chart',
    metadata: {
      query_id: 'test-123',
      query_type: 'aggregation',
      latency_ms: 200,
      row_count: 2,
    },
  };

  it('should send POST request with correct body and headers', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ rendered_output: mockRenderedOutput }),
    });
    globalThis.fetch = mockFetch;

    await queryBackend('show revenue');

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE}/query`,
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query_text: 'show revenue' }),
      }),
    );
  });

  it('should return ok result with rendered_output data on HTTP 200', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ rendered_output: mockRenderedOutput }),
    });

    const result = await queryBackend('show revenue');

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(mockRenderedOutput);
    }
  });

  it('should use metadata.latency_ms when available', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ rendered_output: mockRenderedOutput }),
    });

    const result = await queryBackend('show revenue');

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.latencyMs).toBe(200); // from metadata.latency_ms
    }
  });

  it('should use elapsed time as fallback when metadata.latency_ms is absent', async () => {
    const outputWithoutLatency: RenderedOutput = {
      ...mockRenderedOutput,
      metadata: {
        query_id: 'test-456',
        query_type: 'aggregation',
      },
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ rendered_output: outputWithoutLatency }),
    });

    const result = await queryBackend('show revenue');

    expect(result.ok).toBe(true);
    if (result.ok) {
      // latencyMs should be a number (elapsed time from performance.now)
      expect(typeof result.latencyMs).toBe('number');
      expect(result.latencyMs).toBeGreaterThanOrEqual(0);
    }
  });

  it('should return error result on HTTP 422', async () => {
    const errorBody = {
      error_code: 'UNPARSEABLE_QUERY',
      error_message: 'Could not interpret your question.',
      query_id: 'err-789',
    };

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => errorBody,
    });

    const result = await queryBackend('gibberish');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(422);
      expect(result.error.error_code).toBe('UNPARSEABLE_QUERY');
      expect(result.error.error_message).toBe('Could not interpret your question.');
      expect(result.error.query_id).toBe('err-789');
      expect(typeof result.latencyMs).toBe('number');
    }
  });

  it('should return error result on HTTP 503', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ error_message: 'Service unavailable' }),
    });

    const result = await queryBackend('show revenue');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(503);
      expect(result.error.error_message).toBe('Service unavailable');
    }
  });

  it('should return error result on HTTP 504', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 504,
      json: async () => ({ error_message: 'Gateway timeout' }),
    });

    const result = await queryBackend('show revenue');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(504);
      expect(result.error.error_message).toBe('Gateway timeout');
    }
  });

  it('should return 408 when fetch is aborted (simulates timeout)', async () => {
    const abortError = new Error('The operation was aborted.');
    abortError.name = 'AbortError';
    globalThis.fetch = vi.fn().mockRejectedValue(abortError);

    const result = await queryBackend('slow query');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(408);
      expect(result.error.error_message).toBe('Request timed out after 60s');
      expect(result.latencyMs).toBeUndefined();
    }
  });

  it('should pass AbortController signal to fetch', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ rendered_output: mockRenderedOutput }),
    });
    globalThis.fetch = mockFetch;

    await queryBackend('show revenue');

    const callArgs = mockFetch.mock.calls[0][1];
    expect(callArgs.signal).toBeInstanceOf(AbortSignal);
  });

  it('should rethrow non-abort errors', async () => {
    const networkError = new Error('Network failure');
    globalThis.fetch = vi.fn().mockRejectedValue(networkError);

    await expect(queryBackend('show revenue')).rejects.toThrow('Network failure');
  });
});

describe('fetchSession', () => {
  const mockSessionData = {
    id: 'session-abc',
    chat_thread: [
      { id: 'msg-1', role: 'user' as const, content: 'hello', timestamp: 1000 },
    ],
    cards: [],
    workspace_name: 'Test Workspace',
  };

  it('should send GET request to /sessions/:id', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSessionData,
    });
    globalThis.fetch = mockFetch;

    await fetchSession('session-abc');

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE}/sessions/session-abc`,
      expect.objectContaining({
        method: 'GET',
        headers: { 'Accept': 'application/json' },
      }),
    );
  });

  it('should URL-encode the session ID', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSessionData,
    });
    globalThis.fetch = mockFetch;

    await fetchSession('session/with spaces');

    expect(mockFetch).toHaveBeenCalledWith(
      `${API_BASE}/sessions/session%2Fwith%20spaces`,
      expect.anything(),
    );
  });

  it('should return ok result with session data on HTTP 200', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => mockSessionData,
    });

    const result = await fetchSession('session-abc');

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.id).toBe('session-abc');
      expect(result.data.chat_thread).toHaveLength(1);
      expect(result.data.workspace_name).toBe('Test Workspace');
    }
  });

  it('should return error result on HTTP 404', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error_message: 'Session not found' }),
    });

    const result = await fetchSession('nonexistent');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.error.error_message).toBe('Session not found');
    }
  });

  it('should return 408 when fetch is aborted (simulates timeout)', async () => {
    const abortError = new Error('The operation was aborted.');
    abortError.name = 'AbortError';
    globalThis.fetch = vi.fn().mockRejectedValue(abortError);

    const result = await fetchSession('session-abc');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(408);
      expect(result.error.error_message).toBe('Request timed out after 60s');
    }
  });

  it('should rethrow non-abort errors', async () => {
    const networkError = new Error('Network failure');
    globalThis.fetch = vi.fn().mockRejectedValue(networkError);

    await expect(fetchSession('session-abc')).rejects.toThrow('Network failure');
  });
});
