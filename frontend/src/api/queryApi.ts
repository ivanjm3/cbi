/**
 * API integration layer for the Conversational BI backend.
 * Implements the query and session endpoints with timeout and error handling.
 */

import type { RenderedOutput } from '../types';

export const API_BASE = 'http://localhost:8001';
export const TIMEOUT_MS = 120_000;

/** Error shape returned by the backend on non-200 responses */
export interface ApiError {
  error_message?: string;
  error_code?: string;
  query_id?: string;
}

/** Discriminated union for query results */
export type QueryResult =
  | { ok: true; data: RenderedOutput; latencyMs: number }
  | { ok: false; status: number; error: ApiError; latencyMs?: number };

/**
 * Send a query to the backend NLP translator.
 * Returns a discriminated union result for success/failure handling.
 *
 * - 60-second timeout via AbortController
 * - HTTP 200: extracts rendered_output and computes latency (from meta or elapsed)
 * - HTTP 422: returns error payload with inline error message
 * - HTTP 503/504: returns error payload for service unavailability
 * - Timeout: returns synthetic 408 with descriptive message
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
        error: data as ApiError,
        latencyMs: elapsed,
      };
    }

    return {
      ok: true,
      data: data.rendered_output ?? data,
      latencyMs: data.rendered_output?.metadata?.latency_ms ?? data.metadata?.latency_ms ?? elapsed,
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

/** Response shape for the sessions endpoint */
export interface SessionResponse {
  id: string;
  chat_thread: Array<{
    id: string;
    role: 'user' | 'system' | 'error';
    content: string;
    card_id?: string;
    timestamp: number;
  }>;
  cards: Array<{
    id: string;
    query: string;
    rendered_output: RenderedOutput;
    grid_position: { col: number; row: number };
    grid_size: { col_span: 1 | 2; row_span: 1 | 2 };
    pinned: boolean;
    bookmarked: boolean;
    created_at: number;
  }>;
  workspace_name?: string;
}

/** Result type for fetchSession */
export type SessionResult =
  | { ok: true; data: SessionResponse }
  | { ok: false; status: number; error: ApiError };

/**
 * Fetch a server-persisted session by ID.
 * Used when restoring a bookmarked session that references a server session.
 *
 * - 60-second timeout via AbortController
 * - Returns the session payload on success
 * - Returns error information on failure
 */
export async function fetchSession(sessionId: string): Promise<SessionResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/sessions/${encodeURIComponent(sessionId)}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      signal: controller.signal,
    });

    const data = await response.json();

    if (!response.ok) {
      return {
        ok: false,
        status: response.status,
        error: data as ApiError,
      };
    }

    return {
      ok: true,
      data: data as SessionResponse,
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
