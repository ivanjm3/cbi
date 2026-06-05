# Requirements Document

## Introduction

This document specifies the requirements for a Conversational BI Frontend that replaces the existing single-page HTML frontend (`frontend/index.html`). The new frontend is a React-based application inspired by ThoughtSpot, Polymer Search, and Sigma Computing. It connects to the existing NLP Translator backend (`POST /query`) and provides a multi-panel visualization canvas, persistent chat history, session bookmarking, and per-card statistical summaries. The backend services remain unchanged.

## Glossary

- **Frontend_App**: The React + Tailwind single-page application that serves as the conversational BI user interface
- **Chat_Bar**: The fixed bottom input area containing the prompt text field, submit button, and voice-input icon
- **Sidebar**: The persistent left navigation panel showing chat thread history, bookmarked sessions, and a new-chat button
- **Canvas**: The main content area using CSS Grid layout (2 columns × 3 rows, max 6 panels) for displaying visualization cards
- **Visualization_Card**: A single panel on the Canvas containing an interactive chart or table rendered from backend data
- **Card_Toolbar**: The toolbar attached to each Visualization_Card with actions: Download PNG/CSV, Pin to canvas, Expand fullscreen, Bookmark, Drag handle
- **Stats_Panel**: The collapsible right rail or card footer displaying per-column statistical metadata for the active Visualization_Card
- **Session_Store**: The zustand-managed state holding the current chat thread, canvas layout, and all card configurations
- **Bookmark**: A serialized snapshot of a full session including chat thread, prompts, chart configurations, data, and stats
- **Backend_API**: The existing NLP Translator service at port 8001 exposing `POST /query` and `GET /sessions/:id`
- **Meta_Payload**: The `meta` field in the backend response containing `latency_ms`, `row_count`, and `columns` array with per-column stats
- **Chart_Selector**: The logic that automatically selects the appropriate chart type (bar, line, scatter, pie, table, heatmap) based on data shape

## Requirements

### Requirement 1: Application Layout Shell

**User Story:** As a BI analyst, I want a structured three-panel layout with sidebar, canvas, and stats panel, so that I can navigate sessions, view visualizations, and inspect data simultaneously.

#### Acceptance Criteria

1. THE Frontend_App SHALL render a persistent Sidebar on the left (fixed width of 260px), a Canvas in the center (fluid width filling remaining space), and a collapsible Stats_Panel on the right (fixed width of 300px when expanded)
2. THE Sidebar SHALL display a "New Chat" button, a scrollable list of up to 50 chat thread history entries (most recent first), and a section for bookmarked sessions
3. THE Canvas SHALL use a CSS Grid layout with 2 columns and 3 rows, supporting a maximum of 6 Visualization_Cards simultaneously
4. WHILE the Canvas contains fewer than 2 Visualization_Cards, THE Canvas SHALL display a single-column layout spanning the full grid width
5. THE Stats_Panel SHALL be collapsible via a toggle button and SHALL remember its collapsed state within the current browser session using the Session_Store
6. THE Frontend_App SHALL render all three panels without horizontal overflow, content truncation, or panel overlap on viewport widths from 1024px to 2560px
7. WHEN the Canvas contains zero Visualization_Cards, THE Canvas SHALL display a centered empty-state message prompting the user to submit a query via the Chat_Bar
8. WHEN the Stats_Panel is collapsed, THE Canvas SHALL expand to fill the space previously occupied by the Stats_Panel

### Requirement 2: Chat Interface and Prompt Submission

**User Story:** As a BI analyst, I want a fixed chat bar at the bottom of the screen where I can type or speak queries, so that I can quickly ask questions about my data.

#### Acceptance Criteria

1. THE Chat_Bar SHALL be fixed at the bottom of the viewport and SHALL contain a text input field with a maximum length of 500 characters, a submit button, and a voice-input icon
2. WHEN the user submits a prompt via the submit button or the Enter key, THE Frontend_App SHALL send a POST request to the Backend_API `/query` endpoint with `{ query_text: <prompt> }` and SHALL disable the text input field and submit button until a response is received or the request times out
3. IF the text input field is empty or contains only whitespace when the user attempts to submit, THEN THE Frontend_App SHALL prevent submission and SHALL not send a request to the Backend_API
4. WHEN the user activates the voice-input icon, THE Frontend_App SHALL use the Web Speech API to transcribe speech into the text input field
5. IF the browser does not support the Web Speech API, THEN THE Frontend_App SHALL hide the voice-input icon
6. THE Frontend_App SHALL render each user message above its resulting Visualization_Card in a conversational thread format
7. WHILE the Backend_API is processing a request, THE Frontend_App SHALL display a streaming response indicator (animated skeleton or pulse animation) in the Canvas area
8. WHEN the Backend_API returns a response, THE Frontend_App SHALL dismiss the streaming indicator and render the Visualization_Card within 100ms of response receipt

### Requirement 3: Query Transparency Drawer

**User Story:** As a BI analyst, I want to see how my natural language query was interpreted, so that I can verify the system understood my intent correctly.

#### Acceptance Criteria

1. WHEN a Visualization_Card is rendered, THE Frontend_App SHALL display a collapsible "How I got this" drawer below the visualization result, defaulting to the collapsed state
2. WHEN the user activates the drawer toggle, THE Frontend_App SHALL expand the drawer to display three labeled sections: the paraphrased query rewrite (natural language summary of how the system interpreted the query), the structured intent JSON (query_id, query_type, entity_refs, routing_metadata, and timestamp fields), and the API call summary (target agent identifiers, data sources queried, and response status for each dispatched agent)
3. WHEN the user activates the drawer toggle while the drawer is expanded, THE Frontend_App SHALL collapse the drawer and hide the transparency content
4. IF transparency data is unavailable or incomplete for a section, THEN THE Frontend_App SHALL display that section with a placeholder message indicating the data could not be retrieved, rather than omitting the section

### Requirement 4: Visualization Card Rendering

**User Story:** As a BI analyst, I want automatically selected interactive charts based on my data, so that I can explore results without manually choosing chart types.

#### Acceptance Criteria

1. WHEN the Backend_API returns data with a `chart_type` field in `rendered_output`, THE Chart_Selector SHALL render the corresponding chart type using Recharts
2. WHEN the Backend_API returns data without a `chart_type` field, THE Chart_Selector SHALL infer the chart type from the data shape: time-series data produces a line chart, categorical with numeric produces a bar chart, two numeric columns produce a scatter plot, proportional categories (8 or fewer) produce a pie chart, high-dimensional data produces a heatmap, and all other shapes produce a table
3. THE Visualization_Card SHALL support the following chart types: bar, line, scatter, pie, table, and heatmap
4. THE Visualization_Card SHALL render charts as interactive elements with hover tooltips displaying data point values
5. WHEN the backend returns `output_type: "text"` with no chart data, THE Visualization_Card SHALL render the `text_content` field as a formatted text block with the statistical description

### Requirement 5: Card Toolbar Actions

**User Story:** As a BI analyst, I want quick actions on each visualization card, so that I can export, organize, and save individual results.

#### Acceptance Criteria

1. THE Card_Toolbar SHALL be visible on each Visualization_Card and SHALL contain buttons for: Download PNG, Download CSV, Pin to canvas, Expand fullscreen, Bookmark, and Drag handle
2. WHEN the user clicks "Download PNG", THE Frontend_App SHALL export the current chart as a PNG image file matching the rendered dimensions of the Visualization_Card
3. WHEN the user clicks "Download CSV", THE Frontend_App SHALL export the underlying data array as a CSV file encoded in UTF-8, with column headers as the first row
4. WHEN the user clicks "Expand fullscreen", THE Visualization_Card SHALL expand to fill the viewport as a modal overlay with a visible close button, and WHEN the user clicks the close button or presses the Escape key, THE Visualization_Card SHALL return to its original Canvas position and size
5. WHEN the user clicks "Pin to canvas", THE Visualization_Card SHALL persist on the Canvas across new query submissions, THE Card_Toolbar SHALL display a visual pinned-state indicator on the card, and WHEN the user clicks the pin button again on a pinned card, THE Visualization_Card SHALL become unpinned and eligible for replacement
6. WHEN the user clicks "Bookmark" on a card, THE Frontend_App SHALL add the card configuration and data to the current session Bookmark
7. IF the PNG or CSV export fails, THEN THE Frontend_App SHALL display an inline error message on the Visualization_Card indicating the export could not be completed

### Requirement 6: Drag-to-Reorder and Resize

**User Story:** As a BI analyst, I want to rearrange and resize visualization cards on my canvas, so that I can organize my workspace according to my analysis priorities.

#### Acceptance Criteria

1. THE Frontend_App SHALL enable drag-to-reorder of Visualization_Cards on the Canvas using react-dnd
2. WHEN the user drags a card via its Drag handle, THE Canvas SHALL display a visual drop indicator highlighting valid placement positions where the card can be dropped
3. WHEN the user drops a card in a new position, THE Canvas SHALL reflow all cards to accommodate the new layout within 300ms of the drop event
4. THE Visualization_Card SHALL have resize handles on its bottom-right corner and bottom-left corner allowing the user to span 1 or 2 columns and 1 or 2 rows within the grid
5. WHEN the user resizes a card, THE chart within SHALL re-render to fit the new dimensions within 200ms, preserving all data points, axis labels, and legend visibility
6. IF the user attempts to resize a Visualization_Card beyond the grid boundaries or into a cell occupied by another card, THEN THE Frontend_App SHALL constrain the resize to the maximum available space and prevent overlap
7. IF the user drops a card on a position that would cause overlap with a pinned card, THEN THE Canvas SHALL reject the drop and return the dragged card to its original position

### Requirement 7: Per-Card Statistics Panel

**User Story:** As a BI analyst, I want to see column-level statistics for each visualization, so that I can quickly assess data quality and distribution without writing additional queries.

#### Acceptance Criteria

1. WHEN the user clicks or keyboard-focuses a Visualization_Card, THE Stats_Panel SHALL display statistics sourced from the Meta_Payload `columns` array for that card, and SHALL clear any previously displayed statistics from another card
2. WHILE a Visualization_Card is active, THE Stats_Panel SHALL display the row count (integer) and null percentage (rounded to one decimal place) for every column in the Meta_Payload `columns` array
3. WHILE a Visualization_Card is active, THE Stats_Panel SHALL display min, max, mean, median, and standard deviation (each rounded to two decimal places) for each column whose type is numeric
4. WHILE a Visualization_Card is active, THE Stats_Panel SHALL display cardinality (unique value count as an integer) for each column whose type is categorical
5. WHILE a Visualization_Card is active, THE Stats_Panel SHALL display the time range (earliest and latest values formatted in ISO 8601) for each column whose type is time-series
6. WHILE a Visualization_Card is active, THE Stats_Panel SHALL display a query latency badge showing the value from `meta.latency_ms` formatted as "↯ {N}ms" where N is the integer millisecond value
7. IF the Meta_Payload `columns` array is empty or absent for the active Visualization_Card, THEN THE Stats_Panel SHALL display an informational message indicating that no column statistics are available
8. WHEN no Visualization_Card is active (none clicked or focused), THE Stats_Panel SHALL display an empty state indicating that no card is selected

### Requirement 8: Session Bookmarking

**User Story:** As a BI analyst, I want to save and restore complete analysis sessions, so that I can return to previous work without re-running queries.

#### Acceptance Criteria

1. WHEN the user clicks "Save session", THE Frontend_App SHALL prompt the user to enter a session name (maximum 100 characters), and SHALL serialize the current chat thread, all prompts, rendered chart configurations, underlying data arrays, and stats into a Bookmark stored with that name and the current date-time
2. THE Sidebar SHALL list all saved Bookmarks (up to 50) under a "Bookmarks" section, displaying the user-provided session name and a timestamp formatted as relative time (e.g., "2 hours ago") for entries less than 24 hours old, or as "YYYY-MM-DD HH:mm" for older entries, ordered by most recently saved first
3. WHEN the user selects a saved Bookmark from the Sidebar, THE Frontend_App SHALL prompt the user to confirm if the current session has unsaved changes, and upon confirmation SHALL replace the current Session_Store state with the saved Bookmark state, restoring all Visualization_Cards to their saved grid positions without making new Backend_API requests
4. THE Frontend_App SHALL persist Bookmarks to browser localStorage so they survive page refreshes
5. WHEN the user clicks delete on a Bookmark, THE Frontend_App SHALL display a confirmation prompt, and upon confirmation SHALL remove the Bookmark from localStorage and from the Sidebar listing
6. IF the browser localStorage quota is exceeded when saving a Bookmark, THEN THE Frontend_App SHALL display an error message indicating insufficient storage and suggest deleting older Bookmarks to free space, without losing the current session state

### Requirement 9: Backend API Integration

**User Story:** As a BI analyst, I want the frontend to correctly integrate with the existing backend contract, so that queries work without backend modifications.

#### Acceptance Criteria

1. THE Frontend_App SHALL send query requests as `POST /query` with body `{ "query_text": "<user prompt>" }` matching the existing Backend_API contract, where the `query_text` field is a non-empty string with a maximum length of 2000 characters
2. WHEN the Backend_API returns a successful HTTP 200 response, THE Frontend_App SHALL extract chart data from the `rendered_output.chart_data` field and statistics from the `rendered_output.metadata` field within 100ms of receiving the response
3. IF the Backend_API returns an HTTP 422 status, THEN THE Frontend_App SHALL display the value of the `error_message` field from the response body in an inline error card appended to the conversational thread, without clearing the user's original prompt from the Chat_Bar
4. IF the Backend_API returns an HTTP 503 or 504 status, THEN THE Frontend_App SHALL display a service unavailability message in an inline error card and render a retry button that, when activated, re-sends the identical `POST /query` request with the same `query_text` payload
5. IF the Backend_API does not respond within 60 seconds, THEN THE Frontend_App SHALL abort the request, display a timeout message in an inline error card, and offer a retry button
6. THE Frontend_App SHALL read query latency from the `meta.latency_ms` field in the Meta_Payload when present in the response, or compute it as the elapsed milliseconds between request dispatch and response receipt as a fallback, and store the resulting value in Session_Store for display in the Stats_Panel
7. WHEN the Frontend_App loads a bookmarked session that references a server-persisted session identifier, THE Frontend_App SHALL send a `GET /sessions/:id` request to the Backend_API and, if a successful response is received, restore the session state from the response payload

### Requirement 10: State Management

**User Story:** As a BI analyst, I want the application state to be predictable and consistent, so that my canvas layout, chat history, and bookmarks remain stable during my session.

#### Acceptance Criteria

1. THE Session_Store SHALL use zustand to manage canvas layout state, chat thread history, active card selection, and bookmark data
2. THE Session_Store SHALL maintain an ordered list of Visualization_Cards with their grid positions (column and row index), sizes (column span and row span), pin states, chart configurations, and underlying data arrays
3. WHEN a new query response arrives, THE Session_Store SHALL append the new Visualization_Card to the next available Canvas position in left-to-right, top-to-bottom order within the 2-column × 3-row grid
4. IF the Canvas is full (6 panels occupied) and at least one Visualization_Card is unpinned, THEN THE Session_Store SHALL replace the oldest unpinned Visualization_Card with the new result
5. IF the Canvas is full (6 panels occupied) and all Visualization_Cards are pinned, THEN THE Session_Store SHALL display an inline notification indicating the canvas is full and the user must unpin or remove a card before new results can be displayed
6. THE Session_Store SHALL persist the current session to localStorage within 1 second of a state change to enable recovery after page refresh
7. IF a localStorage write fails due to quota or unavailability, THEN THE Session_Store SHALL display a non-blocking warning indicating that session persistence is unavailable without losing the in-memory state
8. WHEN the Frontend_App loads and localStorage contains a previously persisted session, THE Session_Store SHALL restore the canvas layout, chat thread history, and bookmark data from the persisted state without making new Backend_API requests
