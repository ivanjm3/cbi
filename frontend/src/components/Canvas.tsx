/**
 * Canvas component with CSS Grid layout and drag-and-drop support.
 *
 * - 2 columns × 3 rows CSS Grid; single-column when <2 cards
 * - Drag-to-reorder with react-dnd and visual drop indicators
 * - Drops on pinned card positions are rejected
 * - Reflow cards within 300ms of drop
 * - Resize handles (bottom-right, bottom-left) for 1-2 col/row spans
 * - Constrain resize to grid boundaries, prevent overlap
 * - Re-render charts within 200ms of resize
 * - Empty-state message when no cards; streaming skeleton during loading
 *
 * Requirements: 1.3, 1.4, 1.7, 2.7, 2.8, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
 */

import { useCallback, useRef } from 'react';
import { DndProvider, useDrag, useDrop, useDragLayer } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import type { CardState } from '../types';
import { GRID_COLS, GRID_ROWS } from '../types/grid';
import { useSessionStore } from '../store/sessionStore';
import { buildOccupiedSet, constrainResize } from '../utils/gridHelpers';
import { VisualizationCard } from './VisualizationCard';
import { ErrorCard } from './ErrorCard';

// ---------------------------------------------------------------------------
// DnD item type
// ---------------------------------------------------------------------------

const CARD_DND_TYPE = 'VISUALIZATION_CARD';

interface DragItem {
  id: string;
  col: number;
  row: number;
}

// ---------------------------------------------------------------------------
// DraggableCard — wraps VisualizationCard with drag source + resize handles
// ---------------------------------------------------------------------------

interface DraggableCardProps {
  card: CardState;
}

function DraggableCard({ card }: DraggableCardProps) {
  const resizeCard = useSessionStore((s) => s.resizeCard);
  const cards = useSessionStore((s) => s.cards);
  const cardRef = useRef<HTMLDivElement>(null);

  const [{ isDragging }, dragRef, previewRef] = useDrag(
    () => ({
      type: CARD_DND_TYPE,
      item: { id: card.id, col: card.gridPosition.col, row: card.gridPosition.row },
      canDrag: () => !card.pinned,
      collect: (monitor) => ({
        isDragging: monitor.isDragging(),
      }),
    }),
    [card.id, card.gridPosition.col, card.gridPosition.row, card.pinned],
  );

  // Resize handler
  const handleResize = useCallback(
    (direction: 'br' | 'bl') => {
      // Toggle span: if currently 1, try 2; if 2, go back to 1
      let newColSpan: 1 | 2 = card.gridSize.colSpan;
      let newRowSpan: 1 | 2 = card.gridSize.rowSpan;

      if (direction === 'br') {
        // Bottom-right: toggle colSpan and rowSpan
        newColSpan = card.gridSize.colSpan === 1 ? 2 : 1;
        newRowSpan = card.gridSize.rowSpan === 1 ? 2 : 1;
      } else {
        // Bottom-left: toggle rowSpan only (col doesn't change for BL)
        newRowSpan = card.gridSize.rowSpan === 1 ? 2 : 1;
      }

      const constrained = constrainResize(
        card.gridPosition.col,
        card.gridPosition.row,
        newColSpan,
        newRowSpan,
        cards,
        card.id,
      );

      resizeCard(card.id, constrained);
    },
    [card, cards, resizeCard],
  );

  // Compute grid placement CSS
  const gridColumn = `${card.gridPosition.col + 1} / span ${card.gridSize.colSpan}`;
  const gridRow = `${card.gridPosition.row + 1} / span ${card.gridSize.rowSpan}`;

  return (
    <div
      ref={(node) => {
        previewRef(node);
        (cardRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
      }}
      className={`relative transition-opacity duration-200 ${
        isDragging ? 'opacity-40' : 'opacity-100'
      }`}
      style={{ gridColumn, gridRow }}
    >
      {/* Drag handle overlay — whole card is draggable */}
      <div ref={dragRef as unknown as React.Ref<HTMLDivElement>} className={`h-full ${!card.pinned ? 'cursor-grab active:cursor-grabbing' : ''}`}>
        <VisualizationCard card={card} />
      </div>

      {/* Resize handles */}
      {!card.pinned && (
        <>
          {/* Bottom-right resize handle */}
          <button
            type="button"
            onClick={() => handleResize('br')}
            className="absolute bottom-1 right-1 w-4 h-4 bg-gray-300 dark:bg-gray-600 rounded-sm opacity-0 hover:opacity-100 transition-opacity cursor-nwse-resize flex items-center justify-center"
            title="Resize card"
            aria-label="Resize card from bottom-right"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-3 w-3 text-gray-600 dark:text-gray-300"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 13l-6 6m2-8l4 4" />
            </svg>
          </button>

          {/* Bottom-left resize handle */}
          <button
            type="button"
            onClick={() => handleResize('bl')}
            className="absolute bottom-1 left-1 w-4 h-4 bg-gray-300 dark:bg-gray-600 rounded-sm opacity-0 hover:opacity-100 transition-opacity cursor-nesw-resize flex items-center justify-center"
            title="Resize card vertically"
            aria-label="Resize card from bottom-left"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-3 w-3 text-gray-600 dark:text-gray-300"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l6 6m-2-8l-4 4" />
            </svg>
          </button>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// DropCell — represents a droppable grid cell
// ---------------------------------------------------------------------------

interface DropCellProps {
  col: number;
  row: number;
  occupied: boolean;
  pinnedOccupied: boolean;
}

function DropCell({ col, row, occupied, pinnedOccupied, isDragActive }: DropCellProps & { isDragActive: boolean }) {
  const moveCard = useSessionStore((s) => s.moveCard);

  const [{ isOver, canDrop }, dropRef] = useDrop(
    () => ({
      accept: CARD_DND_TYPE,
      canDrop: () => !occupied,
      drop: (item: DragItem) => {
        if (pinnedOccupied) return; // Reject drops on pinned positions
        moveCard(item.id, { col, row });
      },
      collect: (monitor) => ({
        isOver: monitor.isOver(),
        canDrop: monitor.canDrop(),
      }),
    }),
    [col, row, occupied, pinnedOccupied, moveCard],
  );

  // Only enable pointer-events on drop cells during an active drag
  // so they don't intercept clicks/interactions on cards
  return (
    <div
      ref={dropRef as unknown as React.Ref<HTMLDivElement>}
      className={`absolute inset-0 z-10 transition-colors duration-150 ${
        isDragActive ? 'pointer-events-auto' : 'pointer-events-none'
      } ${
        isOver && canDrop
          ? 'bg-blue-200/50 dark:bg-blue-800/30 border-2 border-blue-400 dark:border-blue-500 border-dashed rounded-lg'
          : isOver && !canDrop
            ? 'bg-red-200/30 dark:bg-red-800/20 border-2 border-red-400 dark:border-red-500 border-dashed rounded-lg'
            : ''
      }`}
      style={{
        gridColumn: `${col + 1}`,
        gridRow: `${row + 1}`,
      }}
    />
  );
}

// ---------------------------------------------------------------------------
// CanvasGrid — the inner grid with drop targets
// ---------------------------------------------------------------------------

function CanvasGrid() {
  const cards = useSessionStore((s) => s.cards);
  const loading = useSessionStore((s) => s.loading);

  // Track whether a drag is currently in progress to enable DropCell pointer-events
  const { isDragActive } = useDragLayer((monitor) => ({
    isDragActive: monitor.isDragging(),
  }));

  // Build occupied cell data for drop targets
  const occupied = buildOccupiedSet(cards);
  const pinnedOccupied = buildOccupiedSet(cards.filter((c) => c.pinned));

  // Determine if we should use single-column layout
  const useSingleCol = cards.length < 2;

  // Canvas full + all pinned check
  const isCanvasFull = occupied.size >= GRID_COLS * GRID_ROWS;
  const allPinned = isCanvasFull && cards.every((c) => c.pinned);

  // Generate drop target cells for empty positions
  const dropCells: Array<{ col: number; row: number; isOccupied: boolean; isPinnedOccupied: boolean }> = [];
  for (let r = 0; r < GRID_ROWS; r++) {
    for (let c = 0; c < GRID_COLS; c++) {
      const key = `${c},${r}`;
      dropCells.push({
        col: c,
        row: r,
        isOccupied: occupied.has(key),
        isPinnedOccupied: pinnedOccupied.has(key),
      });
    }
  }

  return (
    <div
      className={`relative grid gap-4 h-full min-h-0 ${
        useSingleCol
          ? 'grid-cols-1 grid-rows-3'
          : 'grid-cols-2 grid-rows-3'
      }`}
      style={{
        gridTemplateRows: 'repeat(3, minmax(0, 1fr))',
        gridTemplateColumns: useSingleCol ? '1fr' : 'repeat(2, minmax(0, 1fr))',
      }}
    >
      {/* Drop target overlay cells */}
      {dropCells.map((cell) => (
        <div
          key={`drop-${cell.col}-${cell.row}`}
          className="relative"
          style={{
            gridColumn: `${cell.col + 1}`,
            gridRow: `${cell.row + 1}`,
          }}
        >
          <DropCell
            col={cell.col}
            row={cell.row}
            occupied={cell.isOccupied}
            pinnedOccupied={cell.isPinnedOccupied}
            isDragActive={isDragActive}
          />
        </div>
      ))}

      {/* Visualization cards */}
      {cards.map((card) => (
        <DraggableCard key={card.id} card={card} />
      ))}

      {/* Empty state */}
      {cards.length === 0 && !loading && (
        <div className="col-span-full row-span-full flex items-center justify-center">
          <div className="text-center">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-12 w-12 mx-auto mb-3 text-gray-300 dark:text-gray-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <h2 className="text-lg font-medium text-gray-700 dark:text-gray-300">
              No visualizations yet
            </h2>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              Ask a question using the chat bar below to get started
            </p>
          </div>
        </div>
      )}

      {/* Streaming skeleton / loading indicator */}
      {loading && (
        <div
          className="flex items-center justify-center rounded-lg border-2 border-dashed border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50"
          style={{
            gridColumn: useSingleCol ? '1' : `${(cards.length % 2) + 1}`,
            gridRow: `${Math.floor(cards.length / (useSingleCol ? 1 : 2)) + 1}`,
          }}
        >
          <div className="flex flex-col items-center gap-3 p-6">
            <div className="flex space-x-1">
              <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Generating visualization…
            </p>
          </div>
        </div>
      )}

      {/* Canvas full notification — all cards pinned */}
      {allPinned && (
        <div
          className="col-span-full flex items-center justify-center"
          role="alert"
          aria-live="polite"
        >
          <div className="inline-flex items-center gap-2 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-4 py-3">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5 text-amber-500 dark:text-amber-400 flex-shrink-0"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            <p className="text-sm text-amber-800 dark:text-amber-300">
              Canvas is full — unpin or remove a card to display new results.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ErrorThread — renders error messages from the chat thread
// ---------------------------------------------------------------------------

/**
 * Renders error messages from the chat thread below the canvas grid.
 * Displays inline error cards for 422, 503/504, and timeout errors.
 * Finds the original query for retryable errors by looking at the preceding
 * user message in the chat thread.
 */
function ErrorThread() {
  const chatThread = useSessionStore((s) => s.chatThread);

  const errorMessages = chatThread.filter((m) => m.role === 'error');

  if (errorMessages.length === 0) return null;

  return (
    <div className="mt-4 space-y-3" aria-label="Error messages">
      {errorMessages.map((msg) => {
        return (
          <ErrorCard
            key={msg.id}
            message={msg.content}
            statusCode={msg.statusCode}
            originalQuery={msg.originalQuery}
          />
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Canvas — exported wrapper with DndProvider
// ---------------------------------------------------------------------------

export function Canvas() {
  return (
    <DndProvider backend={HTML5Backend}>
      <main
        className="flex-1 min-w-0 max-w-full min-h-0 overflow-y-auto p-4"
        aria-label="Canvas"
      >
        <CanvasGrid />
        <ErrorThread />
      </main>
    </DndProvider>
  );
}
