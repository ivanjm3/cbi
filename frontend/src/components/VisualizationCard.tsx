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
    <div className="flex items-start gap-3 mb-4">
      <div 
        className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500/20 to-cyan-600/20 border border-cyan-500/30 flex items-center justify-center backdrop-blur-sm"
        style={{
          boxShadow: '0 0 20px rgba(6, 182, 212, 0.15), inset 0 1px 1px rgba(255, 255, 255, 0.1)'
        }}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-4 w-4 text-cyan-400"
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
      <div className="flex-1 pt-1">
        <p 
          className="text-sm text-slate-200 leading-relaxed tracking-wide"
          style={{
            fontFamily: 'var(--font-display)',
            fontWeight: 400,
            letterSpacing: '0.01em'
          }}
        >
          {query}
        </p>
      </div>
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
        group relative flex flex-col rounded-2xl border bg-slate-900/60 backdrop-blur-xl
        shadow-2xl transition-all duration-300 overflow-hidden animate-fade-in-up
        ${isActive
          ? 'border-cyan-500/60 ring-2 ring-cyan-500/30 shadow-cyan-500/20'
          : 'border-slate-700/50 hover:border-slate-600/60 hover:shadow-slate-800/40'
        }
      `}
      style={{
        boxShadow: isActive 
          ? '0 20px 40px rgba(6, 182, 212, 0.15), 0 8px 16px rgba(0, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.05)'
          : '0 8px 24px rgba(0, 0, 0, 0.3), inset 0 1px 1px rgba(255, 255, 255, 0.03)'
      }}
    >
      {/* Subtle gradient overlay for depth */}
      <div 
        className="absolute inset-0 opacity-30 pointer-events-none"
        style={{
          background: 'radial-gradient(circle at 20% 20%, rgba(6, 182, 212, 0.08) 0%, transparent 60%)'
        }}
      />

      {/* Pinned indicator with amber glow */}
      {card.pinned && (
        <div
          className="absolute top-4 right-4 z-30 text-amber-400"
          title="Pinned"
          aria-label="Card is pinned"
          style={{
            filter: 'drop-shadow(0 0 8px rgba(245, 158, 11, 0.6))'
          }}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-5 w-5"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z" />
          </svg>
        </div>
      )}

      {/* Card content with generous padding */}
      <div className="relative z-10 p-6 flex flex-col gap-3 flex-1 min-h-0">
        {/* User message in conversational format */}
        <UserMessage query={card.query} />

        {/* Card toolbar */}
        <CardToolbar
          card={card}
          chartRef={chartRef}
        />

        {/* Chart / visualization with refined container */}
        <div 
          ref={chartRef} 
          className="flex-1 min-h-0 rounded-xl bg-slate-950/40 p-4 border border-slate-800/50"
          style={{
            boxShadow: 'inset 0 2px 8px rgba(0, 0, 0, 0.3)'
          }}
        >
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

      {/* Subtle border glow on hover */}
      <div 
        className={`absolute inset-0 rounded-2xl pointer-events-none transition-opacity duration-300 ${
          isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-50'
        }`}
        style={{
          background: 'linear-gradient(135deg, rgba(6, 182, 212, 0.1) 0%, rgba(245, 158, 11, 0.05) 100%)',
          mixBlendMode: 'overlay'
        }}
      />
    </div>
  );
}
