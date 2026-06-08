/**
 * TraceabilityPanel placeholder component.
 *
 * Displays a simple placeholder. Will be fully implemented in task 9.1
 * with query rewrite, structured intent, and API call summary sections.
 *
 * Requirements: 3.1, 3.2, 3.3
 */

export function TraceabilityPanel() {
  return (
    <aside
      className="flex h-full w-[360px] min-w-[360px] flex-col border-l border-border-default bg-bg-secondary animate-slide-in-right"
      aria-label="Traceability panel"
    >
      <div className="flex items-center justify-between border-b border-border-default px-4 py-3">
        <h2 className="text-sm font-semibold text-text-primary">
          Traceability &amp; Explainability
        </h2>
      </div>
      <div className="flex flex-1 items-center justify-center p-4">
        <p className="text-sm text-text-muted">
          Select a visualization to view traceability
        </p>
      </div>
    </aside>
  );
}
