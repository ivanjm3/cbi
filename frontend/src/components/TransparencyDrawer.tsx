/**
 * TransparencyDrawer component.
 *
 * Collapsible "How I got this" drawer displayed below each visualization card.
 * Defaults to collapsed state. When expanded, shows three labeled sections:
 * 1. Paraphrased query rewrite (natural language interpretation)
 * 2. Structured intent JSON (query_id, query_type, timestamp, etc.)
 * 3. API call summary (data sources, response status)
 *
 * Displays placeholder messages for any section where data is unavailable.
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4
 */

import { useState, useCallback } from 'react';
import type { RenderedOutput } from '../types';

export interface TransparencyDrawerProps {
  renderedOutput: RenderedOutput;
}

/**
 * Section wrapper providing consistent styling for each transparency section.
 */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <h4 className="text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
        {title}
      </h4>
      <div className="text-xs text-gray-600 dark:text-gray-400">{children}</div>
    </div>
  );
}

/**
 * Placeholder shown when a section's data is missing or incomplete.
 */
function Placeholder({ message }: { message: string }) {
  return (
    <p className="italic text-gray-400 dark:text-gray-500">{message}</p>
  );
}

export function TransparencyDrawer({ renderedOutput }: TransparencyDrawerProps) {
  const [isOpen, setIsOpen] = useState(false);

  const handleToggle = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setIsOpen((prev) => !prev);
  }, []);

  const { description, metadata } = renderedOutput;

  // Extract structured intent fields from metadata
  const queryId = metadata?.query_id;
  const queryType = metadata?.query_type;
  const timestamp = metadata?.timestamp;
  const dataSources = metadata?.data_sources;

  // Build structured intent object for display
  const structuredIntent: Record<string, unknown> = {};
  if (queryId) structuredIntent.query_id = queryId;
  if (queryType) structuredIntent.query_type = queryType;
  if (timestamp) structuredIntent.timestamp = timestamp;

  // entity_refs and routing_metadata may be present in extended metadata
  const extendedMeta = metadata as Record<string, unknown> | undefined;
  if (extendedMeta?.entity_refs) structuredIntent.entity_refs = extendedMeta.entity_refs;
  if (extendedMeta?.routing_metadata) structuredIntent.routing_metadata = extendedMeta.routing_metadata;

  const hasStructuredIntent = Object.keys(structuredIntent).length > 0;
  const hasDataSources = dataSources && dataSources.length > 0;

  return (
    <div className="mt-2 border-t border-gray-100 dark:border-gray-800 pt-2">
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={isOpen}
        aria-controls="transparency-drawer-content"
        className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors cursor-pointer select-none"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className={`h-3.5 w-3.5 transition-transform duration-200 ${isOpen ? 'rotate-90' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
        <span>How I got this</span>
      </button>

      {isOpen && (
        <div
          id="transparency-drawer-content"
          role="region"
          aria-label="Query transparency details"
          className="mt-2 p-3 rounded-md bg-gray-50 dark:bg-gray-800 space-y-4"
        >
          {/* Section 1: Paraphrased Query Rewrite */}
          <Section title="Query Interpretation">
            {description ? (
              <p>{description}</p>
            ) : (
              <Placeholder message="Query interpretation data could not be retrieved." />
            )}
          </Section>

          {/* Section 2: Structured Intent JSON */}
          <Section title="Structured Intent">
            {hasStructuredIntent ? (
              <pre className="whitespace-pre-wrap break-all bg-gray-100 dark:bg-gray-900 p-2 rounded text-[11px] font-mono leading-relaxed overflow-x-auto">
                {JSON.stringify(structuredIntent, null, 2)}
              </pre>
            ) : (
              <Placeholder message="Structured intent data could not be retrieved." />
            )}
          </Section>

          {/* Section 3: API Call Summary */}
          <Section title="API Call Summary">
            {hasDataSources ? (
              <div className="space-y-1">
                <div>
                  <span className="font-medium">Data sources queried:</span>{' '}
                  {dataSources!.join(', ')}
                </div>
                {queryType && (
                  <div>
                    <span className="font-medium">Query type:</span> {queryType}
                  </div>
                )}
                <div>
                  <span className="font-medium">Response status:</span>{' '}
                  <span className="text-green-600 dark:text-green-400">Success</span>
                </div>
              </div>
            ) : (
              <Placeholder message="API call summary data could not be retrieved." />
            )}
          </Section>
        </div>
      )}
    </div>
  );
}
