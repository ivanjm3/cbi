# Implementation Plan: Conversational BI Frontend

## Overview

This plan implements a React 18 + Vite + Tailwind CSS conversational BI frontend that connects to the existing NLP Translator backend. The implementation proceeds from project scaffolding and core interfaces, through state management and API integration, to UI components and testing. Each task builds incrementally on previous work, ensuring no orphaned code.

## Tasks

- [x] 1. Project scaffolding and core interfaces
  - [x] 1.1 Initialize Vite + React + TypeScript project in `frontend/`
    - Run `npm create vite@latest` with React-TS template in `frontend/`
    - Install dependencies: tailwindcss, postcss, autoprefixer, recharts, react-dnd, react-dnd-html5-backend, zustand, fast-check, vitest, @testing-library/react, @testing-library/jest-dom, @testing-library/user-event, jsdom, msw
    - Configure `tailwind.config.ts`, `postcss.config.js`, and `vite.config.ts`
    - Configure Vitest in `vite.config.ts` with jsdom environment
    - Set up `frontend/src/index.css` with Tailwind directives
    - _Requirements: 1.1, 1.6_

  - [x] 1.2 Define TypeScript interfaces and types
    - Create `frontend/src/types/index.ts` with all interfaces: `RenderedOutput`, `MetaPayload`, `ColumnMeta`, `CardState`, `SessionState`, `ChatMessage`, `Bookmark`, `ThreadSummary`
    - Create `frontend/src/types/grid.ts` with grid position constants and type helpers
    - _Requirements: 4.1, 7.1, 9.1, 10.2_

- [ ] 2. State management and API layer
  - [-] 2.1 Implement zustand Session Store with localStorage persistence
    - Create `frontend/src/store/sessionStore.ts` with zustand `create` + `persist` middleware
    - Implement all actions: `submitQuery`, `addCard`, `removeCard`, `moveCard`, `resizeCard`, `pinCard`, `unpinCard`, `setActiveCard`, `toggleStatsPanel`, `saveBookmark`, `loadBookmark`, `deleteBookmark`, `startNewChat`
    - Implement localStorage error handling (quota exceeded warning, corrupted data fallback)
    - Persist session within 1 second of state changes (debounced)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8_

  - [-] 2.2 Implement card placement algorithm (`nextPosition`)
    - Create `frontend/src/utils/gridHelpers.ts` with `nextPosition` function
    - Build occupied cell set accounting for card spans
    - Iterate positions in LTR-TTB order: (0,0), (1,0), (0,1), (1,1), (0,2), (1,2)
    - Return null when all cells occupied
    - Implement `constrainResize` function for grid boundary enforcement
    - _Requirements: 10.3, 6.6_

  - [-] 2.3 Implement API integration layer
    - Create `frontend/src/api/queryApi.ts` with `queryBackend` function
    - Implement 60-second timeout with AbortController
    - Handle HTTP 200, 422, 503/504 responses per contract
    - Compute fallback latency when `meta.latency_ms` absent
    - Implement `fetchSession` for `GET /sessions/:id`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [-] 2.4 Implement chart type selection logic
    - Create `frontend/src/utils/chartSelector.ts` with `selectChartType` function
    - Implement explicit chart_type pass-through
    - Implement inference rules: time-series → line, categorical + numeric → bar, 2 numeric → scatter, categorical ≤8 + 1 numeric → pie, 3+ numeric → heatmap, else → table
    - _Requirements: 4.1, 4.2_

  - [ ]* 2.5 Write property test: Whitespace-only queries never submitted (Property 1)
    - **Property 1: Whitespace-only queries are never submitted**
    - Use `fc.string()` filtered to whitespace-only characters
    - Verify `submitQuery` is prevented and no fetch is dispatched
    - **Validates: Requirements 2.3**

  - [ ]* 2.6 Write property test: Chart type selection correctness (Property 2)
    - **Property 2: Chart type selection correctness**
    - Generate random `RenderedOutput` with varying column compositions
    - Verify explicit `chart_type` pass-through and inference rules
    - **Validates: Requirements 4.1, 4.2**

  - [ ]* 2.7 Write property test: Next available position follows LTR-TTB order (Property 11)
    - **Property 11: Next available position follows LTR-TTB order**
    - Generate random occupied-cell sets
    - Verify `nextPosition` returns first unoccupied cell in correct order or null
    - **Validates: Requirements 10.3**

  - [ ]* 2.8 Write property test: Oldest unpinned card replaced on full canvas (Property 12)
    - **Property 12: Oldest unpinned card replaced on full canvas**
    - Generate random full-canvas states with at least one unpinned card
    - Verify the unpinned card with earliest `createdAt` is replaced, all others unchanged
    - **Validates: Requirements 10.4**

  - [ ]* 2.9 Write property test: Pinned cards survive new query additions (Property 4)
    - **Property 4: Pinned cards survive new query additions**
    - Generate random canvas states with pinned cards + add sequences
    - Verify all pinned cards remain with original positions and data
    - **Validates: Requirements 5.5**

- [~] 3. Checkpoint - Core logic validation
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Utility functions and formatters
  - [~] 4.1 Implement CSV export utility
    - Create `frontend/src/utils/csvExport.ts` with `exportCSV` function
    - Handle RFC 4180 escaping: commas, quotes, newlines in cell values
    - Generate column headers as first row, UTF-8 encoded
    - Trigger download via Blob + object URL
    - _Requirements: 5.3_

  - [~] 4.2 Implement PNG export utility
    - Create `frontend/src/utils/pngExport.ts` with `exportPNG` function
    - Use html2canvas or SVG serialization to capture chart area
    - Trigger download matching rendered card dimensions
    - Handle export failure with error callback
    - _Requirements: 5.2, 5.7_

  - [~] 4.3 Implement timestamp and latency formatters
    - Create `frontend/src/utils/formatters.ts` with `formatTimestamp` and `formatLatency`
    - `formatLatency(n)` → `↯ {N}ms`
    - `formatTimestamp(date)` → relative time if <24h, else "YYYY-MM-DD HH:mm"
    - _Requirements: 7.6, 8.2_

  - [ ]* 4.4 Write property test: CSV export structural correctness (Property 3)
    - **Property 3: CSV export structural correctness**
    - Generate random 2D arrays with special characters (commas, quotes, newlines)
    - Verify headers as first row, correct row count, RFC 4180 escaping
    - **Validates: Requirements 5.3**

  - [ ]* 4.5 Write property test: Latency badge formatting (Property 8)
    - **Property 8: Latency badge formatting**
    - Use `fc.nat()` to generate non-negative integers
    - Verify output matches `↯ {N}ms` exactly
    - **Validates: Requirements 7.6**

  - [ ]* 4.6 Write property test: Timestamp display formatting (Property 10)
    - **Property 10: Timestamp display formatting**
    - Use `fc.date()` with varying offsets from "now"
    - Verify relative format for <24h, "YYYY-MM-DD HH:mm" for ≥24h
    - **Validates: Requirements 8.2**

- [ ] 5. Application shell and layout components
  - [~] 5.1 Implement App shell with three-panel layout
    - Create `frontend/src/App.tsx` with Sidebar (260px fixed), Canvas (fluid), StatsPanel (300px collapsible)
    - Use Tailwind flex layout with no horizontal overflow from 1024px to 2560px
    - Connect Stats Panel collapse to zustand store
    - Canvas expands when Stats Panel collapsed
    - _Requirements: 1.1, 1.5, 1.6, 1.8_

  - [~] 5.2 Implement Sidebar component
    - Create `frontend/src/components/Sidebar.tsx` with NewChatButton, ThreadList, BookmarkList
    - Display up to 50 thread history entries (most recent first)
    - Display bookmarks with formatted timestamps (relative <24h, absolute otherwise)
    - Implement bookmark delete with confirmation prompt
    - _Requirements: 1.2, 8.2, 8.5_

  - [~] 5.3 Implement Chat Bar component
    - Create `frontend/src/components/ChatBar.tsx` fixed at viewport bottom
    - Text input with 500-char max, submit button, voice-input icon
    - Prevent submission on empty/whitespace-only input
    - Disable input and button while request in flight
    - Implement Web Speech API for voice transcription (hide icon if unsupported)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [~] 5.4 Implement Stats Panel component
    - Create `frontend/src/components/StatsPanel.tsx` with collapse toggle
    - Display per-column stats from active card's `metadata.columns`
    - Render row_count, null_percentage for all columns
    - Render min/max/mean/median/std_dev for numeric columns (2 decimal places)
    - Render cardinality for categorical columns
    - Render time_range_start/end (ISO 8601) for time-series columns
    - Display latency badge (`↯ {N}ms`)
    - Show empty state when no card active or no columns available
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ]* 5.5 Write property test: Column statistics rendered by type (Property 7)
    - **Property 7: Column statistics rendered by type**
    - Generate random `ColumnMeta[]` arrays with mixed types
    - Verify correct stat fields are rendered per column type
    - **Validates: Requirements 7.2, 7.3, 7.4, 7.5**

- [ ] 6. Visualization cards and canvas
  - [~] 6.1 Implement ChartRenderer component
    - Create `frontend/src/components/ChartRenderer.tsx` using Recharts
    - Render BarChart, LineChart, ScatterChart, PieChart, HeatmapChart, DataTable based on `selectChartType` result
    - Include hover tooltips displaying data point values
    - Handle text-only output_type with formatted text block
    - Handle invalid chart_data with error state
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [~] 6.2 Implement VisualizationCard component
    - Create `frontend/src/components/VisualizationCard.tsx`
    - Compose: UserMessage, CardToolbar, ChartRenderer, TransparencyDrawer
    - Display user message above chart in conversational format
    - Handle click/focus to set active card in store
    - _Requirements: 2.6, 4.1_

  - [~] 6.3 Implement CardToolbar component
    - Create `frontend/src/components/CardToolbar.tsx`
    - Buttons: Download PNG, Download CSV, Pin/Unpin, Expand fullscreen, Bookmark, Drag handle
    - Connect PNG/CSV exports to utility functions with error handling
    - Toggle pin state via store action with visual indicator
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 5.6, 5.7_

  - [~] 6.4 Implement TransparencyDrawer component
    - Create `frontend/src/components/TransparencyDrawer.tsx`
    - Collapsible "How I got this" drawer, default collapsed
    - Three sections: paraphrased query rewrite, structured intent JSON, API call summary
    - Placeholder messages for missing data sections
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [~] 6.5 Implement FullscreenModal component
    - Create `frontend/src/components/FullscreenModal.tsx`
    - Expand card to viewport as modal overlay
    - Close on button click or Escape key
    - _Requirements: 5.4_

  - [~] 6.6 Implement Canvas grid with drag-and-drop
    - Create `frontend/src/components/Canvas.tsx` with react-dnd DndProvider
    - CSS Grid 2 columns × 3 rows; single-column when <2 cards
    - Implement drag-to-reorder with visual drop indicators
    - Reject drops on pinned card positions
    - Reflow cards within 300ms of drop
    - Implement resize handles (bottom-right, bottom-left) for 1-2 col/row spans
    - Constrain resize to grid boundaries, prevent overlap
    - Re-render charts within 200ms of resize
    - Show empty-state message when no cards, streaming skeleton during loading
    - _Requirements: 1.3, 1.4, 1.7, 2.7, 2.8, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 6.7 Write property test: Drop rejected on pinned card positions (Property 5)
    - **Property 5: Drop rejected on pinned card positions**
    - Generate random grid states with pinned cards + drop targets
    - Verify drops targeting pinned cells are rejected, dragged card stays in place
    - **Validates: Requirements 6.7**

  - [ ]* 6.8 Write property test: Resize constrained to grid boundaries (Property 6)
    - **Property 6: Resize constrained to grid boundaries**
    - Generate random positions + resize deltas
    - Verify col + colSpan ≤ 2, row + rowSpan ≤ 3, no overlap with occupied cells
    - **Validates: Requirements 6.6**

- [~] 7. Checkpoint - UI components complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Session bookmarking and error handling
  - [~] 8.1 Implement bookmark save/load/delete logic
    - Wire "Save session" flow: prompt for name (100 char max), serialize state to Bookmark
    - Implement `loadBookmark` with unsaved-changes confirmation prompt
    - Implement `deleteBookmark` with confirmation prompt
    - Handle localStorage quota exceeded error on save
    - _Requirements: 8.1, 8.3, 8.4, 8.5, 8.6_

  - [~] 8.2 Implement error card rendering and retry
    - Create `frontend/src/components/ErrorCard.tsx`
    - Display 422 error with `error_message` from response; preserve prompt
    - Display 503/504 with retry button re-sending identical request
    - Display timeout with retry button
    - Integrate error cards into conversational thread in canvas
    - _Requirements: 9.3, 9.4, 9.5_

  - [~] 8.3 Implement canvas-full notification
    - When canvas full and all cards pinned, display inline notification
    - Prompt user to unpin or remove a card
    - _Requirements: 10.5_

  - [ ]* 8.4 Write property test: Bookmark serialization round-trip (Property 9)
    - **Property 9: Bookmark serialization round-trip**
    - Generate random session states (chat threads, card configurations, grid positions, pin states, data)
    - Verify serialize then deserialize produces equivalent state
    - **Validates: Requirements 8.1**

- [ ] 9. Integration wiring and final assembly
  - [~] 9.1 Wire all components together in App
    - Connect ChatBar submit → store.submitQuery → API → addCard → Canvas render
    - Connect Sidebar thread selection and bookmark load
    - Connect card click/focus → activeCardId → StatsPanel update
    - Connect session restore from localStorage on app load
    - Verify streaming indicator shows during API calls and dismisses within 100ms of response
    - _Requirements: 2.2, 2.6, 2.7, 2.8, 7.1, 9.2, 9.7, 10.8_

  - [ ]* 9.2 Write integration tests with MSW
    - Set up MSW handlers for POST /query (200, 422, 503, timeout)
    - Test full flow: submit query → loading state → card rendered
    - Test error flows: 422 error card, 503 retry, timeout retry
    - Test bookmark save/load/delete cycle
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [~] 10. Final checkpoint - All tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using fast-check (min 100 iterations)
- Unit tests validate specific examples and edge cases
- All code uses TypeScript with React 18 + Vite in the `frontend/` directory
- The backend API at port 8001 remains unchanged; CORS is pre-configured

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "2.4"] },
    { "id": 3, "tasks": ["2.5", "2.6", "2.7", "2.8", "2.9", "4.1", "4.2", "4.3"] },
    { "id": 4, "tasks": ["4.4", "4.5", "4.6", "5.1"] },
    { "id": 5, "tasks": ["5.2", "5.3", "5.4"] },
    { "id": 6, "tasks": ["5.5", "6.1", "6.5"] },
    { "id": 7, "tasks": ["6.2", "6.3", "6.4"] },
    { "id": 8, "tasks": ["6.6"] },
    { "id": 9, "tasks": ["6.7", "6.8", "8.1", "8.2", "8.3"] },
    { "id": 10, "tasks": ["8.4", "9.1"] },
    { "id": 11, "tasks": ["9.2"] }
  ]
}
```
