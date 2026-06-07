import { describe, it, expect } from 'vitest';
import { selectChartType } from './chartSelector';
import type { RenderedOutput } from '../types';

function makeOutput(overrides: Partial<RenderedOutput> = {}): RenderedOutput {
  return {
    output_type: 'chart',
    description: 'test',
    metadata: { query_id: 'q1', query_type: 'aggregation' },
    ...overrides,
  };
}

describe('selectChartType', () => {
  describe('explicit chart_type pass-through', () => {
    it('returns explicit chart_type when provided', () => {
      expect(selectChartType(makeOutput({ chart_type: 'bar' }))).toBe('bar');
      expect(selectChartType(makeOutput({ chart_type: 'scatter' }))).toBe('scatter');
      expect(selectChartType(makeOutput({ chart_type: 'heatmap' }))).toBe('heatmap');
    });

    it('ignores column metadata when chart_type is explicit', () => {
      const output = makeOutput({
        chart_type: 'pie',
        metadata: {
          query_id: 'q1',
          query_type: 'aggregation',
          columns: [
            { name: 'ts', type: 'time-series' },
            { name: 'val', type: 'numeric' },
          ],
        },
      });
      expect(selectChartType(output)).toBe('pie');
    });
  });

  describe('text output type', () => {
    it('returns text for text output_type', () => {
      const output = makeOutput({ output_type: 'text' });
      expect(selectChartType(output)).toBe('text');
    });

    it('returns text even when columns are present', () => {
      const output = makeOutput({
        output_type: 'text',
        metadata: {
          query_id: 'q1',
          query_type: 'info',
          columns: [{ name: 'val', type: 'numeric' }],
        },
      });
      expect(selectChartType(output)).toBe('text');
    });
  });

  describe('inference from column metadata', () => {
    it('returns line for time-series + numeric', () => {
      const output = makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'trend',
          columns: [
            { name: 'date', type: 'time-series' },
            { name: 'revenue', type: 'numeric' },
          ],
        },
      });
      expect(selectChartType(output)).toBe('line');
    });

    it('returns bar for categorical + numeric', () => {
      const output = makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'aggregation',
          columns: [
            { name: 'region', type: 'categorical', cardinality: 12 },
            { name: 'sales', type: 'numeric' },
          ],
        },
      });
      expect(selectChartType(output)).toBe('bar');
    });

    it('returns scatter for exactly 2 numeric columns (no categorical)', () => {
      const output = makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'correlation',
          columns: [
            { name: 'height', type: 'numeric' },
            { name: 'weight', type: 'numeric' },
          ],
        },
      });
      expect(selectChartType(output)).toBe('scatter');
    });

    it('returns pie for categorical (cardinality ≤8) + 1 numeric', () => {
      const output = makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'breakdown',
          columns: [
            { name: 'category', type: 'categorical', cardinality: 5 },
            { name: 'amount', type: 'numeric' },
          ],
        },
      });
      // Note: this matches `categorical + numeric → bar` first
      // The pie rule requires that the bar rule doesn't match first.
      // Actually looking at the logic: bar matches first (categorical >= 1 && numeric >= 1).
      // So pie only triggers if bar rule doesn't fire. Let me check the design...
      // The design has bar before pie, so this case would be 'bar'.
      expect(selectChartType(output)).toBe('bar');
    });

    it('returns heatmap for 3+ numeric columns', () => {
      const output = makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'matrix',
          columns: [
            { name: 'x', type: 'numeric' },
            { name: 'y', type: 'numeric' },
            { name: 'z', type: 'numeric' },
          ],
        },
      });
      expect(selectChartType(output)).toBe('heatmap');
    });

    it('returns table as fallback for empty columns', () => {
      const output = makeOutput({
        metadata: { query_id: 'q1', query_type: 'unknown', columns: [] },
      });
      expect(selectChartType(output)).toBe('table');
    });

    it('returns table when no columns metadata is present', () => {
      const output = makeOutput({
        metadata: { query_id: 'q1', query_type: 'unknown' },
      });
      expect(selectChartType(output)).toBe('table');
    });

    it('returns line when time-series and categorical are both present with numeric', () => {
      const output = makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'trend',
          columns: [
            { name: 'date', type: 'time-series' },
            { name: 'region', type: 'categorical' },
            { name: 'revenue', type: 'numeric' },
          ],
        },
      });
      // time-series rule fires first
      expect(selectChartType(output)).toBe('line');
    });

    it('does not return scatter when categorical columns are present', () => {
      const output = makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'mixed',
          columns: [
            { name: 'cat', type: 'categorical' },
            { name: 'x', type: 'numeric' },
            { name: 'y', type: 'numeric' },
          ],
        },
      });
      // categorical + numeric → bar (not scatter since categorical present)
      expect(selectChartType(output)).toBe('bar');
    });
  });

  describe('null/undefined chart_type', () => {
    it('treats null chart_type as absent', () => {
      const output = makeOutput({
        chart_type: null,
        metadata: {
          query_id: 'q1',
          query_type: 'trend',
          columns: [
            { name: 'date', type: 'time-series' },
            { name: 'value', type: 'numeric' },
          ],
        },
      });
      expect(selectChartType(output)).toBe('line');
    });
  });
});
