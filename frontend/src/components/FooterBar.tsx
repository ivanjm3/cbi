/**
 * FooterBar component.
 *
 * Persistent clickable bar below ChatThread, above ChatInput.
 * Displays "Traceability & Explainability" label with an info icon.
 * Clicking toggles the TraceabilityPanel visibility via the zustand store.
 *
 * Requirements: 1.6, 3.1, 3.3
 */

import { useSessionStore } from '../store/sessionStore';

export function FooterBar() {
  const toggleTraceabilityPanel = useSessionStore((s) => s.toggleTraceabilityPanel);
  const traceabilityPanelVisible = useSessionStore((s) => s.traceabilityPanelVisible);

  return (
    <button
      type="button"
      onClick={toggleTraceabilityPanel}
      className="flex w-full items-center gap-2 border-t border-border-default bg-bg-secondary px-4 py-2 text-text-secondary hover:bg-accent-subtle hover:text-accent-primary transition-colors duration-150"
      aria-label="Toggle traceability panel"
      aria-pressed={traceabilityPanelVisible}
    >
      {/* Eye/info icon */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-4 w-4"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"
        />
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
        />
      </svg>
      <span className="text-sm font-medium">
        Traceability &amp; Explainability
      </span>
      {/* Chevron indicator */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className={`ml-auto h-4 w-4 transition-transform duration-150 ${
          traceabilityPanelVisible ? 'rotate-180' : ''
        }`}
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
      </svg>
    </button>
  );
}
