# Implementation Plan: Conversational BI Frontend

## Overview

This plan implements a React 18 + Vite + Tailwind CSS conversational BI frontend with a ChatGPT/Claude-style thread layout, collapsible sidebar, inline visualization cards, a right-side traceability panel toggled via a footer bar, and a professional BI design system. The architecture replaces the previous 2×3 grid canvas with a vertical scrolling chat thread where cards are rendered inline. Implementation proceeds from scaffolding through state management, layout shell, chat UI, visualization components, and final integration.

## Tasks

- [x] 1. Project scaffolding and design system setup
  - [x] 1.1 Initialize Vite + React + TypeScript project in `frontend/`
    - Run `npm create vite@latest` with React-TS template in `frontend/`
    - Install dependencies: tailwindcss, postcss, autoprefixer, recharts, react-dnd, react-dnd-html5-backend, zustand, fast-check, vitest, @testing-library/react, @testing-library/jest-dom, @testing-library/user-event, jsdom, msw, html2canvas
    - Configure `tailwind.config.ts` with design system tokens (colors, shadows, fonts, font sizes from design)
    - Configure `postcss.config.js` and `vite.config.ts`
    - Configure Vitest in `vite.config.ts` with jsdom environment
    - Set up `frontend/src/index.css` with Tailwind directives and Inter/JetBrains Mono font imports
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [x] 1.2 Define TypeScript interfaces and types
    - Create `frontend/src/types/index.ts` with all interfaces: `RenderedOutput`, `MetaPayload`, `ColumnMeta`, `TransparencyData`, `ChatMessage`, `CardState`, `SessionState`, `SavedPrompt`, `ThreadSummary`
    - Define `CardState.width` as `'50%' | '100%'` (no grid positions)
    - Define `ChartType` union type: `'bar' | 'line' | 'scatter' | 'pie' | 'table' | 'heatmap'`
    - Define chart type keyword map for user prompt parsing
    - _Requirements: 4.1, 4.4, 7.1, 9.1, 10.2_

- [x] 2. State management and API layer
  - [x] 2.1 Implement zustand Session Store with localStorage persistence
    - Create `frontend/src/store/sessionStore.ts` with zustand `create` + `persist` middleware
    - Implement state shape: `chatThread`, `cards` (Map by ID), `activeCardId`, `chatHistory`, `savedPrompts`, `sidebarCollapsed`, `traceabilityPanelVisible`, `statsPanelCollapsed`, `loading`
    - Implement actions: `submitQuery`, `setActiveCard`, `pinCard`, `unpinCard`, `resizeCard` (50%/100%), `reorderCard`, `toggleSidebar`, `toggleTraceabilityPanel`, `toggleStatsPanel`, `saveSavedPrompt`, `loadSavedPrompt`, `deleteSavedPrompt`, `startNewChat`
    - Implement localStorage error handling (quota exceeded warning, corrupted data fallback to fresh state)
    - Use `persist` middleware with `cbi-session` key; debounce persistence within 1 second
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 2.2 Implement API integration layer
    - Create `frontend/src/api/queryApi.ts` with `queryBackend` function
    - Implement 60-second timeout with AbortController
    - Handle HTTP 200 (extract `rendered_output` + `metadata`), 422 (extract `error_message`), 503/504 (service unavailable)
    - Compute fallback latency from `performance.now()` when `meta.latency_ms` absent
    - Implement `fetchSession` for `GET /sessions/:id`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [x] 2.3 Implement chart type selection logic with user override parsing
    - Create `frontend/src/utils/chartSelector.ts` with `selectChartType` and `parseUserRequestedChartType` functions
    - Implement keyword parsing from user prompt (highest priority): "bar chart", "line chart", "scatter plot", "pie chart", "heatmap", "table"
    - Implement backend `chart_type` pass-through (second priority)
    - Implement data shape inference (third priority): time-series → line, categorical + numeric → bar, 2 numeric → scatter, categorical ≤8 + 1 numeric → pie, 3+ numeric → heatmap, else → table
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 2.4 Write property test: Whitespace-only queries never submitted (Property 1)
    - **Property 1: Whitespace-only queries are never submitted**
    - Use `fc.string()` filtered to whitespace-only characters
    - Verify `submitQuery` is prevented and no fetch is dispatched
    - **Validates: Requirements 2.3**

  - [ ]* 2.5 Write property test: Chart type selection respects user override (Property 2)
    - **Property 2: Chart type selection respects user override**
    - Generate random `RenderedOutput` + random chart type keyword in query
    - Verify `selectChartType` returns user-requested chart type regardless of backend or data shape
    - **Validates: Requirements 4.1**

  - [ ]* 2.6 Write property test: Chart type selection correctness without user override (Property 3)
    - **Property 3: Chart type selection correctness (no user override)**
    - Generate random `RenderedOutput` with varying column compositions, no user override
    - Verify backend `chart_type` honored when present, inference rules applied when absent
    - **Validates: Requirements 4.2, 4.3**

  - [ ]* 2.7 Write property test: User chart type keyword parsing (Property 12)
    - **Property 12: User chart type keyword parsing**
    - Generate random strings with/without chart type keywords
    - Verify `parseUserRequestedChartType` returns correct enum or null
    - **Validates: Requirements 4.1**

- [x] 3. Checkpoint - Core logic validation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Utility functions and formatters
  - [x] 4.1 Implement CSV export utility
    - Create `frontend/src/utils/csvExport.ts` with `exportCSV` function
    - Handle RFC 4180 escaping: commas, quotes, newlines in cell values
    - Generate column headers as first row, UTF-8 encoded
    - Trigger download via Blob + object URL
    - _Requirements: 5.3_

  - [x] 4.2 Implement PNG export utility
    - Create `frontend/src/utils/pngExport.ts` with `exportPNG` function
    - Use html2canvas to capture chart area
    - Trigger download matching rendered card dimensions
    - Handle export failure with error callback
    - _Requirements: 5.2, 5.7_

  - [x] 4.3 Implement timestamp and latency formatters
    - Create `frontend/src/utils/formatters.ts` with `formatTimestamp` and `formatLatency`
    - `formatLatency(n)` → `↯ {N}ms`
    - `formatTimestamp(date)` → relative time if <24h (e.g., "2 hours ago"), else "YYYY-MM-DD HH:mm"
    - _Requirements: 7.6, 8.2_

  - [ ]* 4.4 Write property test: CSV export structural correctness (Property 4)
    - **Property 4: CSV export structural correctness**
    - Generate random 2D arrays with special characters (commas, quotes, newlines)
    - Verify headers as first row, correct row count, RFC 4180 escaping
    - **Validates: Requirements 5.3**

  - [ ]* 4.5 Write property test: Latency badge formatting (Property 9)
    - **Property 9: Latency badge formatting**
    - Use `fc.nat()` to generate non-negative integers
    - Verify output matches `↯ {N}ms` exactly
    - **Validates: Requirements 7.6**

  - [ ]* 4.6 Write property test: Timestamp display formatting (Property 11)
    - **Property 11: Timestamp display formatting**
    - Use `fc.date()` with varying offsets from "now"
    - Verify relative format for <24h, "YYYY-MM-DD HH:mm" for ≥24h
    - **Validates: Requirements 8.2**

- [-] 5. Application layout shell
  - [x] 5.1 Implement App shell with collapsible sidebar, chat thread, and panel layout
    - Create `frontend/src/App.tsx` with flex layout: Sidebar (260px/48px), MainContent (fluid), TraceabilityPanel (360px, hidden by default)
    - Connect sidebar collapse state to zustand store
    - Connect traceability panel visibility to zustand store
    - MainContent contains ChatThread + FooterBar + ChatInput stacked vertically
    - No horizontal overflow on viewports 1024px–2560px
    - _Requirements: 1.1, 1.3, 1.4, 1.7_

  - [x] 5.2 Implement Collapsible Sidebar component
    - Create `frontend/src/components/Sidebar.tsx`
    - Expanded state (260px): collapse toggle, "New Chat" button, scrollable chat history list (up to 50 entries, most recent first), "Saved Prompts" section with saved sessions, "Schedulability" disabled placeholder
    - Collapsed state (48px icon rail): icons for New Chat, History, Saved Prompts, Schedulability
    - Animate between collapsed/expanded states
    - Dark sidebar background (`bg-sidebar` token)
    - _Requirements: 1.2, 1.3, 1.4, 12.1, 12.2, 12.3, 12.4_

  - [ ] 5.3 Implement Saved Prompts list in Sidebar
    - Display up to 50 saved prompts with name + formatted timestamp (relative <24h, absolute otherwise)
    - Implement delete with confirmation prompt
    - Implement selection to load saved prompt (with unsaved-changes warning)
    - _Requirements: 8.2, 8.3, 8.5_

  - [ ] 5.4 Implement Footer Bar component
    - Create `frontend/src/components/FooterBar.tsx`
    - Persistent clickable bar below ChatThread, above ChatInput
    - Displays "Traceability & Explainability" label
    - Clicking toggles the TraceabilityPanel visibility via store
    - _Requirements: 1.6, 3.1, 3.3_

- [ ] 6. Chat interface components
  - [ ] 6.1 Implement ChatThread component
    - Create `frontend/src/components/ChatThread.tsx`
    - Vertical scrolling container displaying messages in chronological order
    - User messages as right-aligned bubbles (blue background, white text)
    - System responses as left-aligned blocks containing Visualization Cards inline
    - Error messages as left-aligned with error styling and optional retry button
    - Auto-scroll to newest message on new response
    - Empty state when no messages: centered prompt to submit a query
    - Streaming/typing indicator as left-aligned placeholder while loading
    - _Requirements: 1.5, 1.8, 2.6, 2.7, 2.8, 9.3, 9.4, 9.5_

  - [ ] 6.2 Implement ChatInput component
    - Create `frontend/src/components/ChatInput.tsx` fixed at bottom of viewport
    - Text input with 500-char max, submit button, voice-input icon
    - Prevent submission on empty/whitespace-only input
    - Disable input and submit button while request is in flight
    - On submit: append user message bubble, dispatch to store `submitQuery`
    - Implement Web Speech API for voice transcription (hide icon if unsupported)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ]* 6.3 Write property test: Pinned cards survive new query additions (Property 5)
    - **Property 5: Pinned cards survive new query additions**
    - Generate random chat thread states with pinned cards + new query sequences
    - Verify all pinned cards remain present with original data after additions
    - **Validates: Requirements 5.5**

  - [ ]* 6.4 Write property test: Chat thread chronological ordering (Property 13)
    - **Property 13: Chat thread chronological ordering**
    - Generate random sequences of submitted queries
    - Verify messages maintain strict chronological order, each user message followed by its system response
    - **Validates: Requirements 10.3**

- [ ] 7. Visualization cards and chart rendering
  - [ ] 7.1 Implement ChartRenderer component
    - Create `frontend/src/components/ChartRenderer.tsx` using Recharts
    - Render BarChart, LineChart, ScatterChart, PieChart based on `selectChartType` result
    - Implement HeatmapChart (custom grid with Recharts)
    - Implement DataTable for table type
    - Include hover tooltips displaying data point values
    - Handle text-only `output_type` with formatted text block
    - Handle invalid/missing `chart_data` with error state card
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ] 7.2 Implement VisualizationCard component
    - Create `frontend/src/components/VisualizationCard.tsx`
    - Compose: CardToolbar + ChartRenderer
    - Card renders inline in chat thread at 50% or 100% width
    - Handle click/focus to set active card in store (for Stats Panel + Traceability Panel)
    - Visual pinned-state indicator when card is pinned
    - Professional styling with design tokens (subtle shadow, fine border)
    - _Requirements: 2.6, 4.1, 5.5, 11.3_

  - [ ] 7.3 Implement CardToolbar component
    - Create `frontend/src/components/CardToolbar.tsx`
    - Buttons: Download PNG, Download CSV, Pin/Unpin toggle, Expand fullscreen, Save Prompt, Drag handle
    - Connect PNG/CSV exports to utility functions with inline error toast on failure
    - Toggle pin state via store action
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7_

  - [ ] 7.4 Implement FullscreenModal component
    - Create `frontend/src/components/FullscreenModal.tsx`
    - Expand card to viewport as modal overlay with close button
    - Close on button click or Escape key
    - _Requirements: 5.4_

  - [ ] 7.5 Implement drag-to-reorder and resize within chat thread
    - Set up react-dnd DndProvider with HTML5Backend
    - Enable drag-to-reorder cards via drag handle within the chat thread
    - Visual drop indicator showing valid placement positions
    - Reflow cards within 300ms of drop
    - Resize handles (bottom-right, bottom-left) toggling between 50% and 100% width
    - Re-render chart within 200ms of resize
    - Constrain resize to available width (max 100%)
    - Reject drops on positions occupied by pinned cards
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 7.6 Write property test: Drop rejected on pinned card positions (Property 6)
    - **Property 6: Drop rejected on pinned card positions**
    - Generate random chat thread states with pinned cards + drag-drop operations
    - Verify drops targeting pinned card positions are rejected
    - **Validates: Requirements 6.7**

  - [ ]* 7.7 Write property test: Resize constrained to available width (Property 7)
    - **Property 7: Resize constrained to available width**
    - Generate random card widths + resize actions
    - Verify resulting width is always '50%' or '100%', never exceeds container
    - **Validates: Requirements 6.6**

- [ ] 8. Checkpoint - UI components complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Traceability Panel and Stats Panel
  - [ ] 9.1 Implement Traceability Panel component
    - Create `frontend/src/components/TraceabilityPanel.tsx` as a right sidebar (360px)
    - Three sections: paraphrased query rewrite, structured intent JSON (formatted), API call summary
    - Update content when active card changes
    - Empty state when no card selected: "Select a visualization to view traceability"
    - Placeholder message per section if data unavailable
    - Slide in from right edge, push or overlay layout
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 9.2 Implement Stats Panel component
    - Create `frontend/src/components/StatsPanel.tsx` as a collapsible right rail
    - Display per-column stats from active card's `metadata.columns`
    - Render row_count + null_percentage (1 decimal) for all columns
    - Render min/max/mean/median/std_dev (2 decimals) for numeric columns
    - Render cardinality for categorical columns
    - Render time_range_start/end (ISO 8601) for time-series columns
    - Display latency badge (`↯ {N}ms`)
    - Empty state when no card active or no columns available
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ]* 9.3 Write property test: Column statistics rendered by type (Property 8)
    - **Property 8: Column statistics rendered by type**
    - Generate random `ColumnMeta[]` arrays with mixed types
    - Verify correct stat fields rendered per column type
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5**

- [ ] 10. Saved Prompts and error handling
  - [ ] 10.1 Implement Saved Prompt save/load/delete logic
    - Wire "Save session" flow in store: prompt for name (100 char max), serialize full state (chat thread, cards, pins, data, stats) to `SavedPrompt`
    - Persist saved prompts to localStorage (`cbi-saved-prompts` key, max 50)
    - Implement `loadSavedPrompt` with unsaved-changes confirmation, restore without API calls
    - Implement `deleteSavedPrompt` with confirmation prompt
    - Handle localStorage quota exceeded with user-facing error message
    - _Requirements: 8.1, 8.3, 8.4, 8.5, 8.6_

  - [ ] 10.2 Implement error message rendering and retry in chat thread
    - Create `frontend/src/components/ErrorMessage.tsx`
    - Display 422 errors with `error_message` from response as left-aligned in chat thread; preserve prompt in input
    - Display 503/504 errors with service unavailability message and retry button
    - Display timeout errors with message and retry button
    - Retry button re-sends identical `POST /query` request with same `query_text`
    - _Requirements: 9.3, 9.4, 9.5_

  - [ ]* 10.3 Write property test: Saved prompt serialization round-trip (Property 10)
    - **Property 10: Saved prompt serialization round-trip**
    - Generate random session states (chat threads, card configs with pins, widths, data arrays)
    - Verify serialize then deserialize produces equivalent state
    - **Validates: Requirements 8.1**

- [ ] 11. Integration wiring and final assembly
  - [ ] 11.1 Wire all components together in App
    - Connect ChatInput submit → store.submitQuery → API → append system response with card to ChatThread
    - Connect Footer Bar → toggle TraceabilityPanel
    - Connect card click/focus → activeCardId → StatsPanel + TraceabilityPanel update
    - Connect Sidebar: thread selection, saved prompt load, new chat
    - Connect session restore from localStorage on app load
    - Verify streaming indicator shows during API calls and dismisses within 100ms of response
    - Apply Design System tokens consistently across all components
    - _Requirements: 2.2, 2.6, 2.7, 2.8, 3.1, 3.4, 7.1, 9.2, 10.6, 11.5_

  - [ ]* 11.2 Write integration tests with MSW
    - Set up MSW handlers for POST /query (200, 422, 503, timeout)
    - Test full flow: submit query → loading indicator → card rendered in chat thread
    - Test error flows: 422 error in thread, 503 retry, timeout retry
    - Test saved prompt save/load/delete cycle
    - Test sidebar collapse/expand
    - Test footer bar → traceability panel toggle
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 12. Final checkpoint - All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using fast-check (min 100 iterations)
- Unit tests validate specific examples and edge cases
- All code uses TypeScript with React 18 + Vite in the `frontend/` directory
- The backend API at port 8001 remains unchanged; CORS is pre-configured
- Layout is a conversational chat thread (NOT a grid canvas) — cards are inline in the thread
- Sidebar collapses from 260px to a 48px icon rail
- "Bookmarks" are now "Saved Prompts" throughout
- Traceability Panel is a right sidebar toggled via Footer Bar (not per-card drawers)
- Card sizing is 50% or 100% width within the chat thread (no grid cells)
