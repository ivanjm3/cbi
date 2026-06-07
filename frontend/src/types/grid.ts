/**
 * Grid position constants and type helpers for the 2×3 canvas grid.
 *
 * Layout:
 * ┌─────────┬─────────┐
 * │ (0,0)   │ (1,0)   │  row 0
 * ├─────────┼─────────┤
 * │ (0,1)   │ (1,1)   │  row 1
 * ├─────────┼─────────┤
 * │ (0,2)   │ (1,2)   │  row 2
 * └─────────┴─────────┘
 *   col 0     col 1
 */

/** Number of columns in the canvas grid */
export const GRID_COLS = 2;

/** Number of rows in the canvas grid */
export const GRID_ROWS = 3;

/** Maximum number of cells in the grid */
export const GRID_MAX_CELLS = GRID_COLS * GRID_ROWS;

/** Valid column indices */
export type GridCol = 0 | 1;

/** Valid row indices */
export type GridRow = 0 | 1 | 2;

/** A position on the grid */
export interface GridPosition {
  col: GridCol;
  row: GridRow;
}

/** Allowed span sizes for cards */
export type ColSpan = 1 | 2;
export type RowSpan = 1 | 2;

/** Card size in grid units */
export interface GridSize {
  colSpan: ColSpan;
  rowSpan: RowSpan;
}

/**
 * All grid positions in left-to-right, top-to-bottom order.
 * Used by the card placement algorithm to find the next available slot.
 */
export const GRID_POSITIONS_LTR_TTB: readonly GridPosition[] = [
  { col: 0, row: 0 },
  { col: 1, row: 0 },
  { col: 0, row: 1 },
  { col: 1, row: 1 },
  { col: 0, row: 2 },
  { col: 1, row: 2 },
] as const;

/**
 * Check if a position is within the grid boundaries.
 */
export function isValidPosition(col: number, row: number): boolean {
  return col >= 0 && col < GRID_COLS && row >= 0 && row < GRID_ROWS;
}

/**
 * Check if a card with given position and size fits within the grid boundaries.
 */
export function fitsInGrid(
  col: number,
  row: number,
  colSpan: ColSpan,
  rowSpan: RowSpan,
): boolean {
  return col + colSpan <= GRID_COLS && row + rowSpan <= GRID_ROWS;
}

/**
 * Convert a grid position to a unique cell key string for use in Sets/Maps.
 */
export function cellKey(col: number, row: number): string {
  return `${col},${row}`;
}

/**
 * Get all cells occupied by a card at the given position with the given span.
 */
export function getOccupiedCells(
  col: number,
  row: number,
  colSpan: ColSpan,
  rowSpan: RowSpan,
): string[] {
  const cells: string[] = [];
  for (let c = col; c < col + colSpan; c++) {
    for (let r = row; r < row + rowSpan; r++) {
      cells.push(cellKey(c, r));
    }
  }
  return cells;
}
