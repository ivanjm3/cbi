/**
 * VisualizationCard component.
 *
 * Renders a single visualization card on the canvas in conversational format:
 * - User message (query) displayed above the chart
 * - Card toolbar with actions (Download, Pin, Expand, Bookmark, Drag)
 * - Chart rendered via ChartRenderer
 * - Transparency drawer ("How I got this")
 *
 * Handles click/focus to set the active card in the session store.
 *
 * Requirements: 2.6, 4.1
 */

import { useCallback, useRef, useState } from 'react';
import type { CardState } from '../types';
import { useSessionStore } from '../store/sessionStore';
import { ChartRenderer } from './ChartRenderer';
import { CardToolbar } from './CardToolbar';
import { TransparencyDrawer } from './TransparencyDrawer';
import { FullscreenModal } from './FullscreenModal';

export interface VisualizationCardProps {
  card: CardState;
}

/**
 * UserMessage displays the original user query in conversational format
 * above the visualization result.
 */
function UserMessage({ query }: { query: string }) {
  return (
    <div className="flex items-start gap-2 mb-3">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4 text-blue-600 dark:text-blue-300"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
          />
        </svg>
      </div>
      <p className="text-sm text-gray-800 dark:text-gray-200 pt-1 leading-snug">
        {query}
      </p>
    </div>
  );
}

export function VisualizationCard({ card }: VisualizationCardProps) {
  const activeCardId = useSessionStore((s) => s.activeCardId);
  const setActiveCard = useSessionStore((s) => s.setActiveCard);
  const cardRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<HTMLDivElement>(null);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);

  const isActive = activeCardId === card.id;

  const handleActivate = useCallback((e: React.MouseEvent) => {
    // Only activate when clicking the card itself, not interactive children
    // (buttons, links, or elements inside a toolbar/drawer)
    const target = e.target as HTMLElement;
    if (target.closest('button, a, [role="toolbar"], [role="region"]')) {
      return;
    }
    setActiveCard(card.id);
  }, [card.id, setActiveCard]);

  const handleFocusActivate = useCallback(() => {
    setActiveCard(card.id);
  }, [card.id, setActiveCard]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Activate on Enter or Space when the card itself is focused
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setActiveCard(card.id);
      }
    },
    [card.id, setActiveCard],
  );

  return (
    <div
      ref={cardRef}
      role="article"
      aria-label={`Visualization card: ${card.query}`}
      aria-selected={isActive}
      tabIndex={0}
      onClick={handleActivate}
      onDoubleClick={(e) => {
        // Don't trigger on button/interactive double-clicks
        const target = e.target as HTMLElement;
        if (!target.closest('button, a, [role="toolbar"]')) {
          setFullscreenOpen(true);
        }
      }}
      onFocus={handleFocusActivate}
      onKeyDown={handleKeyDown}
      className={`
        relative flex flex-col rounded-lg border bg-white dark:bg-gray-900
        shadow-sm transition-shadow duration-150
        ${isActive
          ? 'border-blue-500 dark:border-blue-400 ring-2 ring-blue-200 dark:ring-blue-800 shadow-md'
          : 'border-gray-200 dark:border-gray-700 hover:shadow-md'
        }
      `}
    >
      {/* Pinned indicator */}
      {card.pinned && (
        <div
          className="absolute top-2 right-2 text-amber-500 dark:text-amber-400"
          title="Pinned"
          aria-label="Card is pinned"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-4 w-4"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z" />
          </svg>
        </div>
      )}

      {/* Card content */}
      <div className="p-4 flex flex-col gap-2 flex-1 min-h-0">
        {/* User message in conversational format */}
        <UserMessage query={card.query} />

        {/* Card toolbar */}
        <CardToolbar
          card={card}
          chartRef={chartRef}
        />

        {/* Chart / visualization */}
        <div ref={chartRef} className="flex-1 min-h-0">
          <ChartRenderer renderedOutput={card.renderedOutput} />
        </div>

        {/* Transparency drawer */}
        <TransparencyDrawer renderedOutput={card.renderedOutput} />

        {/* Fullscreen modal */}
        {fullscreenOpen && (
          <FullscreenModal
            card={card}
            onClose={() => setFullscreenOpen(false)}
          />
        )}
      </div>
    </div>
  );
}
