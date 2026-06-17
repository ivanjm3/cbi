/**
 * Chart type conversion utilities for re-rendering visualizations.
 * Converts between chart types while maintaining data integrity.
 */

import type { RenderedOutput, ChartType } from '../types';

/** Metadata needed to re-render a chart in a different type */
export interface RenderableData {
  rawData: Record<string, unknown>;
  metadata: Record<string, unknown>;
  originalChartType: ChartType | null;
}

/**
 * Extract renderable data from a RenderedOutput for type conversion.
 * Returns the data needed to regenerate a visualization in a different type.
 */
export function extractRenderableData(output: RenderedOutput): RenderableData | null {
  if (!output.raw_data) {
    return null;
  }

  return {
    rawData: output.raw_data,
    metadata: output.metadata || {},
    originalChartType: output.chart_type as ChartType | null,
  };
}

/**
 * Generate a prompt for converting a visualization to a different chart type.
 * Sent back to the agent to re-render with the selected type.
 */
export function generateChartTypeConversionPrompt(
  selectedType: ChartType | 'text',
  originalQuery: string,
  rawData: Record<string, unknown>,
): string {
  if (selectedType === 'text') {
    return `
The user has requested to view this data as text instead of a chart.
Original query: "${originalQuery}"

Please provide a clear, analytical text summary of the data that explains:
- Key metrics and findings
- Important patterns or trends
- Actionable insights

Format the response as a readable, professional summary.
    `.trim();
  }

  return `
The user has requested to view this data as a ${selectedType} chart.
Original query: "${originalQuery}"

Please generate a complete Chart.js v4 configuration that displays this data as a ${selectedType} chart.
Ensure the chart is visually clear and highlights the most important insights.

The raw data is: ${JSON.stringify(rawData)}

Remember to:
- Use appropriate styling and colors
- Include clear labels and legends
- Make the chart type selection match the data characteristics
- Provide a 2-4 sentence analytical insight in the description
    `.trim();
}

/**
 * Available visualization types that can be generated from most datasets.
 */
export const AVAILABLE_VIZ_TYPES: (ChartType | 'text')[] = [
  'bar',
  'line',
  'scatter',
  'pie',
  'table',
  'text',
];

/**
 * Determine which visualization types are suitable for the given data.
 * Returns a filtered list based on data characteristics.
 */
export function getAvailableVisualizationTypes(
  output: RenderedOutput,
): (ChartType | 'text')[] {
  // For now, return all types as available
  // In future, could inspect data to determine suitable types
  return AVAILABLE_VIZ_TYPES;
}
