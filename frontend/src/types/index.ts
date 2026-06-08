/**
 * Core TypeScript interfaces for the Conversational BI Frontend.
 *
 * These mirror the backend response contract and define the client-side
 * state shapes used throughout the application.
 */

// ---------------------------------------------------------------------------
// Backend response types
// ---------------------------------------------------------------------------

/** Backend response shape (mirrors RenderedOutput pydantic model) */
export interface RenderedOutput {
  output_type: 'chart' | 'text';
  chart_type?: 'bar' | 'line' | 'scatter' | 'pie' | 'table' | 'heatmap' | null;
  chart_data?: Record<string, unknown> | null;
  text_content?: string | null;
  description: string;
  metadata: MetaPayload;
}

/** Metadata returned alongside every query response */
export interface MetaPayload {
  query_id: string;
  query_type: string;
  latency_ms?: number;
  row_count?: number;
  columns?: ColumnMeta[];
  timestamp?: string;
  data_sources?: string[];
}

/** Per-column statistics provided in MetaPayload */
export interface ColumnMeta {
  name: string;
  type: 'numeric' | 'categorical' | 'time-series';
  row_count?: number;
  null_percentage?: number;
  // Numeric stats
  min?: number;
  max?: number;
  mean?: number;
  median?: number;
  std_dev?: number;
  // Categorical stats
  cardinality?: number;
  // Time-series stats
  time_range_start?: string;
  time_range_end?: string;
}

// ---------------------------------------------------------------------------
// Canvas and card state
// ---------------------------------------------------------------------------

/** State of a single visualization card on the canvas */
export interface CardState {
  id: string;
  query: string;
  renderedOutput: RenderedOutput;
  gridPosition: { col: number; row: number };
  gridSize: { colSpan: 1 | 2; rowSpan: 1 | 2 };
  pinned: boolean;
  bookmarked: boolean;
  createdAt: number;
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

/** A single message in the chat thread */
export interface ChatMessage {
  id: string;
  role: 'user' | 'system' | 'error';
  content: string;
  cardId?: string;
  timestamp: number;
  /** HTTP status code for error messages (422, 503, 504, 408) */
  statusCode?: number;
  /** Original query text, stored on error messages for retry */
  originalQuery?: string;
}
}

// ---------------------------------------------------------------------------
// Bookmarks
// ---------------------------------------------------------------------------

/** Session-level bookmark (saves entire workspace state) */
export interface Bookmark {
  id: string;
  name: string;
  savedAt: number;
  chatThread: ChatMessage[];
  cards: CardState[];
  workspaceName: string;
}

/** Per-card bookmark (bookmarks an individual card result) */
export interface CardBookmark {
  id: string;
  cardId: string;
  query: string;
  chartType: string | null;
  savedAt: number;
}

// ---------------------------------------------------------------------------
// Sidebar / Threads
// ---------------------------------------------------------------------------

/** Summary of a chat thread shown in the sidebar history */
export interface ThreadSummary {
  id: string;
  firstMessage: string;
  lastActivity: number;
  messageCount: number;
}

// ---------------------------------------------------------------------------
// Session store
// ---------------------------------------------------------------------------

/** Full session store shape (zustand state + actions) */
export interface SessionState {
  // Canvas
  cards: CardState[];
  activeCardId: string | null;

  // Chat
  chatThread: ChatMessage[];

  // Sidebar
  threads: ThreadSummary[];
  bookmarks: Bookmark[];

  // UI state
  statsPanelCollapsed: boolean;
  loading: boolean;
  workspaceName: string;

  // Actions
  submitQuery: (queryText: string) => Promise<void>;
  addCard: (card: CardState) => void;
  removeCard: (id: string) => void;
  moveCard: (id: string, position: { col: number; row: number }) => void;
  resizeCard: (id: string, size: { colSpan: 1 | 2; rowSpan: 1 | 2 }) => void;
  pinCard: (id: string) => void;
  unpinCard: (id: string) => void;
  setActiveCard: (id: string | null) => void;
  toggleStatsPanel: () => void;
  toggleCardBookmark: (id: string) => void;
  saveBookmark: (name: string) => void;
  loadBookmark: (id: string) => void;
  deleteBookmark: (id: string) => void;
  startNewChat: () => void;
}
