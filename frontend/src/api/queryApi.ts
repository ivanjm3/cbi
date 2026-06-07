import type { RenderedOutput } from '../types';

/** Discriminated union for query results */
export type QueryResult =
  | { ok: true; data: RenderedOutput; latencyMs: number }
  | {
      ok: false;
      status: number;
      error: { error_message?: string; error_code?: string; query_id?: string; message?: string; error?: string };
      latencyMs?: number;
    };

/** Session state returned from GET /sessions/:id */
export interface SessionResponse {
  id: string;
  chatThread: unknown[];
  cards: unknown[];
  [key: string]: unknown;
}

const API_BASE = 'http://localhost:8001';
const TIMEOUT_MS = 60_000;

/**
 * Sends a natural-language query to the backend and returns a typed result.
 * Implements a 60-second timeout via AbortController.
 * Handles HTTP 200, 422, 503/504 per the backend contract.
 * Computes fallback latency when `meta.latency_ms` is absent.
 */
export async function queryBackend(queryText: string): Promise<QueryResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const startTime = performance.now();

  try {
    const response = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query_text: queryText }),
      signal: controller.signal,
    });

    const elapsed = Math.round(performance.now() - startTime);
    const data = await response.json();

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: data,
        latencyMs: elapsed,
      };
    }

    // Backend puts latency in a top-level `latency` object (latency.total_ms)
    // and rendered_output.metadata may not include latency_ms.
    // We inject it so the Stats Panel can display it.
    const renderedOutput = data.rendered_output;
    const backendLatency = data.latency?.total_ms ?? renderedOutput?.metadata?.latency_ms ?? elapsed;

    if (renderedOutput?.metadata) {
      renderedOutput.metadata.latency_ms = backendLatency;
      renderedOutput.metadata.row_count = renderedOutput.metadata.row_count ?? data.latency?.row_count;
    }

    return {
      ok: true,
      data: renderedOutput,
      latencyMs: backendLatency,
    };
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      return {
        ok: false,
        status: 408,
        error: { error_message: 'Request timed out after 60s' },
      };
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * Fetches a persisted session from the backend.
 * Used when restoring a bookmarked session that references a server-side session id.
 */
export async function fetchSession(sessionId: string): Promise<SessionResponse> {
  const response = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch session ${sessionId}: HTTP ${response.status}`);
  }

  return response.json();
}
