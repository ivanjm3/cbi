/**
 * Grid placement and resize helpers for the 2×3 canvas grid.
 *
 * Functions:
 * - buildOccupiedSet: builds a set of occupied cell keys from card states
 * - nextPosition: finds the first unoccupied cell in LTR-TTB order
 * - constrainResize: ensures a resize stays within grid boundaries and avoids overlap
 */

import type { CardState } from '../types/index';
import { GRID_COLS, GRID_ROWS, ALL_POSITIONS, positionKey } from '../types/grid';

// ---------------------------------------------------------------------------
// buildOccupiedSet
// ---------------------------------------------------------------------------

/**
 * Build a Set of occupied cell keys (e.g. "0,1") from the current cards,
 * accounting for each card's colSpan and rowSpan.
 *
 * @param cards - Current cards on the canvas
 * @param excludeId - Optional card ID to exclude (useful when resizing a card)
 * @returns Set of occupied cell keys in "col,row" format
 */
export function buildOccupiedSet(cards: CardState[], excludeId?: string): Set<string> {
  const occupied = new Set<string>();

  for (const card of cards) {
    if (excludeId && card.id === excludeId) continue;

    const { col, row } = card.gridPosition;
    const { colSpan, rowSpan } = card.gridSize;

    for (let c = col; c < col + colSpan; c++) {
      for (let r = row; r < row + rowSpan; r++) {
        occupied.add(positionKey(c, r));
      }
    }
  }

  return occupied;
}

// ---------------------------------------------------------------------------
// nextPosition
// ---------------------------------------------------------------------------

/**
 * Find the next available grid position for a new 1×1 card.
 *
 * Iterates positions in left-to-right, top-to-bottom order:
 * (0,0), (1,0), (0,1), (1,1), (0,2), (1,2)
 *
 * @param cards - Current cards on the canvas
 * @returns The first unoccupied position, or null if all cells are occupied
 */
export function nextPosition(cards: CardState[]): { col: number; row: number } | null {
  const occupied = buildOccupiedSet(cards);

  for (const pos of ALL_POSITIONS) {
    if (!occupied.has(positionKey(pos.col, pos.row))) {
      return { col: pos.col, row: pos.row };
    }
  }

  return null;
}

// ---------------------------------------------------------------------------
// constrainResize
// ---------------------------------------------------------------------------

/**
 * Constrain a resize operation to ensure it stays within grid boundaries
 * and doesn't overlap other cards.
 *
 * If the requested span violates grid boundaries or overlaps occupied cells,
 * reduce the span to the maximum valid size.
 *
 * @param col - Column position of the card being resized
 * @param row - Row position of the card being resized
 * @param colSpan - Requested column span (1 or 2)
 * @param rowSpan - Requested row span (1 or 2)
 * @param cards - Current cards on the canvas
 * @param excludeId - ID of the card being resized (excluded from overlap check)
 * @returns Constrained span that fits within boundaries and avoids overlap
 */
export function constrainResize(
  col: number,
  row: number,
  colSpan: 1 | 2,
  rowSpan: 1 | 2,
  cards: CardState[],
  excludeId?: string,
): { colSpan: 1 | 2; rowSpan: 1 | 2 } {
  const occupied = buildOccupiedSet(cards, excludeId);

  // Clamp to grid boundaries
  let validColSpan: 1 | 2 = (col + colSpan <= GRID_COLS ? colSpan : 1) as 1 | 2;
  let validRowSpan: 1 | 2 = (row + rowSpan <= GRID_ROWS ? rowSpan : 1) as 1 | 2;

  // Check overlap for the requested colSpan × rowSpan area and reduce if needed
  // Try the full requested area first, then reduce rowSpan, then colSpan
  if (!isAreaFree(col, row, validColSpan, validRowSpan, occupied)) {
    // Try reducing rowSpan first
    if (validRowSpan === 2 && isAreaFree(col, row, validColSpan, 1, occupied)) {
      validRowSpan = 1;
    }
    // Try reducing colSpan
    else if (validColSpan === 2 && isAreaFree(col, row, 1, validRowSpan, occupied)) {
      validColSpan = 1;
    }
    // Reduce both
    else {
      validColSpan = 1;
      validRowSpan = 1;
    }
  }

  return { colSpan: validColSpan, rowSpan: validRowSpan };
}

// ---------------------------------------------------------------------------
// Helpers (internal)
// ---------------------------------------------------------------------------

/**
 * Check if all cells in the area starting at (col, row) with given spans are free.
 */
function isAreaFree(
  col: number,
  row: number,
  colSpan: number,
  rowSpan: number,
  occupied: Set<string>,
): boolean {
  for (let c = col; c < col + colSpan; c++) {
    for (let r = row; r < row + rowSpan; r++) {
      if (occupied.has(positionKey(c, r))) {
        return false;
      }
    }
  }
  return true;
}
