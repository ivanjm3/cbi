/**
 * VisualizationPrompt component
 *
 * Shows a 0.5s disappearing notification when a text-only response is returned,
 * asking if the user would prefer a visualization.
 * 
 * If user clicks "Show me a chart", re-triggers the query for visualization.
 * If user ignores or clicks dismiss, the notification disappears.
 */

import { useEffect, useState } from 'react';
import type { CardState } from '../types';
import { useSessionStore } from '../store/sessionStore';

interface VisualizationPromptProps {
  card: CardState;
  onDismiss?: () => void;
}

export function VisualizationPrompt({ card, onDismiss }: VisualizationPromptProps) {
  const [show, setShow] = useState(true);
  const [userDismissed, setUserDismissed] = useState(false);
  const submitQuery = useSessionStore((s) => s.submitQuery);

  // Auto-hide after 5 seconds (or user dismisses)
  useEffect(() => {
    if (userDismissed) return;

    const timer = setTimeout(() => {
      setShow(false);
      onDismiss?.();
    }, 5000);

    return () => clearTimeout(timer);
  }, [userDismissed, onDismiss]);

  if (!show) return null;

  // Check if visualization was already requested (metadata flag)
  const metadata = card.renderedOutput?.metadata;
  const shouldAskForViz = metadata?.ask_for_visualization === true;

  if (!shouldAskForViz) return null;

  const handleShowChart = () => {
    setUserDismissed(true);
    setShow(false);
    // Re-submit query with explicit chart request
    submitQuery(card.query + " (show me a chart)");
  };

  const handleDismiss = () => {
    setUserDismissed(true);
    setShow(false);
    onDismiss?.();
  };

  return (
    <div
      className="fixed bottom-20 left-1/2 -translate-x-1/2 z-50 flex items-center gap-3 rounded-lg border border-border-default bg-bg-secondary/95 px-4 py-3 shadow-lg backdrop-blur-sm animate-fadeIn"
      role="status"
      aria-live="polite"
      aria-label="Visualization suggestion"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        className="h-5 w-5 flex-shrink-0 text-accent-primary"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.5}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
        />
      </svg>

      <span className="text-sm text-text-primary">Would you like to see this as a visualization?</span>

      <div className="flex gap-2 ml-2">
        <button
          onClick={handleShowChart}
          className="rounded bg-accent-primary px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-1"
          aria-label="Show chart visualization"
        >
          Show Chart
        </button>
        <button
          onClick={handleDismiss}
          className="rounded px-3 py-1.5 text-xs font-medium text-text-muted transition-colors hover:bg-bg-input focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-1"
          aria-label="Dismiss"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}
