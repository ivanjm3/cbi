/**
 * CardHistoryDropdown Component
 *
 * Displays collapsible section showing:
 * - Original query
 * - System response description
 * - Query metadata
 * - Query execution details
 *
 * Requirement #2: Collapsible chat history in card
 */

import { useState } from 'react';
import type { CardState } from '../types';

export interface CardHistoryDropdownProps {
  card: CardState;
}

export function CardHistoryDropdown({ card }: CardHistoryDropdownProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div className="card-history-dropdown">
      <button
        className="card-history-toggle"
        onClick={toggleExpanded}
        aria-expanded={isExpanded}
        type="button"
      >
        <ChevronIcon expanded={isExpanded} />
        <span>Query History & Details</span>
        {card.renderedOutput?.metadata?.row_count && (
          <span className="badge">{card.renderedOutput.metadata.row_count} rows</span>
        )}
      </button>

      {isExpanded && (
        <div className="card-history-content">
          {/* Original Query */}
          <section className="history-section">
            <h4 className="history-section-title">📋 Original Query</h4>
            <p className="history-query-text">{card.query}</p>
          </section>

          {/* System Response */}
          <section className="history-section">
            <h4 className="history-section-title">💬 System Response</h4>
            <p className="history-response-text">{card.renderedOutput?.description ?? 'No description available.'}</p>
          </section>

          {/* Metadata */}
          {card.renderedOutput.metadata && (
            <section className="history-section">
              <h4 className="history-section-title">📊 Query Details</h4>
              <div className="metadata-grid">
                {card.renderedOutput.metadata.query_id && (
                  <div className="metadata-row">
                    <span className="label">Query ID:</span>
                    <code className="value">{card.renderedOutput.metadata.query_id}</code>
                  </div>
                )}
                {card.renderedOutput.metadata.query_type && (
                  <div className="metadata-row">
                    <span className="label">Type:</span>
                    <span className="value">{card.renderedOutput.metadata.query_type}</span>
                  </div>
                )}
                {card.renderedOutput.metadata.latency_ms && (
                  <div className="metadata-row">
                    <span className="label">Latency:</span>
                    <span className="value">{card.renderedOutput.metadata.latency_ms}ms</span>
                  </div>
                )}
                {card.renderedOutput.metadata.row_count && (
                  <div className="metadata-row">
                    <span className="label">Rows:</span>
                    <span className="value">{card.renderedOutput.metadata.row_count}</span>
                  </div>
                )}
                {card.renderedOutput.metadata.timestamp && (
                  <div className="metadata-row">
                    <span className="label">Timestamp:</span>
                    <span className="value">
                      {new Date(card.renderedOutput.metadata.timestamp).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>
            </section>
          )}

          {/* Data Sources */}
          {card.renderedOutput.metadata?.data_sources &&
            card.renderedOutput.metadata.data_sources.length > 0 && (
              <section className="history-section">
                <h4 className="history-section-title">🗄️ Data Sources</h4>
                <div className="sources-list">
                  {card.renderedOutput.metadata.data_sources.map((source) => (
                    <span key={source} className="source-badge">
                      {source}
                    </span>
                  ))}
                </div>
              </section>
            )}

          {/* Entity References */}
          {card.renderedOutput.metadata?.entity_refs &&
            card.renderedOutput.metadata.entity_refs.length > 0 && (
              <section className="history-section">
                <h4 className="history-section-title">🏷️ Entities</h4>
                <div className="entities-list">
                  {card.renderedOutput.metadata.entity_refs.map((entity) => (
                    <code key={entity} className="entity-ref">
                      {entity}
                    </code>
                  ))}
                </div>
              </section>
            )}

          {/* Column Metadata */}
          {card.renderedOutput.metadata?.columns && card.renderedOutput.metadata.columns.length > 0 && (
            <details className="history-details">
              <summary>📈 Column Details ({card.renderedOutput.metadata.columns.length})</summary>
              <div className="columns-list">
                {card.renderedOutput.metadata.columns.map((col) => (
                  <div key={col.name} className="column-info">
                    <div className="column-name">
                      <strong>{col.name}</strong>
                      <span className="column-type">{col.type}</span>
                    </div>
                    {col.row_count && (
                      <div className="column-stat">
                        Rows: {col.row_count}
                      </div>
                    )}
                    {col.null_percentage !== undefined && (
                      <div className="column-stat">
                        Nulls: {col.null_percentage.toFixed(1)}%
                      </div>
                    )}
                    {col.type === 'numeric' && col.mean !== undefined && (
                      <div className="column-stat">
                        Mean: {col.mean.toFixed(2)} (σ: {col.std_dev?.toFixed(2) ?? 'N/A'})
                      </div>
                    )}
                    {col.type === 'numeric' && col.min !== undefined && (
                      <div className="column-stat">
                        Range: [{col.min.toFixed(2)}, {col.max?.toFixed(2) ?? 'N/A'}]
                      </div>
                    )}
                    {col.type === 'categorical' && col.cardinality !== undefined && (
                      <div className="column-stat">
                        Cardinality: {col.cardinality}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Simple chevron icon that rotates based on expanded state
 */
function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`chevron-icon ${expanded ? 'expanded' : ''}`}
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M6 5L10 9L6 13"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default CardHistoryDropdown;
