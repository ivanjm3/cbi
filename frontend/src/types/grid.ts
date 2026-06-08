/**
 * Grid layout constants and type helpers for the 2×3 canvas grid.
 *
 * The canvas is organized as:
 *   ┌─────────┬─────────┐
 *   │ (0,0)   │ (1,0)   │  row 0
 *   ├─────────┼─────────┤
 *   │ (0,1)   │ (1,1)   │  row 1
 *   ├─────────┼─────────┤
 *   │ (0,2)   │ (1,2)   │  row 2
 *   └─────────┴─────────┘
 *     col 0     col 1
 */

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Number of columns in the canvas grid */
export const GRID_COLS = 2;

/** Number of rows in the canvas grid */
export const GRID_ROWS = 3;

/** Maximum number of cards (1×1) the grid can hold */
export const MAX_CARDS = 6;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** A position in the canvas grid (zero-indexed) */
export type GridPosition = { col: number; row: number };

/** Span of a card in the grid (1 or 2 columns/rows) */
export type GridSize = { colSpan: 1 | 2; rowSpan: 1 | 2 };

// ---------------------------------------------------------------------------
// Constants – position enumeration
// ---------------------------------------------------------------------------

/**
 * All grid positions in left-to-right, top-to-bottom order.
 * This order is used by the card placement algorithm.
 */
export const ALL_POSITIONS: readonly GridPosition[] = [
  { col: 0, row: 0 },
  { col: 1, row: 0 },
  { col: 0, row: 1 },
  { col: 1, row: 1 },
  { col: 0, row: 2 },
  { col: 1, row: 2 },
] as const;

// ---------------------------------------------------------------------------
// Type helpers / guards
// ---------------------------------------------------------------------------

/** Check if a position is within the grid boundaries */
export function isValidPosition(pos: GridPosition): boolean {
  return pos.col >= 0 && pos.col < GRID_COLS && pos.row >= 0 && pos.row < GRID_ROWS;
}

/** Check if a card with given position and size fits within the grid */
export function fitsInGrid(pos: GridPosition, size: GridSize): boolean {
  return (
    pos.col >= 0 &&
    pos.row >= 0 &&
    pos.col + size.colSpan <= GRID_COLS &&
    pos.row + size.rowSpan <= GRID_ROWS
  );
}

/** Convert a grid position to a unique string key (useful for Set/Map lookups) */
export function positionKey(col: number, row: number): string {
  return `${col},${row}`;
}
