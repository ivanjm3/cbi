/**
 * FooterBar component — compact toggle button for Traceability panel.
 *
 * Small pill-shaped button positioned at the bottom-right of the chat area
 * (above the floating ChatInput). Clicking toggles the TraceabilityPanel.
 *
 * Requirements: 1.6, 3.1, 3.3
 */

import { useSessionStore } from '../store/sessionStore';

export function FooterBar() {
  const toggleTraceabilityPanel = useSessionStore((s) => s.toggleTraceabilityPanel);
  const traceabilityPanelVisible = useSessionStore((s) => s.traceabilityPanelVisible);

  return (
    <div className="absolute bottom-20 right-4 z-10">
      <button
        type="button"
        onClick={toggleTraceabilityPanel}
        className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium shadow-md transition-colors duration-150 ${
          traceabilityPanelVisible
            ? 'bg-accent-primary text-white'
            : 'bg-bg-secondary/95 border border-border-default text-text-secondary hover:bg-accent-subtle hover:text-accent-primary backdrop-blur-sm'
        }`}
        aria-label="Toggle traceability panel"
        aria-pressed={traceabilityPanelVisible}
      >
        {/* Eye icon */}
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-3.5 w-3.5"
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
        <span>Trace</span>
      </button>
    </div>
  );
}
