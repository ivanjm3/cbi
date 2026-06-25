/**
 * Core TypeScript interfaces for the Conversational BI Frontend.
 *
 * These mirror the backend response contract and define the client-side
 * state shapes used throughout the application. The layout is a
 * conversational chat thread with inline visualization cards (no grid).
 */

// ---------------------------------------------------------------------------
// Chart types
// ---------------------------------------------------------------------------

/** Supported chart visualization types */
export type ChartType = 'bar' | 'line' | 'scatter' | 'pie' | 'radar' | 'table' | 'heatmap';

/** Known chart type keywords for user prompt parsing */
export const CHART_TYPE_KEYWORDS: Record<string, ChartType> = {
  'bar chart': 'bar',
  'bar graph': 'bar',
  'line chart': 'line',
  'line graph': 'line',
  'scatter plot': 'scatter',
  'scatter chart': 'scatter',
  'pie chart': 'pie',
  'pie graph': 'pie',
  'radar chart': 'radar',
  'radar graph': 'radar',
  'spider chart': 'radar',
  'heatmap': 'heatmap',
  'heat map': 'heatmap',
  'table': 'table',
};

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
  /** Indicates if this response is a meta-query (capability/system question) vs data query */
  is_meta_query?: boolean;
  /** Raw data for visualization type conversion (stored for rerendering) */
  raw_data?: Record<string, unknown> | null;
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
  entity_refs?: string[];
  routing_metadata?: Record<string, unknown>;
  /** Backend hint suggesting the user might prefer a visualization for a text-only response */
  ask_for_visualization?: boolean;
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
// Transparency / Traceability
// ---------------------------------------------------------------------------

/** Transparency data for the Traceability Panel */
export interface TransparencyData {
  queryRewrite: string | null;
  structuredIntent: {
    query_id: string;
    query_type: string;
    entity_refs: string[];
    routing_metadata: Record<string, unknown>;
    timestamp: string;
  } | null;
  apiCallSummary: {
    agents: Array<{
      id: string;
      dataSources: string[];
      status: 'success' | 'error' | 'timeout';
    }>;
  } | null;
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
  /** Strand ID for multi-turn conversation management */
  strandId?: string;
}

/** Represents a conversation strand for multi-turn queries */
export interface ConversationStrand {
  id: string;
  cardId: string;
  messages: ChatMessage[];
  context: {
    query: string;
    rawData?: Record<string, unknown>;
    metadata: MetaPayload;
  };
  createdAt: number;
  updatedAt: number;
}

// ---------------------------------------------------------------------------
// Card state (inline in chat thread, no grid positions)
// ---------------------------------------------------------------------------

/** State of a single visualization card inline in the chat thread */
export interface CardState {
  id: string;
  query: string;
  userRequestedChartType?: ChartType | null;
  renderedOutput: RenderedOutput;
  transparencyData: TransparencyData;
  pinned: boolean;
  width: '50%' | '100%';
  createdAt: number;
  /** Current selected visualization type on the card (may differ from original) */
  selectedVisualizationType?: ChartType | 'text' | null;
  /** Available visualization types for this result (for dropdown) */
  availableVisualizationTypes?: (ChartType | 'text')[];
  /** Cache of previously rendered chart types to avoid re-processing */
  renderCache?: Record<string, RenderedOutput>;
}

// ---------------------------------------------------------------------------
// Session store
// ---------------------------------------------------------------------------

/** Full session store shape (zustand state + actions) */
export interface SessionState {
  // Chat thread
  chatThread: ChatMessage[];
  cards: Record<string, CardState>;
  activeCardId: string | null;

  // Conversation strands for multi-turn queries
  strands: Record<string, ConversationStrand>;
  activeStrandId: string | null;

  // Sidebar
  chatHistory: ThreadSummary[];
  savedPrompts: SavedPrompt[];
  sidebarCollapsed: boolean;

  // Panels
  traceabilityPanelVisible: boolean;
  statsPanelCollapsed: boolean;
  loading: boolean;
  strandLoading: Record<string, boolean>;

  // Storage error (user-facing message for quota exceeded, etc.)
  storageError: string | null;

  // Transient query cancellation state (not persisted)
  _activeAbortController: AbortController | null;
  _activeCorrelationId: string | null;

  // Actions
  submitQuery: (queryText: string) => Promise<void>;
  submitFollowUpQuery: (strandId: string, followUpQuery: string) => Promise<void>;
  cancelQuery: () => Promise<void>;
  setActiveCard: (id: string | null) => void;
  pinCard: (id: string) => void;
  unpinCard: (id: string) => void;
  resizeCard: (id: string, width: '50%' | '100%') => void;
  reorderCard: (id: string, newIndex: number) => void;
  changeCardVisualizationType: (cardId: string, newType: ChartType | 'text') => Promise<void>;
  toggleSidebar: () => void;
  toggleTraceabilityPanel: () => void;
  toggleStatsPanel: () => void;
  saveSavedPrompt: (name: string) => void;
  loadSavedPrompt: (id: string) => void;
  deleteSavedPrompt: (id: string) => void;
  startNewChat: () => void;
  clearStorageError: () => void;
  loadChatThread: (id: string) => void;
  deleteChatThread: (id: string) => void;
  renameChatThread: (id: string, newName: string) => void;
  createStrand: (cardId: string) => string;
  deleteStrand: (strandId: string) => void;
}

// ---------------------------------------------------------------------------
// Saved Prompts
// ---------------------------------------------------------------------------

/** A saved prompt (formerly bookmark) preserving full session state */
export interface SavedPrompt {
  id: string;
  name: string;
  savedAt: number;
  chatThread: ChatMessage[];
  cards: CardState[];
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
  /** Full chat thread data for navigation */
  chatThread: ChatMessage[];
  /** Cards associated with this thread */
  cards: CardState[];
}

// ---------------------------------------------------------------------------
// Re-export Scheduled Reports types
// ---------------------------------------------------------------------------

export type {
  RecurrencePattern,
  ScheduledReportStatus,
  ExecutionStatus,
  ScheduledReportDetail,
  ScheduledReportListItem,
  ExecutionHistoryItem,
  ExecutionHistoryResponse,
  CreateReportRequest,
  UpdateReportRequest,
  CreateReportResponse,
  ListReportsResponse,
  ScheduledReportsState,
} from './scheduledReports';
