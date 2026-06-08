/**
 * DraggableCard component.
 *
 * Wraps a VisualizationCard to provide drag-to-reorder functionality using react-dnd.
 * The drag is initiated only from the drag handle (data-drag-handle attribute).
 * Includes resize handles on bottom-right and bottom-left corners for toggling
 * between 50% and 100% width.
 *
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
 */

import { useRef, useCallback } from 'react';
import { useDrag, useDrop } from 'react-dnd';
import type { CardState } from '../types';
import { useSessionStore } from '../store/sessionStore';
import { VisualizationCard } from './VisualizationCard';

/** Drag item type constant for card reordering */
export const CARD_DRAG_TYPE = 'VISUALIZATION_CARD';

export interface DragItem {
  type: typeof CARD_DRAG_TYPE;
  cardId: string;
  originalIndex: number;
}

export interface DraggableCardProps {
  card: CardState;
  index: number;
}

export function DraggableCard({ card, index }: DraggableCardProps) {
  const reorderCard = useSessionStore((s) => s.reorderCard);
  const resizeCard = useSessionStore((s) => s.resizeCard);
  const cards = useSessionStore((s) => s.cards);
  const chatThread = useSessionStore((s) => s.chatThread);

  const containerRef = useRef<HTMLDivElement>(null);

  // ---- Drag source ----
  const [{ isDragging }, drag, dragPreview] = useDrag(
    () => ({
      type: CARD_DRAG_TYPE,
      item: (): DragItem => ({
        type: CARD_DRAG_TYPE,
        cardId: card.id,
        originalIndex: index,
      }),
      collect: (monitor) => ({
        isDragging: monitor.isDragging(),
      }),
      canDrag: () => !card.pinned, // Pinned cards cannot be dragged
    }),
    [card.id, card.pinned, index],
  );

  // ---- Drop target ----
  const [{ isOver, canDrop }, drop] = useDrop(
    () => ({
      accept: CARD_DRAG_TYPE,
      canDrop: (item: DragItem) => {
        // Reject drop on pinned card positions
        if (card.pinned) return false;
        // Can't drop on itself
        if (item.cardId === card.id) return false;
        return true;
      },
      drop: (item: DragItem) => {
        // Find the target index in the chatThread for this card
        const targetIndex = chatThread.findIndex((msg) => msg.cardId === card.id);
        if (targetIndex === -1) return;

        // Check if target position is a pinned card — reject
        const targetMsg = chatThread[targetIndex];
        if (targetMsg?.cardId && cards[targetMsg.cardId]?.pinned) {
          return; // Reject drop on pinned position
        }

        reorderCard(item.cardId, targetIndex);
      },
      collect: (monitor) => ({
        isOver: monitor.isOver(),
        canDrop: monitor.canDrop(),
      }),
    }),
    [card.id, card.pinned, chatThread, cards, reorderCard],
  );

  // Connect drag preview to the container
  dragPreview(drop(containerRef));

  // Connect drag source to the drag handle only
  const handleRef = useCallback(
    (el: HTMLElement | null) => {
      drag(el);
    },
    [drag],
  );

  // ---- Resize handlers ----
  const handleResizeToggle = useCallback(() => {
    const newWidth = card.width === '100%' ? '50%' : '100%';
    resizeCard(card.id, newWidth);
  }, [card.id, card.width, resizeCard]);

  // Determine visual states
  const showDropIndicator = isOver && canDrop;
  const showRejectIndicator = isOver && !canDrop;

  return (
    <div
      ref={containerRef}
      className="relative group"
      style={{
        opacity: isDragging ? 0.4 : 1,
        transition: 'opacity 150ms ease, transform 300ms ease',
      }}
      data-testid={`draggable-card-${card.id}`}
    >
      {/* Drop indicator — top line showing valid placement */}
      {showDropIndicator && (
        <div
          className="absolute -top-1 left-0 right-0 h-0.5 bg-accent-primary rounded-full z-20 animate-pulse"
          data-testid="drop-indicator"
          aria-hidden="true"
        />
      )}

      {/* Reject indicator — red line showing invalid placement */}
      {showRejectIndicator && (
        <div
          className="absolute -top-1 left-0 right-0 h-0.5 bg-status-error rounded-full z-20"
          data-testid="reject-indicator"
          aria-hidden="true"
        />
      )}

      {/* Card with drag handle connection */}
      <div className="relative">
        <VisualizationCard card={card} dragHandleRef={handleRef} />

        {/* Resize handle — bottom-right corner */}
        <button
          type="button"
          onClick={handleResizeToggle}
          className="absolute bottom-1 right-1 w-5 h-5 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-bg-input hover:bg-accent-subtle border border-border-default cursor-se-resize z-10"
          title={card.width === '100%' ? 'Resize to 50%' : 'Resize to 100%'}
          aria-label={card.width === '100%' ? 'Resize card to 50% width' : 'Resize card to 100% width'}
          data-testid="resize-handle-br"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-3 w-3 text-text-muted"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 20l16-16M12 20l8-8M20 20h0" />
          </svg>
        </button>

        {/* Resize handle — bottom-left corner */}
        <button
          type="button"
          onClick={handleResizeToggle}
          className="absolute bottom-1 left-1 w-5 h-5 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 transition-opacity duration-200 bg-bg-input hover:bg-accent-subtle border border-border-default cursor-sw-resize z-10"
          title={card.width === '100%' ? 'Resize to 50%' : 'Resize to 100%'}
          aria-label={card.width === '100%' ? 'Resize card to 50% width' : 'Resize card to 100% width'}
          data-testid="resize-handle-bl"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="h-3 w-3 text-text-muted transform -scale-x-100"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 20l16-16M12 20l8-8M20 20h0" />
          </svg>
        </button>
      </div>
    </div>
  );
}
