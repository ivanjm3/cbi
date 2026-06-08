/**
 * Property-based test: Column statistics rendered by type (Property 7)
 *
 * For any ColumnMeta[] array, the Stats Panel SHALL render row_count and
 * null_percentage for every column, AND min/max/mean/median/std_dev for
 * columns of type "numeric", AND cardinality for columns of type "categorical",
 * AND time_range_start/time_range_end for columns of type "time-series".
 *
 * **Validates: Requirements 7.2, 7.3, 7.4, 7.5**
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import fc from 'fast-check';
import { StatsPanel } from './StatsPanel';
import { useSessionStore } from '../store/sessionStore';
import type { ColumnMeta, CardState } from '../types';

// ---------------------------------------------------------------------------
// Generators
// ---------------------------------------------------------------------------

/** Generate a valid column name (non-empty alphanumeric) */
const columnNameArb = fc.stringOf(
  fc.constantFrom(...'abcdefghijklmnopqrstuvwxyz0123456789_'.split('')),
  { minLength: 1, maxLength: 20 },
);

/** Generate a numeric ColumnMeta with all stats present */
const numericColumnArb: fc.Arbitrary<ColumnMeta> = fc.record({
  name: columnNameArb,
  type: fc.constant('numeric' as const),
  row_count: fc.nat({ max: 100000 }),
  null_percentage: fc.double({ min: 0, max: 100, noNaN: true }),
  min: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
  max: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
  mean: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
  median: fc.double({ min: -1e6, max: 1e6, noNaN: true }),
  std_dev: fc.double({ min: 0, max: 1e6, noNaN: true }),
});

/** Generate a categorical ColumnMeta with cardinality present */
const categoricalColumnArb: fc.Arbitrary<ColumnMeta> = fc.record({
  name: columnNameArb,
  type: fc.constant('categorical' as const),
  row_count: fc.nat({ max: 100000 }),
  null_percentage: fc.double({ min: 0, max: 100, noNaN: true }),
  cardinality: fc.nat({ max: 10000 }),
});

/** Generate a time-series ColumnMeta with time range present */
const timeSeriesColumnArb: fc.Arbitrary<ColumnMeta> = fc.record({
  name: columnNameArb,
  type: fc.constant('time-series' as const),
  row_count: fc.nat({ max: 100000 }),
  null_percentage: fc.double({ min: 0, max: 100, noNaN: true }),
  time_range_start: fc.date({ min: new Date('2000-01-01'), max: new Date('2030-12-31') }).map(
    (d) => d.toISOString(),
  ),
  time_range_end: fc.date({ min: new Date('2000-01-01'), max: new Date('2030-12-31') }).map(
    (d) => d.toISOString(),
  ),
});

/** Generate a mixed ColumnMeta (any of the three types) */
const columnMetaArb: fc.Arbitrary<ColumnMeta> = fc.oneof(
  numericColumnArb,
  categoricalColumnArb,
  timeSeriesColumnArb,
);

/**
 * Generate an array of ColumnMeta with unique names and mixed types.
 * At least 1 column, at most 8 columns per array.
 */
const columnMetaArrayArb: fc.Arbitrary<ColumnMeta[]> = fc
  .array(columnMetaArb, { minLength: 1, maxLength: 8 })
  .map((cols) => {
    // Ensure unique column names by appending index
    const seen = new Set<string>();
    return cols.map((col, idx) => {
      let name = col.name;
      if (seen.has(name)) {
        name = `${name}_${idx}`;
      }
      seen.add(name);
      return { ...col, name };
    });
  });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildCardWithColumns(columns: ColumnMeta[]): CardState {
  return {
    id: 'test-card',
    query: 'test query',
    renderedOutput: {
      output_type: 'chart',
      chart_type: 'bar',
      chart_data: {},
      text_content: null,
      description: 'Test description',
      metadata: {
        query_id: 'q-test',
        query_type: 'aggregation',
        latency_ms: 100,
        row_count: 1000,
        columns,
      },
    },
    gridPosition: { col: 0, row: 0 },
    gridSize: { colSpan: 1, rowSpan: 1 },
    pinned: false,
    bookmarked: false,
    createdAt: Date.now(),
  };
}

// ---------------------------------------------------------------------------
// Property Test
// ---------------------------------------------------------------------------

describe('Feature: conversational-bi-frontend, Property 7: Column statistics rendered by type', () => {
  beforeEach(() => {
    useSessionStore.setState({
      cards: [],
      activeCardId: null,
      chatThread: [],
      threads: [],
      bookmarks: [],
      statsPanelCollapsed: false,
      loading: false,
      workspaceName: 'Test',
    });
  });

  it('renders correct stat fields for each column type', () => {
    fc.assert(
      fc.property(columnMetaArrayArb, (columns) => {
        // Set up store with a card containing the generated columns
        const card = buildCardWithColumns(columns);
        useSessionStore.setState({ cards: [card], activeCardId: 'test-card' });

        const { container, unmount } = render(
          <StatsPanel collapsed={false} onToggle={() => {}} />,
        );

        // For each column, verify the expected stats are rendered
        for (const col of columns) {
          // Common stats: row_count and null_percentage should be rendered for all columns
          if (col.row_count != null) {
            const formattedRowCount = col.row_count.toLocaleString();
            expect(container.textContent).toContain(formattedRowCount);
          }
          if (col.null_percentage != null) {
            const formattedNull = `${col.null_percentage.toFixed(2)}%`;
            expect(container.textContent).toContain(formattedNull);
          }

          // Type-specific stats
          if (col.type === 'numeric') {
            // min, max, mean, median, std_dev (2 decimal places)
            if (col.min != null) {
              expect(container.textContent).toContain(col.min.toFixed(2));
            }
            if (col.max != null) {
              expect(container.textContent).toContain(col.max.toFixed(2));
            }
            if (col.mean != null) {
              expect(container.textContent).toContain(col.mean.toFixed(2));
            }
            if (col.median != null) {
              expect(container.textContent).toContain(col.median.toFixed(2));
            }
            if (col.std_dev != null) {
              expect(container.textContent).toContain(col.std_dev.toFixed(2));
            }
          }

          if (col.type === 'categorical') {
            // cardinality
            if (col.cardinality != null) {
              expect(container.textContent).toContain(
                col.cardinality.toLocaleString(),
              );
            }
          }

          if (col.type === 'time-series') {
            // time_range_start and time_range_end
            if (col.time_range_start != null) {
              expect(container.textContent).toContain(col.time_range_start);
            }
            if (col.time_range_end != null) {
              expect(container.textContent).toContain(col.time_range_end);
            }
          }
        }

        // Verify labels are present for each type
        const numericCols = columns.filter((c) => c.type === 'numeric');
        const categoricalCols = columns.filter((c) => c.type === 'categorical');
        const timeSeriesCols = columns.filter((c) => c.type === 'time-series');

        if (numericCols.length > 0) {
          expect(container.textContent).toContain('Min');
          expect(container.textContent).toContain('Max');
          expect(container.textContent).toContain('Mean');
          expect(container.textContent).toContain('Median');
          expect(container.textContent).toContain('Std Dev');
        }

        if (categoricalCols.length > 0) {
          expect(container.textContent).toContain('Cardinality');
        }

        if (timeSeriesCols.length > 0) {
          expect(container.textContent).toContain('Start');
          expect(container.textContent).toContain('End');
        }

        // Cleanup for next iteration
        unmount();
      }),
      { numRuns: 100 },
    );
  });
});
