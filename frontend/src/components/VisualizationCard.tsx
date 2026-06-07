import { useRef, useState } from 'react';
import type { CardState } from '../types';
import { useSessionStore } from '../store/sessionStore';
import ChartRenderer from './ChartRenderer';
import CardToolbar from './CardToolbar';
import { TransparencyDrawer } from './TransparencyDrawer';
import FullscreenModal from './FullscreenModal';

interface VisualizationCardProps {
  card: CardState;
}

/**
 * VisualizationCard - composes UserMessage, CardToolbar, ChartRenderer,
 * and TransparencyDrawer into a single conversational card.
 *
 * Displays the user query text at the top, the chart below, with a toolbar
 * for actions and a collapsible transparency drawer at the bottom.
 *
 * Sets the active card in the store on click or focus.
 *
 * Requirements: 2.6, 4.1
 */
export default function VisualizationCard({ card }: VisualizationCardProps) {
  const setActiveCard = useSessionStore((state) => state.setActiveCard);
  const activeCardId = useSessionStore((state) => state.activeCardId);
  const cardRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);

  const isActive = activeCardId === card.id;

  const handleActivate = () => {
    setActiveCard(card.id);
  };

  return (
    <>
      <div
        ref={cardRef}
        data-testid={`visualization-card-${card.id}`}
        role="article"
        aria-label={`Visualization for: ${card.query}`}
        tabIndex={0}
        className={`flex flex-col rounded-lg border bg-white shadow-sm transition-shadow ${
          isActive
            ? 'border-blue-500 shadow-md ring-2 ring-blue-200'
            : 'border-gray-200 hover:shadow-md'
        }`}
        onClick={handleActivate}
        onFocus={handleActivate}
      >
        {/* User message - displayed above the chart in conversational format */}
        <div
          data-testid="user-message"
          className="px-4 pt-3 pb-2 border-b border-gray-100"
        >
          <p className="text-sm text-gray-600 font-medium">{card.query}</p>
        </div>

        {/* Card Toolbar */}
        <CardToolbar
          cardId={card.id}
          cardRef={cardRef}
          chartData={card.renderedOutput}
          pinned={card.pinned}
          onExpandFullscreen={() => setFullscreen(true)}
        />

        {/* Chart Renderer */}
        <div className="flex-1 px-2 pb-2">
          <ChartRenderer renderedOutput={card.renderedOutput} />
        </div>

        {/* Transparency Drawer */}
        <TransparencyDrawer
          description={card.renderedOutput.description}
          metadata={card.renderedOutput.metadata}
        />
      </div>

      {/* Fullscreen Modal */}
      {fullscreen && (
        <FullscreenModal onClose={() => setFullscreen(false)}>
          <div className="h-full flex flex-col">
            <div className="px-4 py-3 border-b border-gray-100">
              <p className="text-sm text-gray-600 font-medium">{card.query}</p>
            </div>
            <div className="flex-1 p-4">
              <ChartRenderer renderedOutput={card.renderedOutput} />
            </div>
          </div>
        </FullscreenModal>
      )}
    </>
  );
}
