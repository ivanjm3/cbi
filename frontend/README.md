# Conversational BI Frontend

A React-based conversational business intelligence interface that connects to the Ontology NLP Query System backend.

## Stack

- **React 18** + **TypeScript** — UI components
- **Vite** — Dev server and build tooling
- **Tailwind CSS** — Utility-first styling
- **Recharts** — Interactive charting (bar, line, scatter, pie, heatmap)
- **react-dnd** — Drag-and-drop card reordering
- **zustand** — State management with localStorage persistence
- **html2canvas** — PNG export

## Quick Start

```bash
# Install dependencies
npm install

# Start dev server (http://localhost:5173)
npm run dev

# The backend must be running at http://localhost:8001
# Start it from the project root: python run_all.py
```

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start Vite dev server with hot reload |
| `npm run build` | TypeScript check + production build to `dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run test` | Run unit tests (vitest) |
| `npm run lint` | Run ESLint |

## Architecture

```
src/
├── api/           — Backend API integration (queryApi.ts)
├── components/    — React components
│   ├── Canvas.tsx           — 2×3 grid with drag-and-drop
│   ├── ChatBar.tsx          — Fixed bottom chat input
│   ├── ChartRenderer.tsx    — Recharts-based chart rendering
│   ├── VisualizationCard.tsx — Card composing toolbar + chart + drawer
│   ├── CardToolbar.tsx      — Export, pin, fullscreen, bookmark actions
│   ├── StatsPanel.tsx       — Per-column statistics display
│   ├── Sidebar.tsx          — Thread history + bookmarks
│   ├── TransparencyDrawer.tsx — "How I got this" collapsible section
│   ├── FullscreenModal.tsx  — Viewport-filling card expansion
│   ├── ErrorCard.tsx        — Error display with retry
│   └── CanvasFullNotification.tsx — Canvas-full warning
├── store/         — Zustand session store
├── types/         — TypeScript interfaces
└── utils/         — Helpers (chart selection, grid, CSV/PNG export, formatters)
```

## Backend API Contract

The frontend communicates with the NLP Translator backend:

**Endpoint:** `POST http://localhost:8001/query`

**Request:**
```json
{ "query_text": "show me quarterly sales revenue" }
```

**Success (200):**
```json
{
  "rendered_output": {
    "output_type": "chart",
    "chart_type": "bar",
    "chart_data": { "type": "bar", "data": {...}, "options": {...} },
    "text_content": "stats summary",
    "description": "BI insight text",
    "metadata": {
      "query_id": "uuid",
      "query_type": "lookup",
      "timestamp": "ISO-8601",
      "data_sources": ["financial_data"]
    }
  },
  "latency": {
    "nlp_translation_ms": 4500,
    "orchestrator_ms": 1200,
    "guardrail_ms": 2800,
    "visualization_ms": 25000,
    "total_ms": 33500
  },
  "query_id": "uuid",
  "correlation_id": "uuid"
}
```

**Error (422):**
```json
{ "error_code": "UNPARSEABLE_QUERY", "error_message": "...", "query_id": "uuid" }
```

**Error (503/504):**
```json
{ "error": "SERVICE_UNAVAILABLE", "message": "...", "query_id": "uuid" }
```

## Key Features

- **Auto chart selection** — Picks chart type from data shape (time-series → line, categorical → bar, etc.)
- **Drag-and-drop** — Reorder cards on the 2×3 grid; pinned cards can't be moved
- **Resize** — Corner handles let cards span 1-2 columns and rows
- **Pin cards** — Keep specific visualizations across new queries
- **Export** — Download any card as PNG or CSV
- **Bookmarks** — Save/restore full sessions to localStorage
- **Voice input** — Web Speech API transcription (Chrome/Edge)
- **Error handling** — Inline error cards with retry for 503/504/timeout
- **Session persistence** — State auto-saved to localStorage, restores on refresh
