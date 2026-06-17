/**
 * API integration layer for the Conversational BI backend.
 * Implements the query and session endpoints with timeout and error handling.
 * Supports cooperative query cancellation with correlation IDs.
 */

import type { RenderedOutput } from '../types';

export const API_BASE = import.meta.env.VITE_API_BASE ?? (import.meta.env.DEV ? 'http://localhost:8001' : '');
export const TIMEOUT_MS = 120_000;

/** Discriminated union for query results */
export type QueryResult =
  | { ok: true; data: RenderedOutput; latencyMs: number }
  | { ok: false; status: number; error: { error_message?: string; [key: string]: unknown }; latencyMs?: number };

/**
 * Generate a unique correlation ID for a query using UUID v4.
 * This ID is used to track the query through the system and enable cancellation.
 *
 * @returns A unique correlation ID string
 */
export function generateCorrelationId(): string {
  return crypto.randomUUID();
}

/**
 * Cancel a query by its correlation ID.
 * Sends a fire-and-forget POST request to the backend /cancel endpoint.
 * Errors are logged but do not block the caller.
 *
 * @param correlationId The correlation ID of the query to cancel
 */
export async function cancelQuery(correlationId: string): Promise<void> {
  try {
    await fetch(`${API_BASE}/cancel`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ correlation_id: correlationId }),
    });
  } catch (err) {
    // Fire-and-forget: log warning but don't throw
    console.warn(`Cancel request failed for correlation_id=${correlationId}:`, err);
  }
}

/**
 * Send a query to the backend NLP translator with optional cancellation support.
 * Returns a discriminated union result for success/failure handling.
 *
 * - Accepts an optional correlation ID to track the query
 * - Accepts an optional AbortSignal for client-side abort
 * - 60-second timeout via AbortController
 * - HTTP 200: extracts rendered_output and computes latency (from meta or elapsed)
 * - HTTP 422: returns error payload with inline error message
 * - HTTP 503/504: returns error payload for service unavailability
 * - Timeout: returns synthetic 408 with descriptive message
 */
export async function queryBackend(
  queryText: string,
  correlationId?: string,
  signal?: AbortSignal,
): Promise<QueryResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const startTime = performance.now();

  // If an external signal is provided (e.g., from AbortController), merge it
  let mergedSignal: AbortSignal = controller.signal;
  if (signal) {
    // Listen to both signals — if either aborts, abort our controller
    const listener = () => controller.abort();
    signal.addEventListener('abort', listener, { once: true });
    mergedSignal = signal;  // Use the merged signal for the fetch
  }

  try {
    const headers: HeadersInit = { 'Content-Type': 'application/json' };
    if (correlationId) {
      headers['X-Correlation-ID'] = correlationId;
    }

    const response = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ query_text: queryText }),
      signal: mergedSignal,
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
 * Send a follow-up conversational query about an existing visualization.
 * Uses a dedicated endpoint that passes chart context to the LLM for explanation.
 *
 * @param followUpText The user's follow-up question
 * @param originalQuery The original data query that produced the chart
 * @param conversationHistory Previous messages in the strand
 * @param chartData The chart_data from the card's renderedOutput
 * @param rawData The raw_data from the card's renderedOutput
 * @param metadata The metadata from the card's renderedOutput
 * @param signal Optional AbortSignal for cancellation
 * @returns QueryResult with the explanation text
 */
export async function queryFollowUp(
  followUpText: string,
  originalQuery: string,
  conversationHistory: { role: string; content: string }[],
  chartData?: Record<string, unknown> | null,
  rawData?: Record<string, unknown> | null,
  metadata?: Record<string, unknown> | null,
  signal?: AbortSignal,
): Promise<QueryResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const startTime = performance.now();

  if (signal) {
    const listener = () => controller.abort();
    signal.addEventListener('abort', listener, { once: true });
  }

  const mergedSignal = signal ?? controller.signal;

  try {
    const response = await fetch(`${API_BASE}/query/follow-up`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        follow_up_text: followUpText,
        original_query: originalQuery,
        conversation_history: conversationHistory,
        chart_data: chartData ?? null,
        raw_data: rawData ?? null,
        metadata: metadata ?? null,
      }),
      signal: mergedSignal,
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

/**
 * Convert chart visualization type by re-rendering with new chart config.
 * Sends raw data + new chart type to backend for re-rendering.
 *
 * @param rawData The raw data from original query result
 * @param newChartType The desired visualization type ('bar', 'line', 'scatter', 'table', 'text')
 * @param originalQuery The original query text for context
 * @returns Rendered chart output or error
 */
export async function convertChartType(
  rawData: Record<string, unknown>,
  newChartType: string,
  originalQuery: string,
): Promise<QueryResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), TIMEOUT_MS);
  const startTime = performance.now();

  try {
    const response = await fetch(`${API_BASE}/api/re-render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        original_data: rawData,
        requested_type: newChartType,
        prompt: `Convert visualization to ${newChartType}`,
        query: originalQuery,
        metadata: {},
      }),
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

    // Response is already RenderedOutput (not wrapped)
    return {
      ok: true,
      data: data as RenderedOutput,
      latencyMs: data.metadata?.latency_ms ?? elapsed,
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
