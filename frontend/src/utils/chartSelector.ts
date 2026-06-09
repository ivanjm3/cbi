import type { RenderedOutput, ChartType as BaseChartType } from '../types';
import { CHART_TYPE_KEYWORDS } from '../types';

/**
 * Supported chart types for visualization rendering.
 * Includes 'text' as a rendering-only type (not something users can request).
 */
export type ChartType = BaseChartType | 'text';

/**
 * Parse user-requested chart type from query text.
 * Scans for known chart type keywords and returns the matching type, or null if none found.
 */
export function parseUserRequestedChartType(queryText: string): BaseChartType | null {
  const lower = queryText.toLowerCase();
  for (const [keyword, chartType] of Object.entries(CHART_TYPE_KEYWORDS)) {
    if (lower.includes(keyword)) return chartType;
  }
  return null;
}

/**
 * Selects the appropriate chart type for a given rendered output.
 *
 * Selection priority:
 * 1. User explicitly requested a chart type in their prompt (highest priority)
 * 2. Backend specified `chart_type` (second priority)
 * 3. Text-only output → 'text'
 * 4. Inference from column metadata:
 *    - time-series + numeric → line
 *    - categorical + numeric → bar
 *    - 2 numeric (no categorical) → scatter
 *    - categorical (cardinality ≤8) + 1 numeric → pie
 *    - 3+ numeric → heatmap
 *    - else → table (fallback)
 */
export function selectChartType(
  renderedOutput: RenderedOutput,
  userRequestedType?: BaseChartType | null
): ChartType {
  // 1. User explicitly requested a chart type — highest priority
  if (userRequestedType) return userRequestedType;

  // 2. Backend specified chart type (normalize known aliases)
  if (renderedOutput.chart_type) {
    const ct = renderedOutput.chart_type.toLowerCase();
    if (ct === 'doughnut' || ct === 'polararea') return 'pie';
    if (ct === 'bubble') return 'scatter';
    if (ct === 'radar') return 'radar';
    if (ct === 'bar' || ct === 'line' || ct === 'scatter' || ct === 'pie' || ct === 'table' || ct === 'heatmap') {
      return ct;
    }
    // Unknown chart type — fall through to inference or table
  }

  // 3. Text-only response
  if (renderedOutput.output_type === 'text') return 'text';

  // 4. Infer from data shape
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
