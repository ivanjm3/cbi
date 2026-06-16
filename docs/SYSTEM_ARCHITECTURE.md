# System Architecture — Ontology NLP Query System

## Overview

This system is an ontology-based, NLP-driven query platform built on a hub-and-spoke microservices architecture. A user submits a natural language question through a React-based conversational BI frontend. The system classifies the query against a domain ontology, routes it to the appropriate data-retrieval agent, applies content guardrails, generates a visualization, and returns the result — all in a single request cycle.

The frontend is a React 18 + Vite + Tailwind CSS single-page application providing a multi-panel visualization canvas with drag-and-drop, session persistence, and interactive charts via Recharts. It connects to the backend at port 8001 via `POST /query`.

AI inference runs on Amazon Bedrock. The default LLM is Claude 3.5 Haiku; embeddings use Amazon Titan Embeddings V2. Persistent storage is entirely S3-backed (no local databases).

---

## High-Level Data Flow

```
┌──────────────┐     POST /query      ┌──────────────────┐
│  React SPA   │ ──────────────────→  │  NLP Translator  │ (port 8001)
│  (Vite:5173) │                      │  + Input Guard   │
└──────────────┘                      └────────┬─────────┘
                                           │
                              StructuredIntent (JSON)
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │ Orchestrator Hub │ (port 8002)
                                  │  (deterministic  │
                                  │   routing)       │
                                  └────────┬─────────┘
                                           │
                              Dispatch to spoke agent(s)
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │   Spoke Agent    │ (port 8010)
                                  │  (deterministic  │
                                  │   data retrieval)│
                                  └────────┬─────────┘
                                           │
                              Raw data payload (JSON)
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │ Guardrail Layer  │ (port 8003)
                                  │  (output filter) │
                                  └────────┬─────────┘
                                           │
                              Validated response
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  Visualization   │ (port 8004)
                                  │  Renderer (LLM)  │
                                  └────────┬─────────┘
                                           │
                              RenderedOutput (chart spec + stats + latency)
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  React SPA       │
                                  │  Recharts render │
                                  └──────────────────┘
```

---

## Services

### 1. NLP Translator (port 8001)

**File:** `src/services/nlp_api.py`, `src/services/nlp_translator.py`

**Role:** Entry point for all user queries. Translates natural language into a machine-readable `StructuredIntent`. Also orchestrates the full downstream pipeline and returns the final result with latency breakdown.

**Pipeline:**
1. **Input guardrail** (Bedrock Guardrails, `source=INPUT`) — runs in parallel with NLP translation. Results are cached per-query to avoid repeat Bedrock calls. If input is blocked, returns 422.
2. **Entity resolution** — extracts keywords from the query, searches the ontology for matching concepts.
3. **Specificity check** — rejects vague queries that only match on weak substring fragments (e.g., "for each quarter"). Requires at least one strong domain keyword match.
4. **Query type classification** — calls Claude Haiku via Bedrock with ontology context. Classifies into: `lookup`, `aggregation`, or `comparison`.
5. **Visualization hint extraction** — detects explicit chart type requests (scatter, line, pie, bar, table) via regex patterns in the query text.
6. **Produces** a `StructuredIntent` containing: `query_id`, `query_type`, `entity_refs`, `routing_metadata` (includes `query_text` and optional `requested_chart_type`), `timestamp`.

**Efficiency features:**
- LRU classification cache (1000 entries) — identical query+entity combos skip the Bedrock call.
- Input guardrail cache — same query text skips the Bedrock guardrail API call.
- Entity resolution and history bias run concurrently (`asyncio.gather`).
- Per-step latency tracking returned in the response.

**Also serves:** The frontend HTML (`GET /`) and orchestrates the full downstream pipeline (Orchestrator → Guardrail → Renderer).

---

### 2. Orchestrator Hub (port 8002)

**File:** `src/services/orchestrator_api.py`, `src/services/orchestrator_hub.py`

**Role:** Central routing engine. Receives a StructuredIntent, resolves which spoke agents can handle it based on entity_ref overlap, dispatches concurrently, and merges results. **No LLM call in the active code path.**

**Pipeline:**
1. **Cache check** — computes a deterministic SHA-256 hash of the intent. If cached → returns immediately (0ms).
2. **Agent resolution** — matches the intent's `entity_refs` against registered agents' `entity_refs`. An agent is selected if there's any set overlap.
3. **Direct dispatch** — sends the StructuredIntent via HTTP POST to all resolved agents concurrently (thread pool). Per-agent timeout: 30s.
4. **Merge** — combines successful `AgentResult` objects into an `OrchestratorResponse`. Tracks unavailable/failed agents.
5. **Cache store** — caches successful responses for future identical intents.

**Agent registration:** Spoke agents register at startup via `POST /admin/agents` with `agent_id`, `endpoint_url`, `data_source`, and `entity_refs`. Runtime registration — no restart needed.

**Latency:** ~1-2s first call (HTTP dispatch + S3 data fetch), 0ms on cache hit.

---

### 3. Spoke Agent (port 8010)

**File:** `src/agents/spoke_agent.py`

**Role:** Deterministic data retrieval agent. Routes queries to the correct data source based on `entity_refs` — **no LLM call**. The NLP Translator already resolved entities and the Orchestrator already matched them to this agent, so the spoke agent simply fetches and processes data.

**Routing logic:**
- Financial entities (`sales_revenue`, `quarterly_report`, `order_volume`, `return_rate`, `region`) → `query_financial_data`
- Product entities (`product_catalog`, `inventory_stock`, `product_pricing`, `supplier_info`, `product_category`) → `query_product_catalog`
- Both → queries both sources and returns merged comparison data

**Data sources:**
- `financial_data.json` (S3) — quarterly revenue, order volume by category/region
- `product_catalog.csv` (S3) — products, categories, prices, stock, suppliers

**Query execution:**
- **Lookup** — returns filtered rows as tabular data (columns + rows).
- **Aggregation** — computes sum, avg, min, max, count for all numeric columns.
- **Comparison** — groups by a categorical column, then aggregates within each group.

**Latency:** ~500ms-1s (S3 GetObject + in-memory processing).

---

### 4. Guardrail Layer (port 8003)

**File:** `src/services/guardrail_api.py`, `src/services/guardrail_layer.py`

**Role:** Validates the merged orchestrator response before visualization. Applies schema validation and Amazon Bedrock Guardrails (ML-based content filtering).

**Pipeline:**
1. **Schema validation** — structural correctness (results exist, payloads present).
2. **Cache check** — SHA-256 of serialized response. If previously validated → instant return.
3. **Bedrock Guardrails** (`apply_guardrail`, `source=OUTPUT`) — checks for hate speech, violence, sexual content, insults, misconduct, PII.

**Outcomes:** `passed` | `rejected` (422) | `error` (500)

**Fail-open policy:** If Bedrock Guardrails are unreachable, content passes through with a logged warning.

**Latency:** ~2-3s first call (Bedrock API), 0ms on cache hit.

---

### 5. Visualization Renderer (port 8004)

**File:** `src/services/visualization_api.py`, `src/services/visualization_renderer.py`

**Role:** The intelligent BI analysis engine. Transforms validated data into context-aware visualizations using LLM reasoning. This is the core intelligence layer — it analyzes data shape, considers the user's original query, and produces the most insightful chart type with statistical annotations.

**Pipeline:**
1. **Payload normalization** — converts aggregation/comparison/tabular/multi-source payloads into uniform `columns + rows` format.
2. **Render cache check** — keyed by hash of (payload + query_type + query_text). If cached → instant return.
3. **Statistics generation** — computes key stats as text description (always available immediately).
4. **Strands Agent rendering** — the LLM agent receives:
   - The user's original query text
   - Data columns, sample rows, query type
   - Any explicit chart type request (e.g., "scatter")
   - Pre-computed statistics
   
   The agent analyzes the data and outputs a JSON chart specification with chart type, Chart.js-compatible data, and BI insights.

5. **Fallback** — if the agent output can't be parsed, rule-based selection:
   - User explicitly requested a type → force that type
   - Time-series data (quarters, months) → line chart
   - Comparison with ≤6 groups, single metric → pie chart
   - Comparison with many groups → bar chart
   - Two numeric columns → scatter plot
   - Single aggregation metric → table
   - Everything else → bar chart

**Output:** `RenderedOutput` with `output_type`, `chart_type`, `chart_data` (Chart.js spec), `text_content` (stats), `description` (insights), `metadata`.

**Latency:** ~20-30s first call (Strands Agent LLM), 0ms on cache hit.

---

### 6. Frontend (React SPA)

**Directory:** `frontend/`

**Role:** Conversational BI React application connecting to the NLP Translator backend at port 8001. Replaces the original single-page HTML testing UI.

**Stack:** React 18, Vite, TypeScript, Tailwind CSS, Recharts, react-dnd, zustand

**Architecture:**
- **App Shell** — Three-panel flex layout: TopBar | Sidebar (260px) | Canvas (fluid) | StatsPanel (300px collapsible)
- **TopBar** — Logo, workspace name, "Save Session" button (opens SaveSessionModal for naming bookmarks)
- **Chat Bar** — Fixed bottom input, submits to `POST /query`, displays streaming skeleton during API calls
- **Canvas** — 2×3 CSS Grid with DndProvider (react-dnd), DraggableCard wrappers, DropCell targets, ErrorThread for inline error display
- **VisualizationCard** — Composes ChartRenderer (Recharts), CardToolbar, TransparencyDrawer, FullscreenModal
- **ErrorCard** — Inline error display for 422/503/504/408 errors with retry buttons for retryable failures
- **StatsPanel** — Displays per-column statistics from the card's metadata; accordion mode on mobile
- **Sidebar** — Chat thread history, bookmarks with save/load/delete (with unsaved-changes confirmation), "New Chat" button
- **Session Store** — zustand with localStorage persistence for session state, bookmarks, layout

**Key behaviors:**
- Auto-selects chart type (line/bar/scatter/pie/heatmap/table) from column metadata
- Pinned cards survive new query additions; oldest unpinned card replaced when canvas is full
- Canvas-full notification when all 6 cards are pinned (prompts user to unpin or remove)
- Error cards with retry buttons for 503/504 and timeout errors; 422 errors show message inline
- CSV/PNG export from card toolbar
- "How I got this" transparency drawer on each card
- Session auto-saved to localStorage; bookmarks with named save, load (unsaved-changes confirmation), and delete
- Voice input via Web Speech API (progressive enhancement)
- Fullscreen modal for expanded chart viewing (close via Escape or button)
- Responsive: single-column canvas on narrow screens, stats accordion on mobile

**API contract consumed:**
- `POST http://localhost:8001/query` — body: `{ "query_text": "..." }`
- Success (200): `{ rendered_output: RenderedOutput, latency: {...}, query_id, correlation_id }`
- Error (422): `{ error_code, error_message, query_id }`
- Error (503/504): `{ error, message, query_id }`

---

## Cross-Cutting Concerns

### Logging

**File:** `src/services/logging_config.py`

All services use a shared logging configuration:
- **Console output** — structured JSON logs to stderr (visible in terminal)
- **File persistence** — rotating log file at `logs/system.log` (10MB per file, 7 backups)
- Timestamp, level, and structured JSON for every operation

### Observability

**File:** `src/services/observability.py`

Every service endpoint is wrapped with `@observability_decorator` which emits structured JSON logs:
- `service_name`, `operation_name`, `correlation_id`, `timestamp`, `request_duration_ms`, `status_code`
- On errors: `exception_type`, `exception_message`, `stack_trace`

Correlation IDs propagate between services via `X-Correlation-ID` header.

### Cost Tracking

**File:** `src/services/cost_tracker.py`, `src/services/bedrock_wrapper.py`

Every Bedrock API call is logged to S3 at `costs/{YYYY-MM-DD}/{uuid}.json` with model ID, component, token counts, estimated cost, and correlation ID.

Reports via `python scripts/cost_report.py` (today/daily/monthly/all-time).

### Caching (In-Memory)

| Cache | Location | Key | TTL |
|-------|----------|-----|-----|
| Input guardrail | NLP API | query_text | Process lifetime |
| Classification LRU | NLP Translator | SHA-256(query + entity_refs) | 1000 entries |
| Result Cache | Orchestrator Hub | SHA-256(intent fields) | Process lifetime |
| Guardrail Cache | Guardrail Layer | SHA-256(response JSON) | 500 entries |
| Render Cache | Visualization Renderer | SHA-256(payload + query_type + query_text) | 200 entries |

All caches cleared on service restart.

---

## Latency Profile

### First query (cold, no caches):

| Step | What happens | Typical latency |
|------|-------------|-----------------|
| NLP Translation | Bedrock guardrail + Bedrock classification | 4-6s |
| Orchestrator | Agent resolution + spoke agent HTTP dispatch + S3 fetch | 1-2s |
| Guardrail | Bedrock guardrail (output) | 2-3s |
| Visualization | Strands Agent LLM analysis + chart generation | 20-30s |
| **Total** | | **~30-40s** |

### Repeat query (all caches hit):

| Step | What happens | Typical latency |
|------|-------------|-----------------|
| NLP Translation | Classification cache + guardrail cache | <100ms |
| Orchestrator | Result cache hit | 0ms |
| Guardrail | Guardrail cache hit | 0ms |
| Visualization | Render cache hit | 0ms |
| **Total** | | **<1s** |

### Where the LLM calls are:

| Service | LLM Call | Purpose | Can be removed? |
|---------|----------|---------|-----------------|
| NLP Translator | Bedrock `invoke_model` | Query type classification | No — core NLP function |
| NLP Translator | Bedrock `apply_guardrail` | Input content safety | No — security requirement |
| Orchestrator Hub | None (deterministic) | — | Already removed |
| Spoke Agent | None (deterministic) | — | Already removed |
| Guardrail Layer | Bedrock `apply_guardrail` | Output content safety | No — security requirement |
| Visualization | Strands Agent | Intelligent chart selection + BI insights | Optional (rule-based fallback exists) |

---

## Ontology

**File:** `src/services/ontology_store.py`, `src/models/ontology.py`

**Storage:** S3 at `ontology/{name}.json`. Loaded into memory on service startup.

**Current ontology (`enterprise_ontology`)** — 10 concepts across two domains:
- **Finance:** sales_revenue, order_volume, return_rate, quarterly_report
- **Inventory:** product_catalog, inventory_stock, product_pricing, supplier_info
- **Shared dimensions:** product_category, region

The ontology acts as a gatekeeper — queries that don't match any concept are rejected (`NO_ONTOLOGY_MATCH`). Queries that only weakly match (vague substring) are rejected (`AMBIGUOUS_INTENT`).

---

## Data Sources

| Source | Format | S3 Key | Domain |
|--------|--------|--------|--------|
| Financial Data | JSON | `data-sources/financial_data.json` | Revenue, orders, return rates by quarter/region/category |
| Product Catalog | CSV | `data-sources/product_catalog.csv` | Products, categories, prices, stock, suppliers |

---

## Models Used

| Model | Model ID | Usage |
|-------|----------|-------|
| Claude 3.5 Haiku | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | NLP classification, visualization agent |
| Amazon Titan Embeddings V2 | `amazon.titan-embed-text-v2:0` | Query history embeddings |

---

## AWS Dependencies

- **S3 bucket:** `visualization-poc-bucket`
- **Bedrock:** Claude 3.5 Haiku + Titan Embeddings V2 (us-east-1)
- **Bedrock Guardrails:** ID `unf4323uxnff` (DRAFT version)
- **AWS Profile:** `PowerUserAccess-654654478821`

---

## Startup Sequence

**Backend:** `python run_all.py` launches 5 uvicorn processes:

1. Orchestrator Hub (8002)
2. Guardrail Layer (8003)
3. Visualization Renderer (8004)
4. Spoke Agent (8010)
5. NLP Translator (8001)

After health checks pass, `register_agents.py` registers the spoke agent with the orchestrator. Service logs stream to both terminal and `logs/system.log`.

**Frontend:** `npm run dev` in the `frontend/` directory starts Vite dev server at http://localhost:5173. The frontend calls the backend directly at http://localhost:8001 (CORS enabled with `allow_origins=["*"]`).

---

## Request Lifecycle (End-to-End)

```
1. User types: "show me quarterly sales revenue"
2. POST /query → NLP Translator (8001)
3. [Parallel] Input guardrail check + NLP translation
4. NLP: extract keywords → ontology search → resolve entity_refs
5. NLP: specificity check → strong match confirmed
6. NLP: classify query type via Bedrock → "lookup"
7. NLP: extract viz hints → none (no chart type requested)
8. NLP: produce StructuredIntent {query_type, entity_refs, routing_metadata}
9. NLP → POST /internal/process → Orchestrator Hub (8002)
10. Orchestrator: check cache → MISS
11. Orchestrator: resolve agents via entity_ref overlap → spoke-agent
12. Orchestrator: HTTP dispatch → POST /agents/spoke-agent/invoke (8010)
13. Spoke Agent: entity_refs match financial → query_financial_data
14. Spoke Agent: load JSON from S3, filter rows, return tabular data
15. Orchestrator: merge results → OrchestratorResponse, cache it
16. NLP → POST /internal/validate → Guardrail Layer (8003)
17. Guardrail: schema ✓, Bedrock Guardrails ✓ → "passed", cache it
18. NLP → POST /internal/render → Visualization Renderer (8004)
19. Renderer: normalize payload, check render cache → MISS
20. Renderer: Strands Agent analyzes data, user query, selects chart type
21. Renderer: returns RenderedOutput {chart_type, chart_data, description}
22. Renderer: cache the result
23. NLP → returns response + latency breakdown to client
24. React SPA: parses rendered_output, selects chart type, renders Recharts chart + Stats Panel
```

---

## Error Handling

| Error | Produced by | HTTP Status | Code |
|-------|-------------|-------------|------|
| Empty/whitespace query | NLP Translator | 422 | `UNPARSEABLE_QUERY` |
| No ontology match | NLP Translator | 422 | `NO_ONTOLOGY_MATCH` |
| Vague/ambiguous query | NLP Translator | 422 | `AMBIGUOUS_INTENT` |
| Input content blocked | NLP Translator | 422 | `CONTENT_POLICY_VIOLATION` |
| No agents resolved | Orchestrator | 422 | `NO_AGENTS_RESOLVED` |
| All agents timed out | Orchestrator | 422 | `ALL_AGENTS_TIMED_OUT` |
| Output content blocked | Guardrail Layer | 422 | `rejected` |
| Service unavailable | Any downstream | 503 | `SERVICE_UNAVAILABLE` |
| Timeout | Any downstream | 504 | `GATEWAY_TIMEOUT` |

---

## Configuration

All configuration in `src/config.py`. Key settings:

| Setting | Value | Purpose |
|---------|-------|---------|
| Ports | 8001-8004, 8010 | Service assignments |
| `S3_BUCKET` | `visualization-poc-bucket` | All persistent storage |
| `DEFAULT_MODEL_ID` | Claude 3.5 Haiku | LLM for classification + viz |
| `AGENT_TIMEOUT_DEFAULT` | 30s | Per-agent dispatch timeout |
| `SIMILARITY_THRESHOLD` | 0.85 | Query history cosine threshold |

SSL verification disabled globally for corporate proxy compatibility.

---

## Dependencies

### Backend (Python)

```
fastapi>=0.115.0       — Web framework
uvicorn>=0.34.0        — ASGI server
pydantic>=2.10.0       — Data validation
numpy>=1.26.0          — Cosine similarity
httpx>=0.28.0          — Async HTTP client
boto3>=1.35.0          — AWS SDK (S3, Bedrock)
strands-agents>=0.1.0  — AI agent framework (visualization renderer)
```

### Frontend (Node.js)

```
react ^19             — UI framework
react-dom ^19         — DOM rendering
recharts ^3           — Charting library (bar, line, scatter, pie, heatmap)
react-dnd ^16         — Drag-and-drop
react-dnd-html5-backend ^16 — HTML5 DnD backend
zustand ^5            — State management with localStorage persistence
tailwindcss ^3        — Utility-first CSS
html2canvas ^1        — PNG export from DOM elements
vite ^8               — Dev server and build tool
typescript ~6         — Type checking
vitest ^4             — Test runner
fast-check ^4         — Property-based testing
```
