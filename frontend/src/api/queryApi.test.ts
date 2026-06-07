import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { queryBackend, fetchSession } from './queryApi';

describe('queryBackend', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('performance', { now: vi.fn() });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('returns success result on HTTP 200', async () => {
    const mockRenderedOutput = {
      output_type: 'chart',
      chart_type: 'bar',
      chart_data: { labels: ['A'], datasets: [{ data: [1] }] },
      text_content: null,
      description: 'Test chart',
      metadata: {
        query_id: 'q-123',
        query_type: 'aggregation',
        latency_ms: 500,
        row_count: 1,
        columns: [],
        timestamp: '2025-01-15T10:30:00Z',
        data_sources: ['test'],
      },
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ rendered_output: mockRenderedOutput }),
    }));

    const perf = vi.mocked(performance.now);
    perf.mockReturnValueOnce(0).mockReturnValueOnce(300);

    const result = await queryBackend('show revenue');

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(mockRenderedOutput);
      expect(result.latencyMs).toBe(500); // uses meta.latency_ms
    }
  });

  it('computes fallback latency when meta.latency_ms is absent', async () => {
    const mockRenderedOutput = {
      output_type: 'text',
      text_content: 'Hello',
      description: 'Test text',
      metadata: {
        query_id: 'q-456',
        query_type: 'text',
        // no latency_ms
      },
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ rendered_output: mockRenderedOutput }),
    }));

    const perf = vi.mocked(performance.now);
    perf.mockReturnValueOnce(100).mockReturnValueOnce(450);

    const result = await queryBackend('hello');

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.latencyMs).toBe(350); // fallback: elapsed time
    }
  });

  it('returns error result on HTTP 422', async () => {
    const errorBody = {
      error_code: 'UNPARSEABLE_QUERY',
      error_message: 'Could not interpret your question.',
      query_id: 'q-789',
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: () => Promise.resolve(errorBody),
    }));

    const perf = vi.mocked(performance.now);
    perf.mockReturnValueOnce(0).mockReturnValueOnce(200);

    const result = await queryBackend('asdlkfj');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(422);
      expect(result.error.error_message).toBe('Could not interpret your question.');
      expect(result.error.error_code).toBe('UNPARSEABLE_QUERY');
      expect(result.latencyMs).toBe(200);
    }
  });

  it('returns error result on HTTP 503', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: () => Promise.resolve({ error_message: 'Service unavailable' }),
    }));

    const perf = vi.mocked(performance.now);
    perf.mockReturnValueOnce(0).mockReturnValueOnce(100);

    const result = await queryBackend('test');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(503);
      expect(result.error.error_message).toBe('Service unavailable');
    }
  });

  it('returns timeout error when request exceeds 60s', async () => {
    const abortError = new Error('The operation was aborted');
    abortError.name = 'AbortError';

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abortError));

    const perf = vi.mocked(performance.now);
    perf.mockReturnValueOnce(0);

    const result = await queryBackend('slow query');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(408);
      expect(result.error.error_message).toBe('Request timed out after 60s');
    }
  });

  it('re-throws non-abort errors', async () => {
    const networkError = new Error('Network failure');

    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(networkError));

    const perf = vi.mocked(performance.now);
    perf.mockReturnValueOnce(0);

    await expect(queryBackend('test')).rejects.toThrow('Network failure');
  });

  it('sends correct request format to backend', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        rendered_output: {
          output_type: 'text',
          description: 'test',
          metadata: { query_id: '1', query_type: 'test' },
        },
      }),
    });
    vi.stubGlobal('fetch', mockFetch);

    const perf = vi.mocked(performance.now);
    perf.mockReturnValueOnce(0).mockReturnValueOnce(50);

    await queryBackend('show revenue by region');

    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8001/query',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query_text: 'show revenue by region' }),
      }),
    );
  });
});

describe('fetchSession', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('returns session data on successful response', async () => {
    const mockSession = {
      id: 'session-1',
      chatThread: [{ id: 'm1', role: 'user', content: 'hello', timestamp: 1 }],
      cards: [],
    };

    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockSession),
    }));

    const result = await fetchSession('session-1');

    expect(result).toEqual(mockSession);
    expect(fetch).toHaveBeenCalledWith('http://localhost:8001/sessions/session-1');
  });

  it('throws error on non-200 response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
    }));

    await expect(fetchSession('nonexistent')).rejects.toThrow(
      'Failed to fetch session nonexistent: HTTP 404',
    );
  });

  it('encodes session id in URL', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ id: 'a/b', chatThread: [], cards: [] }),
    });
    vi.stubGlobal('fetch', mockFetch);

    await fetchSession('a/b');

    expect(mockFetch).toHaveBeenCalledWith('http://localhost:8001/sessions/a%2Fb');
  });
});
