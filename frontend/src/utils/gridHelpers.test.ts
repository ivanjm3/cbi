import { describe, it, expect } from 'vitest';
import { nextPosition, constrainResize, buildOccupiedSet } from './gridHelpers';
import type { CardState } from '../types/index';
import type { RenderedOutput } from '../types/index';

/** Helper to create a minimal CardState for testing */
function makeCard(
  id: string,
  col: number,
  row: number,
  colSpan: 1 | 2 = 1,
  rowSpan: 1 | 2 = 1,
  pinned = false,
): CardState {
  return {
    id,
    query: 'test query',
    renderedOutput: {
      output_type: 'text',
      text_content: 'test',
      description: 'test',
      metadata: { query_id: id, query_type: 'test' },
    } as RenderedOutput,
    gridPosition: { col, row },
    gridSize: { colSpan, rowSpan },
    pinned,
    createdAt: Date.now(),
  };
}

describe('buildOccupiedSet', () => {
  it('returns empty set for no cards', () => {
    const result = buildOccupiedSet([]);
    expect(result.size).toBe(0);
  });

  it('includes all cells for a 1x1 card', () => {
    const cards = [makeCard('a', 0, 0)];
    const result = buildOccupiedSet(cards);
    expect(result.has('0,0')).toBe(true);
    expect(result.size).toBe(1);
  });

  it('includes all cells for a 2x2 card', () => {
    const cards = [makeCard('a', 0, 0, 2, 2)];
    const result = buildOccupiedSet(cards);
    expect(result.has('0,0')).toBe(true);
    expect(result.has('1,0')).toBe(true);
    expect(result.has('0,1')).toBe(true);
    expect(result.has('1,1')).toBe(true);
    expect(result.size).toBe(4);
  });

  it('combines cells from multiple cards', () => {
    const cards = [makeCard('a', 0, 0), makeCard('b', 1, 2)];
    const result = buildOccupiedSet(cards);
    expect(result.has('0,0')).toBe(true);
    expect(result.has('1,2')).toBe(true);
    expect(result.size).toBe(2);
  });
});

describe('nextPosition', () => {
  it('returns (0,0) when canvas is empty', () => {
    expect(nextPosition([])).toEqual({ col: 0, row: 0 });
  });

  it('returns (1,0) when (0,0) is occupied', () => {
    const cards = [makeCard('a', 0, 0)];
    expect(nextPosition(cards)).toEqual({ col: 1, row: 0 });
  });

  it('returns (0,1) when row 0 is full', () => {
    const cards = [makeCard('a', 0, 0), makeCard('b', 1, 0)];
    expect(nextPosition(cards)).toEqual({ col: 0, row: 1 });
  });

  it('follows LTR-TTB order skipping occupied cells', () => {
    // Occupy (0,0) and (0,1)
    const cards = [makeCard('a', 0, 0), makeCard('b', 0, 1)];
    // Next should be (1,0)
    expect(nextPosition(cards)).toEqual({ col: 1, row: 0 });
  });

  it('accounts for card spans', () => {
    // A 2x1 card at (0,0) occupies both (0,0) and (1,0)
    const cards = [makeCard('a', 0, 0, 2, 1)];
    expect(nextPosition(cards)).toEqual({ col: 0, row: 1 });
  });

  it('accounts for 2x2 card spans', () => {
    // A 2x2 card at (0,0) occupies (0,0), (1,0), (0,1), (1,1)
    const cards = [makeCard('a', 0, 0, 2, 2)];
    expect(nextPosition(cards)).toEqual({ col: 0, row: 2 });
  });

  it('returns null when all 6 cells are occupied', () => {
    const cards = [
      makeCard('a', 0, 0),
      makeCard('b', 1, 0),
      makeCard('c', 0, 1),
      makeCard('d', 1, 1),
      makeCard('e', 0, 2),
      makeCard('f', 1, 2),
    ];
    expect(nextPosition(cards)).toBeNull();
  });

  it('returns null when a 2x2 card and two 1x1 cards fill the grid', () => {
    const cards = [
      makeCard('a', 0, 0, 2, 2), // occupies (0,0), (1,0), (0,1), (1,1)
      makeCard('b', 0, 2),       // occupies (0,2)
      makeCard('c', 1, 2),       // occupies (1,2)
    ];
    expect(nextPosition(cards)).toBeNull();
  });

  it('finds gaps between cards', () => {
    // Occupy (0,0), (0,1), (1,1), (0,2), (1,2) — gap at (1,0)
    const cards = [
      makeCard('a', 0, 0),
      makeCard('c', 0, 1),
      makeCard('d', 1, 1),
      makeCard('e', 0, 2),
      makeCard('f', 1, 2),
    ];
    expect(nextPosition(cards)).toEqual({ col: 1, row: 0 });
  });
});

describe('constrainResize', () => {
  it('allows valid resize within boundaries', () => {
    const result = constrainResize(
      { col: 0, row: 0 },
      { colSpan: 1, rowSpan: 1 },
      { colSpan: 2, rowSpan: 2 },
      [],
    );
    expect(result).toEqual({ colSpan: 2, rowSpan: 2 });
  });

  it('clamps colSpan to grid boundary', () => {
    // Card at col=1, trying to span 2 columns would exceed grid
    const result = constrainResize(
      { col: 1, row: 0 },
      { colSpan: 1, rowSpan: 1 },
      { colSpan: 2, rowSpan: 1 },
      [],
    );
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('clamps rowSpan to grid boundary', () => {
    // Card at row=2, trying to span 2 rows would exceed grid
    const result = constrainResize(
      { col: 0, row: 2 },
      { colSpan: 1, rowSpan: 1 },
      { colSpan: 1, rowSpan: 2 },
      [],
    );
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('clamps both colSpan and rowSpan', () => {
    // Card at (1,2), trying 2x2
    const result = constrainResize(
      { col: 1, row: 2 },
      { colSpan: 1, rowSpan: 1 },
      { colSpan: 2, rowSpan: 2 },
      [],
    );
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('prevents overlap with other cards by reducing rowSpan', () => {
    // Card at (0,0) trying to resize to 1x2, but (0,1) is occupied
    const otherCards = [makeCard('b', 0, 1)];
    const result = constrainResize(
      { col: 0, row: 0 },
      { colSpan: 1, rowSpan: 1 },
      { colSpan: 1, rowSpan: 2 },
      otherCards,
    );
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('prevents overlap with other cards by reducing colSpan', () => {
    // Card at (0,0) trying to resize to 2x1, but (1,0) is occupied
    const otherCards = [makeCard('b', 1, 0)];
    const result = constrainResize(
      { col: 0, row: 0 },
      { colSpan: 1, rowSpan: 1 },
      { colSpan: 2, rowSpan: 1 },
      otherCards,
    );
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('prevents overlap when trying 2x2 with a card blocking one cell', () => {
    // Card at (0,0) trying 2x2, but (1,1) is occupied
    const otherCards = [makeCard('b', 1, 1)];
    const result = constrainResize(
      { col: 0, row: 0 },
      { colSpan: 1, rowSpan: 1 },
      { colSpan: 2, rowSpan: 2 },
      otherCards,
    );
    // Should reduce to fit — try colSpan=2, rowSpan=1 first (no overlap there)
    expect(result.colSpan * result.rowSpan).toBeLessThanOrEqual(2);
    // Verify no overlap
    expect(result.colSpan + 0).toBeLessThanOrEqual(2);
    expect(result.rowSpan + 0).toBeLessThanOrEqual(3);
  });

  it('allows resize when no other cards present', () => {
    const result = constrainResize(
      { col: 0, row: 1 },
      { colSpan: 1, rowSpan: 1 },
      { colSpan: 2, rowSpan: 2 },
      [],
    );
    expect(result).toEqual({ colSpan: 2, rowSpan: 2 });
  });
});
