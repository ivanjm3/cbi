import { useCallback, useState, useRef, useEffect } from 'react';
import { DndProvider, useDrag, useDrop } from 'react-dnd';
import { HTML5Backend } from 'react-dnd-html5-backend';
import { useSessionStore } from '../store/sessionStore';
import { constrainResize } from '../utils/gridHelpers';
import VisualizationCard from './VisualizationCard';
import ErrorCard from './ErrorCard';
import { CanvasFullNotification } from './CanvasFullNotification';
import type { CardState } from '../types';
import type { ColSpan, RowSpan } from '../types/grid';
import { GRID_COLS, GRID_ROWS, cellKey, getOccupiedCells } from '../types/grid';

// ─── Constants ──────────────────────────────────────────────────────────────

const ITEM_TYPE = 'VISUALIZATION_CARD';
const REFLOW_DURATION_MS = 300;
const RESIZE_RERENDER_MS = 200;

// ─── Drag Item Shape ────────────────────────────────────────────────────────

interface DragItem {
  id: string;
  col: number;
  row: number;
}

// ─── Drop Cell Component ────────────────────────────────────────────────────

interface DropCellProps {
  col: number;
  row: number;
  occupied: boolean;
  pinnedOccupied: boolean;
  onDrop: (item: DragItem, targetCol: number, targetRow: number) => void;
  children?: React.ReactNode;
}

function DropCell({ col, row, occupied, pinnedOccupied, onDrop, children }: DropCellProps) {
  const [{ isOver, canDrop }, dropRef] = useDrop<DragItem, void, { isOver: boolean; canDrop: boolean }>({
    accept: ITEM_TYPE,
    canDrop: (item) => {
      // Reject drops on pinned card positions
      if (pinnedOccupied) return false;
      // Can drop on empty cells or on itself (no-op)
      if (item.col === col && item.row === row) return true;
      return !occupied || (item.col === col && item.row === row);
    },
    drop: (item) => {
      if (item.col !== col || item.row !== row) {
        onDrop(item, col, row);
      }
    },
    collect: (monitor) => ({
      isOver: monitor.isOver(),
      canDrop: monitor.canDrop(),
    }),
  });

  const showDropIndicator = isOver && canDrop;
  const showRejectIndicator = isOver && !canDrop;

  return (
    <div
      ref={dropRef as unknown as React.Ref<HTMLDivElement>}
      data-testid={`drop-cell-${col}-${row}`}
      className={`relative min-h-[200px] rounded-lg transition-all duration-150 ${
        showDropIndicator
          ? 'ring-2 ring-blue-400 bg-blue-50/50'
          : showRejectIndicator
            ? 'ring-2 ring-red-300 bg-red-50/30'
            : ''
      }`}
      style={{ gridColumn: `${col + 1}`, gridRow: `${row + 1}` }}
    >
      {showDropIndicator && !children && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-12 h-12 border-2 border-dashed border-blue-400 rounded-lg" />
        </div>
      )}
      {children}
    </div>
  );
}

// ─── Draggable Card Wrapper ─────────────────────────────────────────────────

interface DraggableCardProps {
  card: CardState;
  onResizeStart: (cardId: string, handle: 'br' | 'bl', e: React.MouseEvent) => void;
}

function DraggableCard({ card, onResizeStart }: DraggableCardProps) {
  const [{ isDragging }, dragRef, previewRef] = useDrag<DragItem, void, { isDragging: boolean }>({
    type: ITEM_TYPE,
    item: { id: card.id, col: card.gridPosition.col, row: card.gridPosition.row },
    collect: (monitor) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  return (
    <div
      ref={previewRef as unknown as React.Ref<HTMLDivElement>}
      data-testid={`draggable-card-${card.id}`}
      className={`relative h-full transition-opacity duration-150 ${isDragging ? 'opacity-30' : 'opacity-100'}`}
      style={{
        gridColumn: `${card.gridPosition.col + 1} / span ${card.gridSize.colSpan}`,
        gridRow: `${card.gridPosition.row + 1} / span ${card.gridSize.rowSpan}`,
      }}
    >
      {/* Drag handle area - the entire card header is draggable */}
      <div
        ref={dragRef as unknown as React.Ref<HTMLDivElement>}
        className="absolute top-0 left-0 right-0 h-8 cursor-grab active:cursor-grabbing z-10"
        aria-label="Drag handle"
      />

      <div className="h-full">
        <VisualizationCard card={card} />
      </div>

      {/* Resize handle: bottom-right */}
      <div
        data-testid={`resize-br-${card.id}`}
        className="absolute bottom-0 right-0 w-4 h-4 cursor-nwse-resize z-20 group"
        onMouseDown={(e) => onResizeStart(card.id, 'br', e)}
        aria-label="Resize bottom-right"
      >
        <svg
          className="w-4 h-4 text-gray-400 group-hover:text-blue-500 transition-colors"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M14 14H10L14 10V14ZM14 8L8 14H6L14 6V8ZM14 2L2 14H0L14 0V2Z" opacity="0.5" />
        </svg>
      </div>

      {/* Resize handle: bottom-left */}
      <div
        data-testid={`resize-bl-${card.id}`}
        className="absolute bottom-0 left-0 w-4 h-4 cursor-nesw-resize z-20 group"
        onMouseDown={(e) => onResizeStart(card.id, 'bl', e)}
        aria-label="Resize bottom-left"
      >
        <svg
          className="w-4 h-4 text-gray-400 group-hover:text-blue-500 transition-colors rotate-90"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M14 14H10L14 10V14ZM14 8L8 14H6L14 6V8ZM14 2L2 14H0L14 0V2Z" opacity="0.5" />
        </svg>
      </div>
    </div>
  );
}

// ─── Streaming Skeleton ─────────────────────────────────────────────────────

function StreamingSkeleton() {
  return (
    <div
      data-testid="streaming-skeleton"
      className="col-span-full row-span-full flex items-center justify-center p-8"
    >
      <div className="w-full max-w-md space-y-4 animate-pulse">
        <div className="h-4 bg-gray-200 rounded w-3/4" />
        <div className="h-32 bg-gray-100 rounded" />
        <div className="h-4 bg-gray-200 rounded w-1/2" />
        <div className="flex gap-2">
          <div className="h-3 bg-gray-200 rounded w-16" />
          <div className="h-3 bg-gray-200 rounded w-24" />
          <div className="h-3 bg-gray-200 rounded w-12" />
        </div>
      </div>
    </div>
  );
}

// ─── Empty State ────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div
      data-testid="canvas-empty-state"
      className="col-span-full row-span-full flex flex-col items-center justify-center text-center p-8"
    >
      <svg
        className="w-16 h-16 text-gray-300 mb-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
      <p className="text-gray-400 text-sm">
        Submit a query to see visualizations here
      </p>
    </div>
  );
}

// ─── Canvas Grid (Inner) ────────────────────────────────────────────────────

function CanvasGrid() {
  const cards = useSessionStore((state) => state.cards);
  const loading = useSessionStore((state) => state.loading);
  const moveCard = useSessionStore((state) => state.moveCard);
  const resizeCard = useSessionStore((state) => state.resizeCard);
  const chatThread = useSessionStore((state) => state.chatThread);

  // Get error messages from the chat thread to render as inline error cards
  const errorMessages = chatThread.filter((m) => m.role === 'error');

  const [reflowing, setReflowing] = useState(false);
  const gridRef = useRef<HTMLDivElement>(null);
  const resizeState = useRef<{
    cardId: string;
    handle: 'br' | 'bl';
    startX: number;
    startY: number;
    cellWidth: number;
    cellHeight: number;
    originalSize: { colSpan: ColSpan; rowSpan: RowSpan };
    originalPosition: { col: number; row: number };
  } | null>(null);

  // Build occupied cell map (which cells are taken by which card)
  const buildOccupiedMap = useCallback(() => {
    const map = new Map<string, string>(); // cellKey → cardId
    for (const card of cards) {
      const cells = getOccupiedCells(
        card.gridPosition.col,
        card.gridPosition.row,
        card.gridSize.colSpan,
        card.gridSize.rowSpan,
      );
      for (const cell of cells) {
        map.set(cell, card.id);
      }
    }
    return map;
  }, [cards]);

  // Check if a cell is occupied by a pinned card
  const isPinnedAt = useCallback(
    (col: number, row: number): boolean => {
      return cards.some(
        (card) =>
          card.pinned &&
          col >= card.gridPosition.col &&
          col < card.gridPosition.col + card.gridSize.colSpan &&
          row >= card.gridPosition.row &&
          row < card.gridPosition.row + card.gridSize.rowSpan,
      );
    },
    [cards],
  );

  // Handle drop: swap positions between dragged card and target
  const handleDrop = useCallback(
    (item: DragItem, targetCol: number, targetRow: number) => {
      // Reject if target is pinned
      if (isPinnedAt(targetCol, targetRow)) return;

      const draggedCard = cards.find((c) => c.id === item.id);
      if (!draggedCard) return;

      // Don't move pinned cards
      if (draggedCard.pinned) return;

      // Find card at target position (if any)
      const occupiedMap = buildOccupiedMap();
      const targetCellKey = cellKey(targetCol, targetRow);
      const targetCardId = occupiedMap.get(targetCellKey);

      if (targetCardId && targetCardId !== item.id) {
        const targetCard = cards.find((c) => c.id === targetCardId);
        if (targetCard && targetCard.pinned) return; // Double-check pinned

        // Swap positions
        moveCard(item.id, { col: targetCol, row: targetRow });
        moveCard(targetCardId, { col: item.col, row: item.row });
      } else {
        // Move to empty cell
        moveCard(item.id, { col: targetCol, row: targetRow });
      }

      // Trigger reflow animation
      setReflowing(true);
      setTimeout(() => setReflowing(false), REFLOW_DURATION_MS);
    },
    [cards, moveCard, isPinnedAt, buildOccupiedMap],
  );

  // ─── Resize Handling ────────────────────────────────────────────────────

  const handleResizeStart = useCallback(
    (cardId: string, handle: 'br' | 'bl', e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();

      const card = cards.find((c) => c.id === cardId);
      if (!card || !gridRef.current) return;

      const gridRect = gridRef.current.getBoundingClientRect();
      const cellWidth = gridRect.width / GRID_COLS;
      const cellHeight = gridRect.height / GRID_ROWS;

      resizeState.current = {
        cardId,
        handle,
        startX: e.clientX,
        startY: e.clientY,
        cellWidth,
        cellHeight,
        originalSize: { ...card.gridSize },
        originalPosition: { ...card.gridPosition },
      };

      document.addEventListener('mousemove', handleResizeMove);
      document.addEventListener('mouseup', handleResizeEnd);
    },
    [cards],
  );

  const handleResizeMove = useCallback(
    (e: MouseEvent) => {
      if (!resizeState.current) return;

      const { cardId, handle, startX, startY, cellWidth, cellHeight, originalSize, originalPosition } =
        resizeState.current;

      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;

      // Calculate desired span changes based on mouse movement
      let desiredColSpan: ColSpan = originalSize.colSpan;
      let desiredRowSpan: RowSpan = originalSize.rowSpan;

      // Vertical: increase rowSpan when dragging down
      const rowDelta = Math.round(deltaY / cellHeight);
      const newRowSpan = Math.max(1, Math.min(2, originalSize.rowSpan + rowDelta));
      desiredRowSpan = newRowSpan as RowSpan;

      // Horizontal: depends on handle direction
      if (handle === 'br') {
        const colDelta = Math.round(deltaX / cellWidth);
        const newColSpan = Math.max(1, Math.min(2, originalSize.colSpan + colDelta));
        desiredColSpan = newColSpan as ColSpan;
      } else {
        // Bottom-left: expanding left doesn't make sense in 2-col grid with fixed position
        // Treat as col-span expansion like br for simplicity
        const colDelta = Math.round(-deltaX / cellWidth);
        const newColSpan = Math.max(1, Math.min(2, originalSize.colSpan + colDelta));
        desiredColSpan = newColSpan as ColSpan;
      }

      // Constrain resize
      const otherCards = cards.filter((c) => c.id !== cardId);
      const constrained = constrainResize(
        originalPosition,
        originalSize,
        { colSpan: desiredColSpan, rowSpan: desiredRowSpan },
        otherCards,
      );

      // Only update if size actually changed
      const currentCard = cards.find((c) => c.id === cardId);
      if (
        currentCard &&
        (currentCard.gridSize.colSpan !== constrained.colSpan ||
          currentCard.gridSize.rowSpan !== constrained.rowSpan)
      ) {
        resizeCard(cardId, constrained);
      }
    },
    [cards, resizeCard],
  );

  const handleResizeEnd = useCallback(() => {
    resizeState.current = null;
    document.removeEventListener('mousemove', handleResizeMove);
    document.removeEventListener('mouseup', handleResizeEnd);
  }, [handleResizeMove]);

  // Cleanup resize listeners on unmount
  useEffect(() => {
    return () => {
      document.removeEventListener('mousemove', handleResizeMove);
      document.removeEventListener('mouseup', handleResizeEnd);
    };
  }, [handleResizeMove, handleResizeEnd]);

  // ─── Determine layout mode ──────────────────────────────────────────────

  const useSingleColumn = cards.length < 2;
  const hasCards = cards.length > 0;
  const hasContent = hasCards || errorMessages.length > 0;

  // Build grid cells for drop targets (only unoccupied cells)
  const occupiedMap = buildOccupiedMap();
  const emptyCells: { col: number; row: number }[] = [];
  for (let row = 0; row < GRID_ROWS; row++) {
    for (let col = 0; col < GRID_COLS; col++) {
      const key = cellKey(col, row);
      if (!occupiedMap.has(key)) {
        emptyCells.push({ col, row });
      }
    }
  }

  return (
    <div
      ref={gridRef}
      data-testid="canvas-grid"
      className={`h-full w-full p-4 gap-4 transition-all ${
        reflowing ? 'duration-300' : 'duration-0'
      } ${
        !hasContent || loading
          ? 'flex items-center justify-center'
          : useSingleColumn
            ? 'grid grid-cols-1 auto-rows-fr'
            : 'grid grid-cols-2 grid-rows-3'
      }`}
      style={
        hasContent && !loading && !useSingleColumn
          ? {
              gridTemplateColumns: 'repeat(2, 1fr)',
              gridTemplateRows: 'repeat(3, 1fr)',
            }
          : undefined
      }
    >
      {/* Loading state */}
      {loading && !hasContent && <StreamingSkeleton />}

      {/* Empty state */}
      {!loading && !hasContent && <EmptyState />}

      {/* Cards */}
      {hasContent && !loading && (
        <>
          {cards.map((card) => (
            <DraggableCard
              key={card.id}
              card={card}
              onResizeStart={handleResizeStart}
            />
          ))}

          {/* Empty drop cells for unoccupied positions */}
          {!useSingleColumn &&
            emptyCells.map(({ col, row }) => (
              <DropCell
                key={`empty-${col}-${row}`}
                col={col}
                row={row}
                occupied={false}
                pinnedOccupied={false}
                onDrop={handleDrop}
              />
            ))}
        </>
      )}

      {/* Error cards rendered inline in the conversational thread */}
      {errorMessages.length > 0 && (
        <div
          className="col-span-full flex flex-col gap-3 p-2"
          style={{ gridColumn: '1 / -1' }}
          data-testid="error-cards-container"
        >
          {errorMessages.map((msg) => (
            <ErrorCard key={msg.id} message={msg} />
          ))}
        </div>
      )}

      {/* Loading skeleton overlay when cards exist and new query is in-flight */}
      {loading && hasContent && (
        <div
          data-testid="streaming-skeleton-overlay"
          className="col-span-full flex items-center justify-center p-4"
          style={{
            gridColumn: '1 / -1',
            gridRow: `${Math.min(cards.length + 1, GRID_ROWS)} / span 1`,
          }}
        >
          <div className="animate-pulse flex gap-3 items-center">
            <div className="h-3 w-3 bg-blue-400 rounded-full animate-bounce" />
            <div className="h-3 w-3 bg-blue-300 rounded-full animate-bounce [animation-delay:150ms]" />
            <div className="h-3 w-3 bg-blue-200 rounded-full animate-bounce [animation-delay:300ms]" />
            <span className="text-sm text-gray-400 ml-2">Generating visualization…</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Canvas (Outer with DndProvider) ────────────────────────────────────────

/**
 * Canvas component - fluid-width center panel with a 2×3 CSS Grid for visualization cards.
 *
 * Features:
 * - react-dnd DndProvider with HTML5 backend for drag-and-drop
 * - CSS Grid 2 columns × 3 rows; single-column when <2 cards
 * - Drag-to-reorder with visual drop indicators
 * - Rejects drops on pinned card positions
 * - Reflows cards within 300ms of drop
 * - Resize handles (bottom-right, bottom-left) for 1-2 col/row spans
 * - Constrains resize to grid boundaries, prevents overlap
 * - Re-renders charts within 200ms of resize (via store update → React re-render)
 * - Empty-state message when no cards, streaming skeleton during loading
 *
 * Requirements: 1.3, 1.4, 1.7, 2.7, 2.8, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
 */
export default function Canvas() {
  return (
    <main
      data-testid="canvas"
      className="flex-1 min-w-0 h-full overflow-y-auto bg-white pb-16"
    >
      <CanvasFullNotification />
      <DndProvider backend={HTML5Backend}>
        <CanvasGrid />
      </DndProvider>
    </main>
  );
}
