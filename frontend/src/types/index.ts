/** Backend response shape (mirrors RenderedOutput pydantic model) */
export interface RenderedOutput {
  output_type: 'chart' | 'text';
  chart_type?: 'bar' | 'line' | 'scatter' | 'pie' | 'table' | 'heatmap' | null;
  chart_data?: Record<string, unknown> | null;
  text_content?: string | null;
  description: string;
  metadata: MetaPayload;
}

export interface MetaPayload {
  query_id: string;
  query_type: string;
  latency_ms?: number;
  row_count?: number;
  columns?: ColumnMeta[];
  timestamp?: string;
  data_sources?: string[];
}

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

/** Canvas card state */
export interface CardState {
  id: string;
  query: string;
  renderedOutput: RenderedOutput;
  gridPosition: { col: number; row: number };
  gridSize: { colSpan: 1 | 2; rowSpan: 1 | 2 };
  pinned: boolean;
  createdAt: number;
}

/** Session store shape */
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
  saveBookmark: (name: string) => void;
  loadBookmark: (id: string) => void;
  deleteBookmark: (id: string) => void;
  startNewChat: () => void;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'system' | 'error';
  content: string;
  cardId?: string;
  timestamp: number;
  /** Error metadata for retry support */
  errorStatus?: number;
  /** Original query text for retry */
  originalQuery?: string;
}

export interface Bookmark {
  id: string;
  name: string;
  savedAt: number;
  chatThread: ChatMessage[];
  cards: CardState[];
}

export interface ThreadSummary {
  id: string;
  firstMessage: string;
  lastActivity: number;
  messageCount: number;
}
