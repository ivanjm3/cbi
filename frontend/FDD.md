# Frontend Design Document (FDD)

## Conversational BI Frontend — Structural Blueprint, Design System & Interactive Behaviors

---

## 1. Project Identity

| Attribute | Value |
|-----------|-------|
| Framework | React 19 (StrictMode) |
| Language | TypeScript 6.x (strict) |
| Build Tool | Vite 8 |
| Styling | Tailwind CSS 4 (JIT, `@tailwindcss/vite` plugin) |
| State Management | Zustand 5 (with `persist` middleware → localStorage) |
| Routing | React Router DOM 7 |
| Charting | Chart.js 4 + react-chartjs-2 5 |
| Drag & Drop | react-dnd 16 + HTML5 Backend |
| Testing | Vitest 4 + Testing Library + fast-check (PBT) + MSW 2 |
| Linting | ESLint 10 + TypeScript-ESLint |
| Package Manager | npm (lockfile v3) |

---

## 2. Directory Structure

```
frontend/
├── index.html                  # Single HTML entry point
├── vite.config.ts              # Vite + React + Tailwind plugin + Vitest config
├── tailwind.config.ts          # Design token definitions
├── tsconfig.json               # TypeScript composite project config
├── package.json                # Dependencies & scripts
├── public/
│   └── favicon.svg
└── src/
    ├── main.tsx                # App bootstrap: Router + DndProvider + Routes
    ├── App.tsx                 # Root shell: Sidebar | Main | TraceabilityPanel
    ├── index.css               # Global styles, @theme tokens, CSS animations
    ├── vite-env.d.ts           # Vite client types
    ├── api/
    │   ├── queryApi.ts         # Backend HTTP layer (query, follow-up, cancel, re-render)
    │   └── scheduledReportsApi.ts  # Scheduled Reports CRUD API
    ├── components/
    │   ├── Sidebar.tsx         # Collapsible left panel (history, saved prompts, reports)
    │   ├── ChatThread.tsx      # Visualization grid + error messages + typing indicator
    │   ├── ChatInput.tsx       # Floating input bar (text + voice + submit/cancel)
    │   ├── FooterBar.tsx       # Traceability toggle pill
    │   ├── TraceabilityPanel.tsx  # Right panel: query rewrite, intent, API summary
    │   ├── VisualizationCard.tsx  # Card shell: toolbar + chart + strand + prompt display
    │   ├── ChartRenderer.tsx   # Chart.js renderer, table, text fallbacks
    │   ├── CardToolbar.tsx     # Export, pin, fullscreen, viz-type, schedule, more
    │   ├── DraggableCard.tsx   # react-dnd drag/drop + resize handles
    │   ├── StrandConversation.tsx # Multi-turn follow-up per card
    │   ├── FullscreenModal.tsx # Fullscreen chart overlay
    │   ├── ErrorMessage.tsx    # Error display with retry
    │   ├── ErrorCard.tsx       # Error boundary card
    │   ├── SaveSessionModal.tsx# Bookmark/save dialog
    │   ├── VisualizationPrompt.tsx # Viz opt-in prompt
    │   ├── CardHistoryDropdown.tsx # Card history selector
    │   ├── RecurrencePatternSelector.tsx # Cron schedule builder
    │   ├── ScheduledReportsListPage.tsx  # Reports list view
    │   └── ScheduledReportDetailPage.tsx # Report create/edit
    ├── store/
    │   └── sessionStore.ts     # Zustand global store (chat, cards, strands, sidebar)
    ├── styles/
    │   ├── card-history-dropdown.css
    │   └── conversation-strand.css
    ├── types/
    │   ├── index.ts            # Core domain types (CardState, ChatMessage, etc.)
    │   └── scheduledReports.ts # Scheduled reports types
    ├── utils/
    │   ├── chartSelector.ts    # Chart type selection heuristics
    │   ├── chartTypeConverter.ts # Available viz types list
    │   ├── csvExport.ts        # RFC 4180 CSV builder + download
    │   ├── formatters.ts       # Latency badge + relative timestamps
    │   └── pngExport.ts        # html2canvas → PNG download
    └── test/
        ├── setup.ts            # Vitest global setup (jsdom, Testing Library matchers)
        └── setup.test.ts       # Setup verification
```

---

## 3. Layout Architecture

### 3.1 Shell Layout (App.tsx)

```
┌─────────────────────────────────────────────────────────────┐
│ ┌──────┐  ┌──────────────────────────────┐  ┌───────────┐  │
│ │      │  │          Main Content         │  │Traceability│  │
│ │ Side │  │  ┌─ StorageErrorBanner ─────┐ │  │   Panel   │  │
│ │ bar  │  │  ├─ ChatTopBar ─────────────┤ │  │  (360px)  │  │
│ │      │  │  │                          │ │  │  hidden   │  │
│ │260px │  │  │      ChatThread          │ │  │  by       │  │
│ │  or  │  │  │   (Visualization Grid)   │ │  │  default  │  │
│ │ 48px │  │  │                          │ │  │           │  │
│ │      │  │  ├─ FooterBar (toggle pill) ─┤ │  │           │  │
│ │      │  │  └─ ChatInput (floating) ───┘ │  │           │  │
│ └──────┘  └──────────────────────────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────────┘
```

- **Full viewport**: `h-screen w-screen overflow-hidden`
- **Sidebar**: 260px expanded / 48px collapsed icon rail, dark background
- **Main**: `flex-1 min-w-0` fluid, contains stacked layers
- **Traceability Panel**: 360px, conditional render, slides in from right

### 3.2 Visualization Grid Layout (ChatThread.tsx)

| Card Count | Layout |
|------------|--------|
| 1 | Full width, single row |
| 2 | Full width, stacked vertically |
| 3 | Row 1: 2 cols, Row 2: 1 col |
| 4 | 2×2 grid |
| 5 | Row 1: 2, Row 2: 2, Row 3: 1 |
| 6 (max) | 3×2 grid |

Cards arranged using `grid-cols-1 md:grid-cols-2` with `gap-4`. Maximum 6 visualizations enforced with modal prompting deletion.

### 3.3 Responsive Behavior

- Viewport range: 1024px–2560px with no horizontal overflow
- Cards: `w-full md:w-1/2` when resized to 50%
- Chat input: `w-[calc(100%-3rem)] max-w-3xl` centered at bottom
- Sidebar: CSS transitions between expanded/collapsed states

---

## 4. Design System

### 4.1 Color Tokens

```css
/* Background Layers */
--color-bg-primary:    #f8f9fa    /* Page background */
--color-bg-secondary:  #ffffff    /* Cards, modals, panels */
--color-bg-sidebar:    #1e293b    /* Sidebar dark background */
--color-bg-input:      #f1f5f9    /* Input fields, table headers */

/* Text Hierarchy */
--color-text-primary:   #1e293b   /* Headings, body text */
--color-text-secondary: #475569   /* Descriptions, labels */
--color-text-muted:     #94a3b8   /* Placeholders, timestamps */
--color-text-inverse:   #f8fafc   /* Text on dark backgrounds */

/* Accent */
--color-accent-primary: #3b82f6   /* Primary buttons, links, focus rings */
--color-accent-hover:   #2563eb   /* Button hover state */
--color-accent-subtle:  #eff6ff   /* Light accent backgrounds */
--color-accent-teal:    #0d9488   /* Secondary accent (scheduled reports) */

/* Borders */
--color-border-default: #e2e8f0   /* Standard borders */
--color-border-subtle:  #f1f5f9   /* Very light separators */

/* Status */
--color-status-error:   #dc2626   /* Errors, destructive actions */
--color-status-success: #059669   /* Success badges */
--color-status-warning: #d97706   /* Warnings, storage alerts */

/* Chat-Specific */
--color-bubble-user:    #3b82f6   /* User message bubble */
--color-bubble-system:  #ffffff   /* System message bubble */
```

### 4.2 Typography

| Token | Value | Usage |
|-------|-------|-------|
| `--font-sans` | Inter, system-ui, -apple-system, sans-serif | All UI text |
| `--font-mono` | JetBrains Mono, Fira Code, monospace | Code, JSON, structured data |
| `--text-xs` | 0.75rem (12px) | Timestamps, badges |
| `--text-sm` | 0.8125rem (13px) | Secondary labels |
| `--text-base` | 0.875rem (14px) | Body text (root font-size) |
| `--text-lg` | 1rem (16px) | Section headings |
| `--text-xl` | 1.25rem (20px) | Page titles |

Root font-size: **14px**. Line-height: 1.5. Font rendering: antialiased.

### 4.3 Shadows

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-card` | `0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.06)` | Cards at rest |
| `--shadow-card-hover` | `0 4px 6px rgba(0,0,0,0.04), 0 2px 4px rgba(0,0,0,0.06)` | Active/hovered cards |
| `--shadow-panel` | `0 2px 8px rgba(0,0,0,0.06)` | Panels, modals |
| `--shadow-sidebar` | `2px 0 8px rgba(0,0,0,0.04)` | Sidebar edge |

### 4.4 Animations

| Name | Duration | Easing | Effect |
|------|----------|--------|--------|
| `fadeIn` | 0.2s | ease-out | opacity 0→1 |
| `slideInRight` | 0.2s | ease-out | translateX(100%)→0 |
| `slideInLeft` | 0.2s | ease-out | translateX(-100%)→0 |
| Sidebar collapse | 0.2s | CSS transition | Width 260px↔48px |
| Card transitions | 0.2s | duration-200 | Shadow, border color |
| Drag opacity | 0.15s | ease | opacity 1→0.4 while dragging |

### 4.5 Component Styling Patterns

- **Cards**: `rounded-lg border border-border-default bg-bg-secondary shadow-card`
- **Active card**: `border-accent-primary shadow-card-hover ring-1 ring-accent-primary/20`
- **Buttons (primary)**: `rounded-md bg-accent-primary px-3 py-2 text-white hover:bg-accent-hover`
- **Buttons (ghost)**: `rounded-lg text-text-muted hover:text-accent-primary hover:bg-accent-subtle`
- **Inputs**: `rounded-lg border border-border-default bg-bg-input px-4 py-2 focus:border-accent-primary focus:ring-1`
- **Modals**: `fixed inset-0 z-50 bg-black/40` overlay + `rounded-lg bg-bg-secondary p-6 shadow-panel`
- **Dropdown menus**: `absolute bg-bg-secondary border border-border-default rounded-lg shadow-card z-20`

---

## 5. State Management Architecture

### 5.1 Store Shape (Zustand + localStorage persist)

```typescript
interface SessionState {
  // Chat
  chatThread: ChatMessage[];         // Ordered message list
  cards: Record<string, CardState>;  // Visualization cards by ID
  activeCardId: string | null;       // Currently focused card

  // Multi-turn
  strands: Record<string, ConversationStrand>;
  activeStrandId: string | null;

  // Sidebar
  chatHistory: ThreadSummary[];      // Up to 50 entries
  savedPrompts: SavedPrompt[];       // Up to 50 saved sessions
  sidebarCollapsed: boolean;

  // Panels
  traceabilityPanelVisible: boolean;
  statsPanelCollapsed: boolean;
  loading: boolean;
  strandLoading: Record<string, boolean>;

  // Error
  storageError: string | null;

  // Transient (not persisted)
  _activeAbortController: AbortController | null;
  _activeCorrelationId: string | null;
}
```

### 5.2 Persistence Strategy

- **Engine**: Custom `PersistStorage` adapter wrapping `localStorage`
- **Key**: `cbi-session` (main state), `cbi-saved-prompts` (separate key)
- **Error handling**: Quota exceeded → non-blocking banner, in-memory continues
- **Corruption recovery**: JSON parse failure → clear key, start fresh
- **Exclusions**: `loading`, `strandLoading`, `_activeAbortController`, `_activeCorrelationId` not persisted

### 5.3 Data Flow

```
User Input → submitQuery() → queryBackend() → POST /query (8001)
     ↓                                              ↓
  loading=true                               RenderedOutput
     ↓                                              ↓
  User ChatMessage appended              CardState created + system msg
     ↓                                              ↓
  chatHistory auto-synced               activeCardId set → panels update
```

---

## 6. Interactive Behaviors

### 6.1 Query Submission
- Text input: 500 char max, Enter to submit, disabled while loading
- Voice input: Web Speech API (browser-conditional), toggle on/off
- Cancel: AbortController + backend `/cancel` endpoint with correlation ID
- Loading state: typing indicator (3 animated dots), cancel button replaces submit

### 6.2 Visualization Cards
- **Pin/Unpin**: Pinned cards cannot be dragged, shown with amber badge
- **Resize**: Toggle 50%/100% width via corner handles (visible on hover)
- **Drag to reorder**: react-dnd, drag handle only, drop indicators (blue=valid, red=invalid)
- **Chart type switching**: Dropdown menu, calls `/api/re-render`, results cached in `renderCache`
- **Export PNG**: html2canvas → Blob → download link
- **Export CSV**: RFC 4180 compliant, handles Chart.js nested data + table format
- **Fullscreen**: Modal overlay with expanded chart rendering

### 6.3 Conversation Strands
- Each card has a follow-up input (StrandConversation)
- First submit creates a strand, subsequent appends
- Detects chart type keywords → routes through viz pipeline
- Detects chart modification keywords → sends contextual query
- Collapsible message history with auto-scroll

### 6.4 Sidebar Interactions
- **New Chat**: Resets chatThread + cards (current auto-saved to history)
- **Chat History**: Click to load, 3-dot menu for rename/delete
- **Saved Prompts**: Full session restore (thread + cards), delete confirmation
- **Unsaved changes warning**: Modal before loading overwrites current session
- **Bulk delete mode**: Checkbox selection + select-all + confirmation modal
- **Scheduled Reports**: Navigation to `/scheduled-reports` routes

### 6.5 Traceability Panel
- Toggle via FooterBar pill button (bottom-right)
- Shows for active card: Query Rewrite, Structured Intent (JSON), API Call Summary
- Empty state when no card selected
- Includes its own ChatInput at bottom

### 6.6 Error Handling
- HTTP errors (422, 503, 504, 408): ErrorMessage component with status-specific styling
- Export errors: Inline toast on card (3s auto-dismiss)
- Storage errors: Top banner (non-blocking, dismissible)
- Network timeout: 120s client-side, synthetic 408

---

## 7. API Integration

### 7.1 Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query` | POST | Main NL query → RenderedOutput |
| `/query/follow-up` | POST | Strand follow-up with chart context |
| `/cancel` | POST | Cancel in-flight query by correlation ID |
| `/api/re-render` | POST | Convert chart type with raw data |
| `/sessions/:id` | GET | Fetch persisted session |
| `/scheduled-reports/*` | CRUD | Scheduled reports management |

### 7.2 Configuration
- Base URL: `VITE_API_BASE` env var (default: `http://localhost:8001` in dev)
- Timeout: 120,000ms
- Correlation ID: `crypto.randomUUID()` in `X-Correlation-ID` header
- User ID: `X-User-ID` header (from localStorage `cbi_user_id`)

---

## 8. Routing

| Path | Component | Description |
|------|-----------|-------------|
| `/` | `App` | Main conversational BI interface |
| `/scheduled-reports` | `ScheduledReportsListPage` | List all scheduled reports |
| `/scheduled-reports/new` | `ScheduledReportDetailPage` | Create new scheduled report |
| `/scheduled-reports/:reportId` | `ScheduledReportDetailPage` | Edit existing report |

All routes wrapped in `BrowserRouter` + `DndProvider` (HTML5Backend).

---

## 9. Key Patterns for Reuse

### 9.1 Component Composition Pattern
```
DraggableCard (drag/drop + resize)
  └── VisualizationCard (selection, focus, state)
       ├── CardToolbar (actions, exports, menus)
       ├── ChartRenderer (Chart.js / table / text)
       ├── VisualizationPrompt (opt-in)
       └── StrandConversation (multi-turn)
```

### 9.2 Design Token Application
- All colors via semantic tokens (never raw hex in components)
- Shadows as token classes (`shadow-card`, `shadow-panel`)
- Typography via `text-{size}` tokens
- Transitions via `transition-colors duration-200`

### 9.3 State Selector Pattern (Zustand)
```typescript
const value = useSessionStore((s) => s.specificField);  // Granular subscriptions
```
Never subscribe to entire store — always use selectors to avoid re-renders.

### 9.4 Error Boundary Strategy
- API errors → discriminated union `QueryResult` (ok: true/false)
- UI errors → inline toasts (auto-dismiss) or modal dialogs
- Storage errors → non-blocking banner
- Missing data → placeholder text ("Data could not be retrieved")

### 9.5 Accessibility Patterns
- `role="toolbar"`, `role="dialog"`, `role="alert"`, `role="article"` semantics
- `aria-label`, `aria-expanded`, `aria-pressed`, `aria-modal` attributes
- `aria-live="polite"` for dynamic content updates
- Keyboard navigation: Enter/Space for activation, Escape for dismiss
- Focus management in modals and dropdowns

---

## 10. Build & Dev Commands

```bash
npm run dev       # Vite dev server (HMR)
npm run build     # tsc -b && vite build → dist/
npm run lint      # ESLint
npm run test      # Vitest (jsdom, watch mode)
npm run preview   # Vite preview of production build
```

---

## 11. Environment Variables

| Variable | Default (dev) | Description |
|----------|---------------|-------------|
| `VITE_API_BASE` | `http://localhost:8001` | Backend API base URL |

Production `.env.production` overrides for deployed environments.

---

## 12. Design Principles Summary

1. **Light theme, professional BI aesthetic** — White cards on light gray, subtle shadows, fine borders
2. **14px base with Inter font** — Optimized for data-dense interfaces
3. **Chat-first interaction model** — NL query → inline visualization cards
4. **Semantic color tokens** — All styling through design system, no raw values
5. **Progressive disclosure** — Traceability panel hidden by default, card details on focus
6. **Non-destructive errors** — Never lose in-memory state on storage failures
7. **Local-first persistence** — localStorage with graceful degradation
8. **Responsive within enterprise viewport range** — 1024px–2560px
9. **Accessibility as default** — ARIA roles, keyboard nav, screen reader support
10. **Composition over inheritance** — Small, focused components composed together
