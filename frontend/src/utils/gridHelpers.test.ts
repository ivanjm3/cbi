import { describe, it, expect } from 'vitest';
import { buildOccupiedSet, nextPosition, constrainResize } from './gridHelpers';
import type { CardState } from '../types/index';

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeCard(
  overrides: Partial<CardState> & { id: string; gridPosition: { col: number; row: number } },
): CardState {
  return {
    id: overrides.id,
    query: overrides.query ?? 'test query',
    renderedOutput: overrides.renderedOutput ?? {
      output_type: 'chart',
      chart_type: 'bar',
      chart_data: {},
      text_content: null,
      description: 'test',
      metadata: { query_id: '1', query_type: 'test' },
    },
    gridPosition: overrides.gridPosition,
    gridSize: overrides.gridSize ?? { colSpan: 1, rowSpan: 1 },
    pinned: overrides.pinned ?? false,
    bookmarked: overrides.bookmarked ?? false,
    createdAt: overrides.createdAt ?? Date.now(),
  };
}

// ---------------------------------------------------------------------------
// buildOccupiedSet
// ---------------------------------------------------------------------------

describe('buildOccupiedSet', () => {
  it('returns empty set for no cards', () => {
    expect(buildOccupiedSet([])).toEqual(new Set());
  });

  it('marks single 1x1 card cell as occupied', () => {
    const cards = [makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } })];
    expect(buildOccupiedSet(cards)).toEqual(new Set(['0,0']));
  });

  it('accounts for colSpan and rowSpan', () => {
    const cards = [
      makeCard({
        id: 'a',
        gridPosition: { col: 0, row: 0 },
        gridSize: { colSpan: 2, rowSpan: 2 },
      }),
    ];
    const occupied = buildOccupiedSet(cards);
    expect(occupied).toEqual(new Set(['0,0', '1,0', '0,1', '1,1']));
  });

  it('excludes card by id', () => {
    const cards = [
      makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } }),
      makeCard({ id: 'b', gridPosition: { col: 1, row: 0 } }),
    ];
    const occupied = buildOccupiedSet(cards, 'a');
    expect(occupied).toEqual(new Set(['1,0']));
  });

  it('handles multiple cards', () => {
    const cards = [
      makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } }),
      makeCard({ id: 'b', gridPosition: { col: 1, row: 1 } }),
      makeCard({ id: 'c', gridPosition: { col: 0, row: 2 } }),
    ];
    const occupied = buildOccupiedSet(cards);
    expect(occupied).toEqual(new Set(['0,0', '1,1', '0,2']));
  });
});

// ---------------------------------------------------------------------------
// nextPosition
// ---------------------------------------------------------------------------

describe('nextPosition', () => {
  it('returns (0,0) for empty canvas', () => {
    expect(nextPosition([])).toEqual({ col: 0, row: 0 });
  });

  it('returns (1,0) when only (0,0) is occupied', () => {
    const cards = [makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } })];
    expect(nextPosition(cards)).toEqual({ col: 1, row: 0 });
  });

  it('skips cells occupied by a 2x1 card', () => {
    const cards = [
      makeCard({
        id: 'a',
        gridPosition: { col: 0, row: 0 },
        gridSize: { colSpan: 2, rowSpan: 1 },
      }),
    ];
    // (0,0) and (1,0) both occupied, next is (0,1)
    expect(nextPosition(cards)).toEqual({ col: 0, row: 1 });
  });

  it('skips cells occupied by a 1x2 card', () => {
    const cards = [
      makeCard({
        id: 'a',
        gridPosition: { col: 0, row: 0 },
        gridSize: { colSpan: 1, rowSpan: 2 },
      }),
    ];
    // (0,0) and (0,1) occupied, next is (1,0)
    expect(nextPosition(cards)).toEqual({ col: 1, row: 0 });
  });

  it('follows LTR-TTB order', () => {
    // Occupy (0,0) and (1,0)
    const cards = [
      makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } }),
      makeCard({ id: 'b', gridPosition: { col: 1, row: 0 } }),
    ];
    expect(nextPosition(cards)).toEqual({ col: 0, row: 1 });
  });

  it('returns null when all cells are occupied', () => {
    const cards = [
      makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } }),
      makeCard({ id: 'b', gridPosition: { col: 1, row: 0 } }),
      makeCard({ id: 'c', gridPosition: { col: 0, row: 1 } }),
      makeCard({ id: 'd', gridPosition: { col: 1, row: 1 } }),
      makeCard({ id: 'e', gridPosition: { col: 0, row: 2 } }),
      makeCard({ id: 'f', gridPosition: { col: 1, row: 2 } }),
    ];
    expect(nextPosition(cards)).toBeNull();
  });

  it('returns null when a 2x2 card and two 1x1 cards fill the grid', () => {
    const cards = [
      makeCard({
        id: 'a',
        gridPosition: { col: 0, row: 0 },
        gridSize: { colSpan: 2, rowSpan: 2 },
      }),
      makeCard({ id: 'b', gridPosition: { col: 0, row: 2 } }),
      makeCard({ id: 'c', gridPosition: { col: 1, row: 2 } }),
    ];
    expect(nextPosition(cards)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// constrainResize
// ---------------------------------------------------------------------------

describe('constrainResize', () => {
  it('allows valid resize within boundaries', () => {
    const cards = [makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } })];
    const result = constrainResize(0, 0, 2, 2, cards, 'a');
    expect(result).toEqual({ colSpan: 2, rowSpan: 2 });
  });

  it('reduces colSpan when card at col 1 tries colSpan 2', () => {
    const cards = [makeCard({ id: 'a', gridPosition: { col: 1, row: 0 } })];
    const result = constrainResize(1, 0, 2, 1, cards, 'a');
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('reduces rowSpan when card at row 2 tries rowSpan 2', () => {
    const cards = [makeCard({ id: 'a', gridPosition: { col: 0, row: 2 } })];
    const result = constrainResize(0, 2, 1, 2, cards, 'a');
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('reduces span when blocked by another card', () => {
    const cards = [
      makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } }),
      makeCard({ id: 'b', gridPosition: { col: 1, row: 0 } }),
    ];
    // Card 'a' at (0,0) tries to expand to 2 cols — blocked by 'b' at (1,0)
    const result = constrainResize(0, 0, 2, 1, cards, 'a');
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('allows colSpan 2 when adjacent cell is free', () => {
    const cards = [makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } })];
    const result = constrainResize(0, 0, 2, 1, cards, 'a');
    expect(result).toEqual({ colSpan: 2, rowSpan: 1 });
  });

  it('allows rowSpan 2 when cell below is free', () => {
    const cards = [makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } })];
    const result = constrainResize(0, 0, 1, 2, cards, 'a');
    expect(result).toEqual({ colSpan: 1, rowSpan: 2 });
  });

  it('reduces rowSpan when cell below is occupied', () => {
    const cards = [
      makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } }),
      makeCard({ id: 'b', gridPosition: { col: 0, row: 1 } }),
    ];
    const result = constrainResize(0, 0, 1, 2, cards, 'a');
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });

  it('works without excludeId', () => {
    const cards = [makeCard({ id: 'a', gridPosition: { col: 0, row: 0 } })];
    // Without exclude, (0,0) is occupied so a 2x1 card at (0,0) overlaps itself
    const result = constrainResize(0, 0, 2, 1, cards);
    expect(result).toEqual({ colSpan: 1, rowSpan: 1 });
  });
});
