/**
 * TraceabilityPanel component.
 *
 * Right sidebar (360px) that slides in from the right edge of the viewport.
 * Displays three sections for the active card's transparency data:
 * 1. Paraphrased query rewrite (natural language interpretation)
 * 2. Structured intent JSON (query_id, query_type, entity_refs, routing_metadata, timestamp)
 * 3. API call summary (agent identifiers, data sources, response status)
 *
 * Shows an empty state when no Visualization_Card is active.
 * Shows placeholder messages per section if data is unavailable.
 * Updates content when active card changes.
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
 */

import { useSessionStore } from '../store/sessionStore';
import type { TransparencyData } from '../types';

// ---------------------------------------------------------------------------
// Sub-components for each section
// ---------------------------------------------------------------------------

function QueryRewriteSection({ data }: { data: TransparencyData['queryRewrite'] }) {
  return (
    <section aria-labelledby="trace-query-rewrite">
      <h3
        id="trace-query-rewrite"
        className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2"
      >
        Query Rewrite
      </h3>
      {data ? (
        <p className="text-sm text-text-secondary leading-relaxed">{data}</p>
      ) : (
        <p className="text-sm italic text-text-muted">
          Data could not be retrieved
        </p>
      )}
    </section>
  );
}

function StructuredIntentSection({
  data,
}: {
  data: TransparencyData['structuredIntent'];
}) {
  return (
    <section aria-labelledby="trace-structured-intent">
      <h3
        id="trace-structured-intent"
        className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2"
      >
        Structured Intent
      </h3>
      {data ? (
        <pre className="rounded-md bg-bg-input p-3 text-xs font-mono text-text-primary overflow-x-auto leading-relaxed">
          {JSON.stringify(data, null, 2)}
        </pre>
      ) : (
        <p className="text-sm italic text-text-muted">
          Data could not be retrieved
        </p>
      )}
    </section>
  );
}

function ApiCallSummarySection({
  data,
}: {
  data: TransparencyData['apiCallSummary'];
}) {
  return (
    <section aria-labelledby="trace-api-summary">
      <h3
        id="trace-api-summary"
        className="text-xs font-semibold uppercase tracking-wider text-text-muted mb-2"
      >
        API Call Summary
      </h3>
      {data ? (
        <ul className="space-y-2">
          {data.agents.map((agent) => (
            <li
              key={agent.id}
              className="rounded-md border border-border-default bg-bg-input p-3"
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-text-primary">
                  {agent.id}
                </span>
                <StatusBadge status={agent.status} />
              </div>
              {agent.dataSources.length > 0 && (
                <div className="mt-1 text-xs text-text-muted">
                  Sources: {agent.dataSources.join(', ')}
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm italic text-text-muted">
          Data could not be retrieved
        </p>
      )}
    </section>
  );
}

function StatusBadge({ status }: { status: 'success' | 'error' | 'timeout' }) {
  const styles: Record<string, string> = {
    success: 'bg-status-success/10 text-status-success',
    error: 'bg-status-error/10 text-status-error',
    timeout: 'bg-status-warning/10 text-status-warning',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${styles[status]}`}
    >
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main TraceabilityPanel component
// ---------------------------------------------------------------------------

export function TraceabilityPanel() {
  const activeCardId = useSessionStore((s) => s.activeCardId);
  const cards = useSessionStore((s) => s.cards);

  const activeCard = activeCardId ? cards[activeCardId] : null;
  const transparencyData = activeCard?.transparencyData ?? null;

  return (
    <aside
      className="flex h-full w-[360px] min-w-[360px] flex-col border-l border-border-default bg-bg-secondary shadow-panel animate-slide-in-right"
      aria-label="Traceability panel"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
        <h2 className="text-sm font-semibold text-text-primary">
          Traceability &amp; Explainability
        </h2>
      </div>

      {/* Content */}
      {!activeCard ? (
        /* Empty state: no card selected */
        <div className="flex flex-1 items-center justify-center p-4">
          <div className="text-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="mx-auto h-10 w-10 text-text-muted mb-3"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"
              />
            </svg>
            <p className="text-sm text-text-muted">
              Select a visualization to view traceability
            </p>
          </div>
        </div>
      ) : (
        /* Active card: show three sections */
        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          <QueryRewriteSection data={transparencyData?.queryRewrite ?? null} />
          <StructuredIntentSection
            data={transparencyData?.structuredIntent ?? null}
          />
          <ApiCallSummarySection
            data={transparencyData?.apiCallSummary ?? null}
          />
        </div>
      )}
    </aside>
  );
}
