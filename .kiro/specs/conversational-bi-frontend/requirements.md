# Requirements Document

## Introduction

This document specifies the requirements for a Conversational BI Frontend that replaces the existing single-page HTML frontend (`frontend/index.html`). The new frontend is a React-based application with a professional, refined BI aesthetic inspired by tools like ThoughtSpot, Polymer Search, and Sigma Computing. It features a ChatGPT/Claude-style conversational chat interface connected to the existing NLP Translator backend (`POST /query`), a collapsible sidebar with chat history and saved prompts, interactive visualization cards on a grid canvas, per-card statistical summaries, and a traceability panel for query transparency. The backend services remain unchanged.

## Glossary

- **Frontend_App**: The React + Tailwind single-page application that serves as the conversational BI user interface
- **Chat_Thread**: The main content area displaying a conversational thread of user messages and system responses in a vertical scrolling layout similar to ChatGPT or Claude
- **Chat_Input**: The fixed bottom input area containing the prompt text field, submit button, and voice-input icon
- **Sidebar**: The collapsible left navigation panel showing chat history threads and saved prompts, with a toggle to expand/collapse
- **Canvas**: The area below each system response in the chat thread where visualization cards are displayed inline within the conversation flow
- **Visualization_Card**: A single panel containing an interactive chart or table rendered from backend data, displayed inline within the Chat_Thread
- **Card_Toolbar**: The toolbar attached to each Visualization_Card with actions: Download PNG/CSV, Pin to canvas, Expand fullscreen, Save Prompt, Drag handle
- **Traceability_Panel**: The right sidebar panel displaying query interpretation details, structured intent, and API call summaries for the active visualization, toggled via the Footer_Bar
- **Footer_Bar**: A persistent clickable bar at the bottom of the viewport (above the Chat_Input) that toggles visibility of the Traceability_Panel
- **Session_Store**: The zustand-managed state holding the current chat thread, canvas layout, and all card configurations
- **Saved_Prompt**: A serialized snapshot of a full session including chat thread, prompts, chart configurations, data, and stats (formerly "Bookmark")
- **Backend_API**: The existing NLP Translator service at port 8001 exposing `POST /query` and `GET /sessions/:id`
- **Meta_Payload**: The `meta` field in the backend response containing `latency_ms`, `row_count`, and `columns` array with per-column stats
- **Chart_Selector**: The logic that selects the appropriate chart type (bar, line, scatter, pie, table, heatmap) based on explicit user request, backend specification, or data shape inference
- **Design_System**: The cohesive set of muted colors, clean typography, subtle shadows, and professional palette tokens applied across the entire Frontend_App
- **Stats_Panel**: The collapsible right rail displaying per-column statistical metadata for the active Visualization_Card
- **Schedulability_Section**: A placeholder section in the Sidebar for future scheduling capabilities (disabled state)

## Requirements

### Requirement 1: Application Layout Shell

**User Story:** As a BI analyst, I want a structured layout with a collapsible sidebar, conversational chat thread, and contextual panels, so that I can navigate sessions, converse with the system, and inspect data simultaneously.

#### Acceptance Criteria

1. THE Frontend_App SHALL render a collapsible Sidebar on the left (260px when expanded, 48px icon rail when collapsed), a Chat_Thread in the center (fluid width filling remaining space), and a Traceability_Panel on the right (fixed width of 360px when visible, hidden by default)
2. THE Sidebar SHALL contain a collapse/expand toggle button, a "New Chat" button, a scrollable list of up to 50 chat history entries (most recent first), a "Saved Prompts" section listing saved sessions, and a disabled "Schedulability" section placeholder
3. WHEN the user clicks the Sidebar collapse toggle, THE Sidebar SHALL animate to a 48px-wide icon rail showing only icons for New Chat, History, Saved Prompts, and Schedulability, and the Chat_Thread SHALL expand to fill the reclaimed horizontal space
4. WHEN the user clicks the Sidebar expand toggle from the collapsed icon rail, THE Sidebar SHALL animate to its full 260px width with labels and list content visible
5. THE Chat_Thread SHALL use a vertical scrolling layout displaying user messages (right-aligned bubbles) and system responses (left-aligned) in chronological order, matching the conversational pattern of ChatGPT or Claude
6. THE Frontend_App SHALL render a Footer_Bar as a persistent clickable element below the Chat_Thread and above the Chat_Input, displaying a "Traceability & Explainability" label
7. THE Frontend_App SHALL render all layout regions without horizontal overflow, content truncation, or panel overlap on viewport widths from 1024px to 2560px
8. WHEN the Chat_Thread contains zero system responses, THE Chat_Thread SHALL display a centered empty-state message prompting the user to submit a query via the Chat_Input

### Requirement 2: Chat Interface and Prompt Submission

**User Story:** As a BI analyst, I want a ChatGPT-style conversational interface where I can type or speak queries and see responses in a natural thread format, so that I can interact with my data conversationally.

#### Acceptance Criteria

1. THE Chat_Input SHALL be fixed at the bottom of the viewport and SHALL contain a text input field with a maximum length of 500 characters, a submit button, and a voice-input icon
2. WHEN the user submits a prompt via the submit button or the Enter key, THE Frontend_App SHALL append the user message as a right-aligned bubble in the Chat_Thread, send a POST request to the Backend_API `/query` endpoint with `{ query_text: <prompt> }`, and SHALL disable the text input field and submit button until a response is received or the request times out
3. IF the text input field is empty or contains only whitespace when the user attempts to submit, THEN THE Frontend_App SHALL prevent submission and SHALL not send a request to the Backend_API
4. WHEN the user activates the voice-input icon, THE Frontend_App SHALL use the Web Speech API to transcribe speech into the text input field
5. IF the browser does not support the Web Speech API, THEN THE Frontend_App SHALL hide the voice-input icon
6. WHEN the Backend_API returns a successful response, THE Frontend_App SHALL append a left-aligned system response containing the Visualization_Card inline within the Chat_Thread, positioned below the corresponding user message
7. WHILE the Backend_API is processing a request, THE Frontend_App SHALL display a streaming response indicator (animated skeleton or typing indicator) as a left-aligned system response placeholder in the Chat_Thread
8. WHEN the Backend_API returns a response, THE Frontend_App SHALL dismiss the streaming indicator and render the system response with Visualization_Card within 100ms of response receipt

### Requirement 3: Traceability and Explainability Panel

**User Story:** As a BI analyst, I want to see how my natural language query was interpreted in a dedicated panel, so that I can verify the system understood my intent correctly without cluttering the conversation.

#### Acceptance Criteria

1. WHEN the user clicks the Footer_Bar, THE Frontend_App SHALL toggle visibility of the Traceability_Panel as a right sidebar overlay or push panel (360px wide), sliding in from the right edge of the viewport
2. WHILE the Traceability_Panel is visible and a Visualization_Card is active (clicked or focused), THE Traceability_Panel SHALL display three labeled sections: the paraphrased query rewrite (natural language summary of how the system interpreted the query), the structured intent JSON (query_id, query_type, entity_refs, routing_metadata, and timestamp fields), and the API call summary (target agent identifiers, data sources queried, and response status for each dispatched agent)
3. WHEN the user clicks the Footer_Bar while the Traceability_Panel is visible, THE Frontend_App SHALL hide the Traceability_Panel and the Chat_Thread SHALL expand to fill the reclaimed space
4. WHEN the user selects a different Visualization_Card while the Traceability_Panel is open, THE Traceability_Panel SHALL update its content to reflect the newly selected card's transparency data
5. IF transparency data is unavailable or incomplete for a section, THEN THE Traceability_Panel SHALL display that section with a placeholder message indicating the data could not be retrieved, rather than omitting the section
6. WHEN no Visualization_Card is active while the Traceability_Panel is visible, THE Traceability_Panel SHALL display an empty state indicating the user should select a visualization to view traceability information

### Requirement 4: Visualization Card Rendering

**User Story:** As a BI analyst, I want charts that respect my explicit requests and intelligently default based on data shape, so that I get the visualization I ask for or the best automatic choice.

#### Acceptance Criteria

1. WHEN the user prompt contains an explicit chart type request (e.g., "show me a scatter plot of X vs Y", "create a bar chart of...", "display a pie chart..."), THE Chart_Selector SHALL honor the user-specified chart type and render the requested visualization regardless of data shape inference rules
2. WHEN the Backend_API returns data with a `chart_type` field in `rendered_output` and the user did not explicitly request a chart type, THE Chart_Selector SHALL render the corresponding chart type using Recharts
3. WHEN the Backend_API returns data without a `chart_type` field and the user did not explicitly request a chart type, THE Chart_Selector SHALL infer the chart type from the data shape: time-series data produces a line chart, categorical with numeric produces a bar chart, two numeric columns produce a scatter plot, proportional categories (8 or fewer) produce a pie chart, high-dimensional data produces a heatmap, and all other shapes produce a table
4. THE Visualization_Card SHALL support the following chart types: bar, line, scatter, pie, table, and heatmap
5. THE Visualization_Card SHALL render charts as interactive elements with hover tooltips displaying data point values
6. WHEN the backend returns `output_type: "text"` with no chart data, THE Visualization_Card SHALL render the `text_content` field as a formatted text block with the statistical description

### Requirement 5: Card Toolbar Actions

**User Story:** As a BI analyst, I want quick actions on each visualization card, so that I can export, organize, and save individual results.

#### Acceptance Criteria

1. THE Card_Toolbar SHALL be visible on each Visualization_Card and SHALL contain buttons for: Download PNG, Download CSV, Pin to canvas, Expand fullscreen, Save Prompt, and Drag handle
2. WHEN the user clicks "Download PNG", THE Frontend_App SHALL export the current chart as a PNG image file matching the rendered dimensions of the Visualization_Card
3. WHEN the user clicks "Download CSV", THE Frontend_App SHALL export the underlying data array as a CSV file encoded in UTF-8, with column headers as the first row
4. WHEN the user clicks "Expand fullscreen", THE Visualization_Card SHALL expand to fill the viewport as a modal overlay with a visible close button, and WHEN the user clicks the close button or presses the Escape key, THE Visualization_Card SHALL return to its original position and size
5. WHEN the user clicks "Pin to canvas", THE Visualization_Card SHALL persist in the Chat_Thread across new query submissions, THE Card_Toolbar SHALL display a visual pinned-state indicator on the card, and WHEN the user clicks the pin button again on a pinned card, THE Visualization_Card SHALL become unpinned and eligible for replacement
6. WHEN the user clicks "Save Prompt" on a card, THE Frontend_App SHALL add the card configuration and data to the current session Saved_Prompt
7. IF the PNG or CSV export fails, THEN THE Frontend_App SHALL display an inline error message on the Visualization_Card indicating the export could not be completed

### Requirement 6: Drag-to-Reorder and Resize

**User Story:** As a BI analyst, I want to rearrange and resize visualization cards, so that I can organize my workspace according to my analysis priorities.

#### Acceptance Criteria

1. THE Frontend_App SHALL enable drag-to-reorder of Visualization_Cards within the Chat_Thread using react-dnd
2. WHEN the user drags a card via its Drag handle, THE Chat_Thread SHALL display a visual drop indicator highlighting valid placement positions where the card can be dropped
3. WHEN the user drops a card in a new position, THE Chat_Thread SHALL reflow cards to accommodate the new layout within 300ms of the drop event
4. THE Visualization_Card SHALL have resize handles on its bottom-right corner and bottom-left corner allowing the user to adjust the card width (50% or 100% of the chat thread width) and height
5. WHEN the user resizes a card, THE chart within SHALL re-render to fit the new dimensions within 200ms, preserving all data points, axis labels, and legend visibility
6. IF the user attempts to resize a Visualization_Card beyond the available width, THEN THE Frontend_App SHALL constrain the resize to the maximum available space
7. IF the user drops a card on a position occupied by a pinned card, THEN THE Chat_Thread SHALL reject the drop and return the dragged card to its original position

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

### Requirement 8: Saved Prompts

**User Story:** As a BI analyst, I want to save and restore complete analysis sessions as saved prompts, so that I can return to previous work without re-running queries.

#### Acceptance Criteria

1. WHEN the user clicks "Save session", THE Frontend_App SHALL prompt the user to enter a session name (maximum 100 characters), and SHALL serialize the current chat thread, all prompts, rendered chart configurations, underlying data arrays, and stats into a Saved_Prompt stored with that name and the current date-time
2. THE Sidebar SHALL list all Saved_Prompts (up to 50) under a "Saved Prompts" section, displaying the user-provided session name and a timestamp formatted as relative time (e.g., "2 hours ago") for entries less than 24 hours old, or as "YYYY-MM-DD HH:mm" for older entries, ordered by most recently saved first
3. WHEN the user selects a Saved_Prompt from the Sidebar, THE Frontend_App SHALL prompt the user to confirm if the current session has unsaved changes, and upon confirmation SHALL replace the current Session_Store state with the saved Saved_Prompt state, restoring all Visualization_Cards to their saved positions without making new Backend_API requests
4. THE Frontend_App SHALL persist Saved_Prompts to browser localStorage so they survive page refreshes
5. WHEN the user clicks delete on a Saved_Prompt, THE Frontend_App SHALL display a confirmation prompt, and upon confirmation SHALL remove the Saved_Prompt from localStorage and from the Sidebar listing
6. IF the browser localStorage quota is exceeded when saving a Saved_Prompt, THEN THE Frontend_App SHALL display an error message indicating insufficient storage and suggest deleting older Saved_Prompts to free space, without losing the current session state

### Requirement 9: Backend API Integration

**User Story:** As a BI analyst, I want the frontend to correctly integrate with the existing backend contract, so that queries work without backend modifications.

#### Acceptance Criteria

1. THE Frontend_App SHALL send query requests as `POST /query` with body `{ "query_text": "<user prompt>" }` matching the existing Backend_API contract, where the `query_text` field is a non-empty string with a maximum length of 2000 characters
2. WHEN the Backend_API returns a successful HTTP 200 response, THE Frontend_App SHALL extract chart data from the `rendered_output.chart_data` field and statistics from the `rendered_output.metadata` field within 100ms of receiving the response
3. IF the Backend_API returns an HTTP 422 status, THEN THE Frontend_App SHALL display the value of the `error_message` field from the response body as a left-aligned error message in the Chat_Thread, without clearing the user's original prompt from the Chat_Input
4. IF the Backend_API returns an HTTP 503 or 504 status, THEN THE Frontend_App SHALL display a service unavailability message as a left-aligned error message in the Chat_Thread and render a retry button that, when activated, re-sends the identical `POST /query` request with the same `query_text` payload
5. IF the Backend_API does not respond within 60 seconds, THEN THE Frontend_App SHALL abort the request, display a timeout message as a left-aligned error in the Chat_Thread, and offer a retry button
6. THE Frontend_App SHALL read query latency from the `meta.latency_ms` field in the Meta_Payload when present in the response, or compute it as the elapsed milliseconds between request dispatch and response receipt as a fallback, and store the resulting value in Session_Store for display in the Stats_Panel
7. WHEN the Frontend_App loads a saved prompt that references a server-persisted session identifier, THE Frontend_App SHALL send a `GET /sessions/:id` request to the Backend_API and, if a successful response is received, restore the session state from the response payload

### Requirement 10: State Management

**User Story:** As a BI analyst, I want the application state to be predictable and consistent, so that my chat history, visualizations, and saved prompts remain stable during my session.

#### Acceptance Criteria

1. THE Session_Store SHALL use zustand to manage chat thread state, active card selection, saved prompt data, and sidebar collapse state
2. THE Session_Store SHALL maintain an ordered list of ChatMessages containing user prompts and system responses with associated Visualization_Cards, their pin states, chart configurations, and underlying data arrays
3. WHEN a new query response arrives, THE Session_Store SHALL append the system response with its Visualization_Card to the end of the Chat_Thread in chronological order
4. THE Session_Store SHALL persist the current session to localStorage within 1 second of a state change to enable recovery after page refresh
5. IF a localStorage write fails due to quota or unavailability, THEN THE Session_Store SHALL display a non-blocking warning indicating that session persistence is unavailable without losing the in-memory state
6. WHEN the Frontend_App loads and localStorage contains a previously persisted session, THE Session_Store SHALL restore the chat thread, saved prompts, and sidebar state from the persisted state without making new Backend_API requests

### Requirement 11: Professional Design System

**User Story:** As a BI analyst, I want the application to have a refined, professional look that conveys trust and competence, so that I feel confident using it for business-critical analysis.

#### Acceptance Criteria

1. THE Design_System SHALL define a muted, professional color palette consisting of: a neutral background (slate/gray tones), subtle accent colors for interactive elements (muted blues or teals), and high-contrast text colors for readability
2. THE Design_System SHALL use clean sans-serif typography with a clear hierarchy: headings at 600-700 weight, body text at 400 weight, and monospace for code/data values
3. THE Design_System SHALL apply subtle box shadows (no harsh drop shadows) and fine borders (1px solid with low-opacity neutrals) to cards and panels to create depth without visual noise
4. THE Design_System SHALL avoid glossy gradients, saturated neon colors, and decorative effects that convey an unrefined appearance
5. THE Frontend_App SHALL apply the Design_System tokens consistently across all components including the Sidebar, Chat_Thread, Visualization_Cards, Traceability_Panel, Footer_Bar, and Chat_Input
6. THE Frontend_App SHALL use Tailwind CSS utility classes mapped to the Design_System tokens for consistent theming

### Requirement 12: Schedulability Placeholder

**User Story:** As a BI analyst, I want to see that scheduling capabilities are planned for the future, so that I know the tool will support automated report scheduling.

#### Acceptance Criteria

1. THE Sidebar SHALL display a "Schedulability" section below the "Saved Prompts" section with a calendar/clock icon and the label "Scheduled Reports"
2. THE Schedulability_Section SHALL render in a visually disabled state (reduced opacity, non-interactive) indicating it is not yet available
3. WHEN the user hovers over or clicks the Schedulability_Section, THE Frontend_App SHALL display a tooltip or inline message stating "Coming soon — schedule recurring queries and reports"
4. THE Schedulability_Section SHALL not trigger any navigation, API calls, or state changes when interacted with

