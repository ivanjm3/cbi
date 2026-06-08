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
  it('passes through explicit chart_type from backend', () => {
    expect(selectChartType(makeOutput({ chart_type: 'scatter' }))).toBe('scatter');
    expect(selectChartType(makeOutput({ chart_type: 'pie' }))).toBe('pie');
    expect(selectChartType(makeOutput({ chart_type: 'heatmap' }))).toBe('heatmap');
  });

  it('returns "text" for text-only output_type', () => {
    expect(selectChartType(makeOutput({ output_type: 'text', chart_type: null }))).toBe('text');
  });

  it('returns "line" for time-series + numeric columns', () => {
    const result = selectChartType(
      makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'trend',
          columns: [
            { name: 'date', type: 'time-series' },
            { name: 'revenue', type: 'numeric' },
          ],
        },
      }),
    );
    expect(result).toBe('line');
  });

  it('returns "bar" for categorical + numeric columns', () => {
    const result = selectChartType(
      makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'aggregation',
          columns: [
            { name: 'region', type: 'categorical', cardinality: 10 },
            { name: 'revenue', type: 'numeric' },
          ],
        },
      }),
    );
    expect(result).toBe('bar');
  });

  it('returns "scatter" for exactly 2 numeric columns with no categorical', () => {
    const result = selectChartType(
      makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'correlation',
          columns: [
            { name: 'height', type: 'numeric' },
            { name: 'weight', type: 'numeric' },
          ],
        },
      }),
    );
    expect(result).toBe('scatter');
  });

  it('returns "bar" for categorical + numeric (bar rule matches before pie)', () => {
    // Per the design spec, the bar rule (categorical >= 1 && numeric >= 1) is checked
    // before the pie rule, so categorical + numeric always yields bar
    const result = selectChartType(
      makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'breakdown',
          columns: [
            { name: 'category', type: 'categorical', cardinality: 5 },
            { name: 'count', type: 'numeric' },
          ],
        },
      }),
    );
    expect(result).toBe('bar');
  });

  it('returns "bar" for categorical + numeric even with high cardinality', () => {
    const result = selectChartType(
      makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'breakdown',
          columns: [
            { name: 'category', type: 'categorical', cardinality: 12 },
            { name: 'count', type: 'numeric' },
          ],
        },
      }),
    );
    expect(result).toBe('bar');
  });

  it('returns "heatmap" for 3+ numeric columns', () => {
    const result = selectChartType(
      makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'matrix',
          columns: [
            { name: 'x', type: 'numeric' },
            { name: 'y', type: 'numeric' },
            { name: 'z', type: 'numeric' },
          ],
        },
      }),
    );
    expect(result).toBe('heatmap');
  });

  it('returns "table" as fallback when no rules match', () => {
    const result = selectChartType(
      makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'unknown',
          columns: [],
        },
      }),
    );
    expect(result).toBe('table');
  });

  it('returns "table" when columns are absent from metadata', () => {
    const result = selectChartType(
      makeOutput({
        metadata: { query_id: 'q1', query_type: 'unknown' },
      }),
    );
    expect(result).toBe('table');
  });

  it('prefers explicit chart_type even when inference would differ', () => {
    const result = selectChartType(
      makeOutput({
        chart_type: 'table',
        metadata: {
          query_id: 'q1',
          query_type: 'trend',
          columns: [
            { name: 'date', type: 'time-series' },
            { name: 'value', type: 'numeric' },
          ],
        },
      }),
    );
    expect(result).toBe('table');
  });

  it('returns "bar" when categorical has no cardinality defined', () => {
    const result = selectChartType(
      makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'breakdown',
          columns: [
            { name: 'category', type: 'categorical' }, // no cardinality field
            { name: 'count', type: 'numeric' },
          ],
        },
      }),
    );
    // bar rule matches first (categorical >= 1 && numeric >= 1)
    expect(result).toBe('bar');
  });
});
