/**
 * VisualizationCard component.
 *
 * Renders a single visualization card inline in the chat thread:
 * - Composes CardToolbar + ChartRenderer + FullscreenModal (conditional)
 * - Renders at 50% or 100% width within the chat thread
 * - Handles click/focus to set active card in the session store (for Stats Panel + Traceability Panel)
 * - Shows visual pinned-state indicator when card is pinned
 * - Professional styling with design tokens (subtle shadow, fine border, white bg)
 *
 * Requirements: 2.6, 4.1, 5.5, 11.3
 */

import { useCallback, useRef, useState } from 'react';
import type { CardState } from '../types';
import { useSessionStore } from '../store/sessionStore';
import { ChartRenderer } from './ChartRenderer';
import { CardToolbar } from './CardToolbar';
import { FullscreenModal } from './FullscreenModal';
import { StrandConversation } from './StrandConversation';
import { VisualizationPrompt } from './VisualizationPrompt';

export interface VisualizationCardProps {
  card: CardState;
  /** Ref callback for the drag handle element — provided by DraggableCard */
  dragHandleRef?: (el: HTMLElement | null) => void;
}

export function VisualizationCard({ card, dragHandleRef }: VisualizationCardProps) {
  const activeCardId = useSessionStore((s) => s.activeCardId);
  const setActiveCard = useSessionStore((s) => s.setActiveCard);
  const strands = useSessionStore((s) => s.strands);
  const strandLoading = useSessionStore((s) => s.strandLoading);
  const chartRef = useRef<HTMLDivElement>(null);
  const [fullscreenOpen, setFullscreenOpen] = useState(false);

  const isActive = activeCardId === card.id;
  
  // Find strand for this card (if any)
  const strand = Object.values(strands).find(s => s.cardId === card.id) || null;
  const strandIsLoading = strand ? strandLoading[strand.id] || false : false;

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      // Don't activate when clicking interactive children (buttons, links, toolbars)
      const target = e.target as HTMLElement;
      if (target.closest('button, a, [role="toolbar"]')) {
        return;
      }
      setActiveCard(card.id);
    },
    [card.id, setActiveCard],
  );

  const handleFocus = useCallback(() => {
    setActiveCard(card.id);
  }, [card.id, setActiveCard]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Don't intercept keys from input elements (text fields, textareas)
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return;
      }
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        setActiveCard(card.id);
      }
    },
    [card.id, setActiveCard],
  );

  // Width style based on card's width setting — responsive
  const widthClass = card.width === '50%' ? 'w-full md:w-1/2' : 'w-full';

  return (
    <div
      role="article"
      aria-label={`Visualization card: ${card.query}`}
      aria-selected={isActive}
      tabIndex={0}
      onClick={handleClick}
      onFocus={handleFocus}
      onKeyDown={handleKeyDown}
      className={[
        'relative flex flex-col rounded-lg border bg-bg-secondary',
        'transition-shadow duration-200 cursor-pointer',
        widthClass,
        isActive
          ? 'border-accent-primary shadow-card-hover ring-1 ring-accent-primary/20'
          : 'border-border-default shadow-card hover:shadow-card-hover',
      ].join(' ')}
    >
      {/* Visualization opt-in prompt */}
      <VisualizationPrompt card={card} />

      {/* Pinned indicator */}
      {card.pinned && (
        <div
          className="absolute top-2 right-2 z-10 flex items-center gap-1 rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5"
          title="Pinned"
          aria-label="Card is pinned"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-3.5 w-3.5 text-amber-500"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z" />
          </svg>
          <span className="text-xs font-medium text-amber-600">Pinned</span>
        </div>
      )}

      {/* Card content */}
      <div className="p-4 flex flex-col gap-3 flex-1 overflow-hidden">
        {/* Card toolbar */}
        <CardToolbar
          card={card}
          chartRef={chartRef}
          onExpandFullscreen={() => setFullscreenOpen(true)}
          dragHandleRef={dragHandleRef}
        />

        {/* Chart renderer - with responsive container */}
        <div 
          ref={chartRef} 
          className="flex-1 min-h-0 w-full overflow-hidden"
          style={{ minHeight: '280px' }}
        >
          <ChartRenderer
            renderedOutput={card.renderedOutput}
            userRequestedChartType={card.userRequestedChartType}
          />
        </div>

        {/* Prompt display — subtle, shown at bottom of card */}
        <div className="flex items-center gap-2 pt-1 border-t border-border-default/50">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-3.5 w-3.5 flex-shrink-0 text-text-muted"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.5}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 8.25h9m-9 3H12m-9.75 1.51c0 1.6 1.123 2.994 2.707 3.227 1.129.166 2.27.293 3.423.379.35.026.67.21.865.501L12 21l2.755-4.133a1.14 1.14 0 01.865-.501 48.172 48.172 0 003.423-.379c1.584-.233 2.707-1.626 2.707-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
          </svg>
          <p className="text-xs text-text-muted truncate" title={card.query}>
            {card.query}
          </p>
        </div>

        {/* Conversation Strand */}
        <div className="border-t border-border-default/50 mt-auto">
          <StrandConversation cardId={card.id} strand={strand} isLoading={strandIsLoading} />
        </div>
      </div>

      {/* Fullscreen modal (conditional) */}
      {fullscreenOpen && (
        <FullscreenModal
          card={card}
          onClose={() => setFullscreenOpen(false)}
        />
      )}
    </div>
  );
}
