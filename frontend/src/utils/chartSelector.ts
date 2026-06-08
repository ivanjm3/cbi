import type { RenderedOutput } from '../types';

/**
 * Supported chart types for visualization rendering.
 */
export type ChartType = 'bar' | 'line' | 'scatter' | 'pie' | 'table' | 'heatmap' | 'text';

/**
 * Selects the appropriate chart type for a given rendered output.
 *
 * Selection priority:
 * 1. Explicit `chart_type` from the backend response (pass-through, normalized)
 * 2. Text-only output → 'text'
 * 3. Inference from column metadata:
 *    - time-series + numeric → line
 *    - categorical + numeric → bar
 *    - 2 numeric (no categorical) → scatter
 *    - categorical (cardinality ≤8) + 1 numeric → pie
 *    - 3+ numeric → heatmap
 *    - else → table (fallback)
 */
export function selectChartType(renderedOutput: RenderedOutput): ChartType {
  // 1. Explicit backend instruction (normalize known aliases)
  if (renderedOutput.chart_type) {
    const ct = renderedOutput.chart_type.toLowerCase();
    if (ct === 'doughnut') return 'pie';
    if (ct === 'bubble') return 'scatter';
    if (ct === 'bar' || ct === 'line' || ct === 'scatter' || ct === 'pie' || ct === 'table' || ct === 'heatmap') {
      return ct;
    }
    // Unknown chart type — fall through to inference or table
  }

  // 2. Text-only response
  if (renderedOutput.output_type === 'text') return 'text';

  // 3. Infer from data shape
  const columns = renderedOutput.metadata?.columns ?? [];
  const hasTime = columns.some((c) => c.type === 'time-series');
  const numericCols = columns.filter((c) => c.type === 'numeric');
  const categoricalCols = columns.filter((c) => c.type === 'categorical');

  if (hasTime && numericCols.length >= 1) return 'line';
  if (categoricalCols.length >= 1 && numericCols.length >= 1) return 'bar';
  if (numericCols.length === 2 && categoricalCols.length === 0) return 'scatter';
  if (
    categoricalCols.length >= 1 &&
    numericCols.length === 1 &&
    (categoricalCols[0]?.cardinality ?? 9) <= 8
  )
    return 'pie';
  if (numericCols.length >= 3) return 'heatmap';

  // If backend gave a chart_type but we don't have column metadata, trust it as table
  if (renderedOutput.chart_type) return 'bar';

  return 'table'; // fallback
}
