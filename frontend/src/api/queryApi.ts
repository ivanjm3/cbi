/**
 * API integration layer for the Conversational BI backend.
 * Implements the query and session endpoints with timeout and error handling.
 */

import type { RenderedOutput } from '../types';

export const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? 'http://localhost:8001' : '');
export const TIMEOUT_MS = 120_000;

/** Discriminated union for query results */
export type QueryResult =
  | { ok: true; data: RenderedOutput; latencyMs: number }
  | { ok: false; status: number; error: { error_message?: string; [key: string]: unknown }; latencyMs?: number };

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
        error: data as { error_message?: string; [key: string]: unknown },
        latencyMs: elapsed,
      };
    }

    return {
      ok: true,
      data: data.rendered_output as RenderedOutput,
      latencyMs: data.rendered_output?.metadata?.latency_ms ?? elapsed,
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
 * Fetch a server-persisted session by ID.
 * Used when restoring a saved prompt that references a server session.
 *
 * Returns the response data on success, or null on any error.
 */
export async function fetchSession(id: string): Promise<unknown | null> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    const response = await fetch(`${API_BASE}/sessions/${encodeURIComponent(id)}`, {
      method: 'GET',
      headers: { 'Accept': 'application/json' },
      signal: controller.signal,
    });

    if (!response.ok) {
      return null;
    }

    const data = await response.json();
    return data;
  } catch {
    return null;
  } finally {
    clearTimeout(timeoutId);
  }
}
