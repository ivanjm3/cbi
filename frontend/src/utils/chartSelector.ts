import type { RenderedOutput } from '../types';

/** Supported chart types for visualization rendering */
export type ChartType = 'bar' | 'line' | 'scatter' | 'pie' | 'table' | 'heatmap' | 'text';

/**
 * Determines the chart type to render for a given backend response.
 *
 * Selection priority:
 * 1. Explicit `chart_type` from the backend (pass-through)
 * 2. Text-only output type → 'text'
 * 3. Inferred from column metadata:
 *    - time-series + numeric → line
 *    - categorical + numeric → bar
 *    - 2 numeric (no categorical) → scatter
 *    - categorical (cardinality ≤8) + 1 numeric → pie
 *    - 3+ numeric → heatmap
 *    - else → table (fallback)
 */
export function selectChartType(renderedOutput: RenderedOutput): ChartType {
  // 1. Explicit backend instruction
  if (renderedOutput.chart_type) return renderedOutput.chart_type;

  // 2. Text-only response
  if (renderedOutput.output_type === 'text') return 'text';

  // 3. Infer from data shape
  const columns = renderedOutput.metadata?.columns ?? [];
  const hasTime = columns.some(c => c.type === 'time-series');
  const numericCols = columns.filter(c => c.type === 'numeric');
  const categoricalCols = columns.filter(c => c.type === 'categorical');

  if (hasTime && numericCols.length >= 1) return 'line';
  if (categoricalCols.length >= 1 && numericCols.length >= 1) return 'bar';
  if (numericCols.length === 2 && categoricalCols.length === 0) return 'scatter';
  if (
    categoricalCols.length >= 1 &&
    numericCols.length === 1 &&
    (categoricalCols[0]?.cardinality ?? 9) <= 8
  ) return 'pie';
  if (numericCols.length >= 3) return 'heatmap';

  return 'table'; // fallback
}
