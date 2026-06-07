import { useState } from 'react';
import type { MetaPayload } from '../types';

interface TransparencyDrawerProps {
  /** The description field from RenderedOutput — paraphrased query rewrite */
  description?: string | null;
  /** The metadata payload from RenderedOutput */
  metadata?: MetaPayload | null;
}

/**
 * TransparencyDrawer — collapsible "How I got this" drawer displayed below
 * a visualization card. Shows query interpretation details in three sections.
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4
 */
export function TransparencyDrawer({ description, metadata }: TransparencyDrawerProps) {
  const [expanded, setExpanded] = useState(false);

  const hasStructuredIntent =
    metadata?.query_id || metadata?.query_type || metadata?.timestamp;

  const hasApiCallData =
    (metadata?.data_sources && metadata.data_sources.length > 0) ||
    metadata?.latency_ms != null ||
    metadata?.row_count != null;

  return (
    <div className="border-t border-gray-200 mt-2">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center justify-between px-3 py-2 text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-50 transition-colors"
        aria-expanded={expanded}
        aria-controls="transparency-drawer-content"
      >
        <span className="font-medium">How I got this</span>
        <span className="text-[10px]">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div
          id="transparency-drawer-content"
          className="px-3 pb-3 space-y-3 text-xs"
        >
          {/* Section 1: Paraphrased Query Rewrite (Req 3.2) */}
          <section>
            <h4 className="font-semibold text-gray-700 mb-1">Query Rewrite</h4>
            {description ? (
              <p className="text-gray-600">{description}</p>
            ) : (
              <p className="text-gray-400 italic">Data not available</p>
            )}
          </section>

          {/* Section 2: Structured Intent JSON (Req 3.2) */}
          <section>
            <h4 className="font-semibold text-gray-700 mb-1">Structured Intent</h4>
            {hasStructuredIntent ? (
              <pre className="bg-gray-50 rounded p-2 text-[11px] text-gray-600 overflow-x-auto">
                {JSON.stringify(
                  {
                    query_id: metadata!.query_id ?? null,
                    query_type: metadata!.query_type ?? null,
                    timestamp: metadata!.timestamp ?? null,
                  },
                  null,
                  2
                )}
              </pre>
            ) : (
              <p className="text-gray-400 italic">Data not available</p>
            )}
          </section>

          {/* Section 3: API Call Summary (Req 3.2) */}
          <section>
            <h4 className="font-semibold text-gray-700 mb-1">API Call Summary</h4>
            {hasApiCallData ? (
              <div className="space-y-1.5">
                {metadata!.data_sources && metadata!.data_sources.length > 0 && (
                  <div>
                    <span className="text-gray-500">Data sources:</span>
                    <ul className="list-disc list-inside text-gray-600 ml-1">
                      {metadata!.data_sources.map((source) => (
                        <li key={source}>{source}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {metadata!.latency_ms != null && (
                  <p className="text-gray-600">
                    <span className="text-gray-500">Latency:</span> {metadata!.latency_ms}ms
                  </p>
                )}
                {metadata!.row_count != null && (
                  <p className="text-gray-600">
                    <span className="text-gray-500">Rows returned:</span> {metadata!.row_count}
                  </p>
                )}
              </div>
            ) : (
              <p className="text-gray-400 italic">Data not available</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}

export default TransparencyDrawer;
