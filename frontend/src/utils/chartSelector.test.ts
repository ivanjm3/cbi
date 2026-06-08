import { describe, it, expect } from 'vitest';
import { selectChartType, parseUserRequestedChartType } from './chartSelector';
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
  describe('Priority 1: User explicitly requested chart type (highest)', () => {
    it('returns user-requested type regardless of backend chart_type', () => {
      const output = makeOutput({ chart_type: 'bar' });
      expect(selectChartType(output, 'scatter')).toBe('scatter');
    });

    it('returns user-requested type regardless of data shape inference', () => {
      const output = makeOutput({
        metadata: {
          query_id: 'q1',
          query_type: 'trend',
          columns: [
            { name: 'date', type: 'time-series' },
            { name: 'value', type: 'numeric' },
          ],
        },
      });
      // Data shape would infer 'line', but user wants 'pie'
      expect(selectChartType(output, 'pie')).toBe('pie');
    });

    it('ignores null userRequestedType and falls through', () => {
      const output = makeOutput({ chart_type: 'bar' });
      expect(selectChartType(output, null)).toBe('bar');
    });

    it('ignores undefined userRequestedType and falls through', () => {
      const output = makeOutput({ chart_type: 'line' });
      expect(selectChartType(output)).toBe('line');
    });
  });

  describe('Priority 2: Backend specified chart_type', () => {
    it('passes through explicit chart_type from backend', () => {
      expect(selectChartType(makeOutput({ chart_type: 'scatter' }))).toBe('scatter');
      expect(selectChartType(makeOutput({ chart_type: 'pie' }))).toBe('pie');
      expect(selectChartType(makeOutput({ chart_type: 'heatmap' }))).toBe('heatmap');
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
  });

  describe('Priority 3: Text-only response', () => {
    it('returns "text" for text-only output_type', () => {
      expect(selectChartType(makeOutput({ output_type: 'text', chart_type: null }))).toBe('text');
    });
  });

  describe('Priority 4: Data shape inference', () => {
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
  });
});

describe('parseUserRequestedChartType', () => {
  it('returns "bar" for "bar chart" keyword', () => {
    expect(parseUserRequestedChartType('show me a bar chart of revenue')).toBe('bar');
  });

  it('returns "line" for "line chart" keyword', () => {
    expect(parseUserRequestedChartType('create a line chart of trends')).toBe('line');
  });

  it('returns "scatter" for "scatter plot" keyword', () => {
    expect(parseUserRequestedChartType('scatter plot of X vs Y')).toBe('scatter');
  });

  it('returns "pie" for "pie chart" keyword', () => {
    expect(parseUserRequestedChartType('display a pie chart of market share')).toBe('pie');
  });

  it('returns "heatmap" for "heatmap" keyword', () => {
    expect(parseUserRequestedChartType('show a heatmap of correlations')).toBe('heatmap');
  });

  it('returns "table" for "table" keyword', () => {
    expect(parseUserRequestedChartType('display data as a table')).toBe('table');
  });

  it('is case-insensitive', () => {
    expect(parseUserRequestedChartType('Show me a BAR CHART')).toBe('bar');
  });

  it('returns null when no keyword is found', () => {
    expect(parseUserRequestedChartType('what is revenue by region')).toBeNull();
  });

  it('returns null for empty string', () => {
    expect(parseUserRequestedChartType('')).toBeNull();
  });
});
