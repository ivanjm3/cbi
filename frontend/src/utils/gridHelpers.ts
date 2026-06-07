import type { CardState } from '../types/index';
import type { GridPosition, GridSize, ColSpan, RowSpan } from '../types/grid';
import {
  GRID_COLS,
  GRID_ROWS,
  GRID_POSITIONS_LTR_TTB,
  cellKey,
  getOccupiedCells,
} from '../types/grid';

/**
 * Build a set of all occupied cell keys from the given cards,
 * accounting for each card's position and span.
 */
export function buildOccupiedSet(cards: CardState[]): Set<string> {
  const occupied = new Set<string>();
  for (const card of cards) {
    const { col, row } = card.gridPosition;
    const { colSpan, rowSpan } = card.gridSize;
    const cells = getOccupiedCells(col, row, colSpan, rowSpan);
    for (const cell of cells) {
      occupied.add(cell);
    }
  }
  return occupied;
}

/**
 * Find the next available grid position for a new card.
 *
 * Iterates positions in left-to-right, top-to-bottom order:
 * (0,0), (1,0), (0,1), (1,1), (0,2), (1,2)
 *
 * Returns the first unoccupied position, or null if all 6 cells are occupied.
 */
export function nextPosition(cards: CardState[]): GridPosition | null {
  const occupied = buildOccupiedSet(cards);

  for (const pos of GRID_POSITIONS_LTR_TTB) {
    const key = cellKey(pos.col, pos.row);
    if (!occupied.has(key)) {
      return { col: pos.col, row: pos.row };
    }
  }

  return null;
}

/**
 * Constrain a resize attempt to fit within grid boundaries and avoid overlapping
 * other occupied cells.
 *
 * @param position - The card's current grid position (col, row)
 * @param currentSize - The card's current size
 * @param desiredSize - The size the user wants to resize to
 * @param otherCards - All other cards on the grid (excluding the card being resized)
 * @returns The constrained size that fits within boundaries and doesn't overlap
 */
export function constrainResize(
  position: { col: number; row: number },
  _currentSize: GridSize,
  desiredSize: GridSize,
  otherCards: CardState[],
): GridSize {
  const { col, row } = position;

  // Clamp to grid boundaries: col + colSpan ≤ GRID_COLS, row + rowSpan ≤ GRID_ROWS
  let colSpan: ColSpan = Math.min(
    desiredSize.colSpan,
    GRID_COLS - col,
  ) as ColSpan;
  let rowSpan: RowSpan = Math.min(
    desiredSize.rowSpan,
    GRID_ROWS - row,
  ) as RowSpan;

  // Ensure at least 1×1
  if (colSpan < 1) colSpan = 1;
  if (rowSpan < 1) rowSpan = 1;

  // Build occupied set from other cards
  const occupied = buildOccupiedSet(otherCards);

  // Check if desired size overlaps with occupied cells; shrink if needed
  // Try desired size first, then fall back to smaller sizes
  if (hasOverlap(col, row, colSpan, rowSpan, occupied)) {
    // Try reducing rowSpan first
    if (rowSpan === 2 && !hasOverlap(col, row, colSpan, 1, occupied)) {
      rowSpan = 1;
    }
    // Try reducing colSpan
    else if (colSpan === 2 && !hasOverlap(col, row, 1, rowSpan, occupied)) {
      colSpan = 1;
    }
    // Try both reduced
    else if (colSpan === 2 && rowSpan === 2 && !hasOverlap(col, row, 1, 1, occupied)) {
      colSpan = 1;
      rowSpan = 1;
    }
    // If even 1x1 overlaps (shouldn't happen for a valid card), return 1x1
    else {
      colSpan = 1;
      rowSpan = 1;
    }
  }

  return { colSpan, rowSpan };
}

/**
 * Check if a card at the given position and size overlaps any occupied cells.
 */
function hasOverlap(
  col: number,
  row: number,
  colSpan: number,
  rowSpan: number,
  occupied: Set<string>,
): boolean {
  for (let c = col; c < col + colSpan; c++) {
    for (let r = row; r < row + rowSpan; r++) {
      if (occupied.has(cellKey(c, r))) {
        return true;
      }
    }
  }
  return false;
}
