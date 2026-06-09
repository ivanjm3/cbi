# Conversational BI — System Architecture Document

## 1. Overview

The Conversational BI system transforms natural language questions into interactive data visualizations. A user types a question like "show me Q4 revenue by region" into a chat interface, and the system returns a fully rendered Chart.js visualization with analytical insights.

The architecture follows a **hub-and-spoke microservices pattern** — five independent FastAPI services communicate over HTTP REST, each owning a single responsibility in the query lifecycle.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                              │
│  Chat UI → Submit Query → Display Chart.js Visualization             │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ POST /query
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    BACKEND (5 Python Services)                         │
│                                                                        │
│   NLP Translator (8001) ─→ Orchestrator Hub (8002)                    │
│         │                        │                                     │
│         │                  Spoke Agent (8010)                          │
│         │                        │                                     │
│         ├── Guardrail Layer (8003) ←─────┘                            │
│         │                                                              │
│         └── Visualization Renderer (8004)                             │
│                                                                        │
└──────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       AWS SERVICES                                     │
│   Amazon Bedrock (Claude 3.5 Haiku) │ S3 (Data Lake) │ Guardrails    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, zustand, Chart.js v4, react-dnd, Tailwind CSS |
| Backend | Python 3.11+, FastAPI, Pydantic, httpx (async HTTP), Strands SDK |
| LLM | Amazon Bedrock — Claude 3.5 Haiku (`us.anthropic.claude-3-5-haiku-20241022-v1:0`) |
| Agent Framework | Strands SDK (tool-calling agents on Bedrock) |
| Content Safety | Amazon Bedrock Guardrails (ML-based content classifier) |
| Storage | Amazon S3 (`visualization-poc-bucket`) |
| Data Sources | `financial_data.json` (sales/revenue), `product_catalog.csv` (inventory/pricing) |
| Ontology | JSON concept definitions stored in S3 (`ontology/` prefix) |

---

## 3. The Complete Query Lifecycle

This section traces what happens from the moment a user presses Enter to when the chart appears on screen.

### Phase 1: Frontend Submission

```
User types: "show me quarterly revenue by product category"
     │
     ▼
Frontend State Store (zustand)
  ├─ Creates user ChatMessage
  ├─ Sets loading = true
  ├─ Shows typing indicator
  └─ Calls queryBackend(queryText)
```

**Implementation**: `frontend/src/api/queryApi.ts`

The frontend issues a `POST http://localhost:8001/query` with body `{"query_text": "..."}`. A 120-second AbortController timeout protects against hangs. The response is a discriminated union — success returns `RenderedOutput`, failure returns structured error info with HTTP status.

### Phase 2: Input Guardrails (Content Safety)

The NLP Translator service (port 8001) receives the request and immediately does two things **in parallel**:

```python
input_rejection, result = await asyncio.gather(
    asyncio.to_thread(_check_input_guardrails_bedrock, query_text),
    translator.translate(query_text),
)
```

**Input Guardrail** (`Bedrock ApplyGuardrail API`):
- Calls `ApplyGuardrail(source="INPUT")` to check for policy violations
- Filters PII, inappropriate content, prompt injection
- Results cached per query text (no repeated calls for same input)
- **Fail-open policy**: If Bedrock is unavailable, content is allowed through (log warning)
- If rejected → immediate 422 response, pipeline stops

### Phase 3: NLP Translation

The NLP Translator converts the natural language query into a machine-readable `StructuredIntent`.

**Step 3a: Entity Resolution** (concurrent with history bias)
- Extract keywords from query (stop-word removal, multi-word combinations)
- Search the Ontology Store for matching concepts
- Return canonical entity IDs (e.g., `ontology:sales_revenue`, `ontology:region`)
- If no match found → 422 `NO_ONTOLOGY_MATCH`

**Step 3b: Specificity Check**
- Verify at least one keyword substantially matches an ontology concept
- Prevents overly vague queries from consuming downstream resources
- If too vague → 422 `AMBIGUOUS_INTENT`

**Step 3c: Query Type Classification** (Amazon Bedrock Claude)
- **Primary path**: LLM classifies query into `lookup`, `aggregation`, or `comparison`
- **Fallback**: Keyword heuristic if Bedrock unavailable
  - "compare", "vs", "versus" → `comparison`
  - "total", "sum", "average", "trend" → `aggregation`
  - Default → `lookup`
- Results cached by `hash(query_text + entity_refs)` (LRU, 1000 entries)

**Step 3d: Visualization Hints**
- Regex scanning for explicit chart requests ("show me a pie chart")
- Detected types: bar, line, scatter, pie, doughnut, radar, polarArea, bubble, table
- Stored in `routing_metadata.requested_chart_type`

**Output — StructuredIntent:**
```json
{
  "query_id": "550e8400-e29b-41d4-a716-446655440000",
  "query_type": "aggregation",
  "entity_refs": ["ontology:sales_revenue", "ontology:product_category"],
  "routing_metadata": {
    "query_text": "show me quarterly revenue by product category",
    "requested_chart_type": null,
    "preferred_agent": null
  },
  "timestamp": "2024-03-15T10:30:00Z"
}
```

### Phase 4: Orchestration & Routing

The NLP Translator forwards the StructuredIntent to the Orchestrator Hub (port 8002).

**Step 4a: Result Cache Check**
- Generate cache key: `SHA256(query_text | sorted(entity_refs))`
- If cache hit → return immediately (skip data retrieval entirely)

**Step 4b: Agent Resolution**
- In-memory agent registry maps entity_refs → available spoke agents
- Set intersection: find agents whose registered entities overlap with the intent's entity_refs
- If no agents resolved → 422 `NO_AGENTS_RESOLVED`

**Step 4c: Dispatch Strategy**

The system uses two dispatch paths:

| Query Complexity | Strategy | LLM Used? |
|-----------------|----------|-----------|
| Single-domain (most queries) | Direct HTTP dispatch | No |
| Multi-domain comparison | Agentic LLM routing via Strands | Yes |

**Direct Dispatch** (fast path):
- Concurrent HTTP POST to all resolved agents
- Wait for responses (30s timeout per agent)
- Merge results into `OrchestratorResponse`

**Agentic Dispatch** (complex queries):
- Strands Agent with three tools reasons about routing:
  - `check_result_cache(cache_key)` — check if answer exists
  - `resolve_available_agents(entity_refs)` — find capable agents
  - `dispatch_to_spoke_agent(agent_id, url, intent)` — invoke specific agent
- Agent decides which agents to call and in what order

### Phase 5: Data Retrieval (Spoke Agent)

The Spoke Agent (port 8010) is purely deterministic — no LLM involved.

**Data Source Routing** (by entity type):
- Financial entities (`sales_revenue`, `quarterly_report`, `order_volume`) → `financial_data.json`
- Product entities (`product_catalog`, `inventory_stock`, `product_pricing`) → `product_catalog.csv`

**Query Execution by Type:**

| Query Type | Operation | Example Output |
|-----------|-----------|----------------|
| `lookup` | Return filtered rows | Raw data rows matching entity_refs |
| `aggregation` | Compute sum/avg/min/max for numeric columns | `{price: {sum: 50000, avg: 250}}` |
| `comparison` | Group by categorical column, aggregate per group | `{Electronics: {...}, Office: {...}}` |

**Data retrieval from S3:**
- `s3.get_object(Bucket, Key)` — single-attempt, no retry
- Parse JSON or CSV content
- Filter rows by entity_ref matching
- Execute query operation
- Return `AgentResult` with status and payload

### Phase 6: Guardrail Validation (Output Safety)

The Orchestrator results flow back through the Guardrail Layer (port 8003).

**Step 6a: Schema Validation**
- Validate `OrchestratorResponse` structure against Pydantic models
- Check all `AgentResult` objects conform to schema
- Reject malformed responses with 422

**Step 6b: Output Content Filtering**
- `ApplyGuardrail(source="OUTPUT")` on agent result data
- Filters PII leakage, inappropriate content in data values
- LRU cache (500 entries) avoids repeated calls
- **Fail-open on Bedrock unavailability** — data passes through, warning logged

### Phase 7: Visualization Rendering

The validated data reaches the Visualization Renderer (port 8004) — the most LLM-intensive step.

**Two-Path Strategy:**

**Path A — Agentic Rendering** (primary, up to 3 retries):
- Strands Agent with forced `emit_chart` tool use
- Input: normalized columns + rows + query text + query type
- Agent selects chart type using a decision tree in its system prompt
- Generates complete Chart.js v4 configuration
- Each retry provides error feedback to the agent

**Path B — Deterministic Fallback** (after all retries exhaust):
- Heuristic decision tree selects chart type from data shape
- Builds polished Chart.js config without LLM
- Tableau-10 color palette, smooth animations

**Chart Type Selection Decision Tree:**

| Priority | Condition | Chart Type |
|----------|-----------|-----------|
| 1 | User explicitly requested a type | That exact type |
| 2 | Part-of-whole, ≤6 categories | Doughnut |
| 3 | Part-of-whole, >6 categories | Polar Area |
| 4 | Time-series, single metric | Line (area fill) |
| 5 | Time-series, multiple metrics | Multi-line |
| 6 | Two numeric axes | Scatter |
| 7 | Three numeric axes | Bubble |
| 8 | Multi-dimensional profiling | Radar |
| 9 | Ranking, ≤8 items | Horizontal bar |
| 10 | Default fallback | Vertical bar |

**Output — RenderedOutput:**
```json
{
  "output_type": "chart",
  "chart_type": "bar",
  "chart_data": {
    "type": "bar",
    "data": {
      "labels": ["Electronics", "Office", "Furniture"],
      "datasets": [{
        "label": "Quarterly Revenue ($M)",
        "data": [2.1, 1.5, 0.9],
        "backgroundColor": ["rgba(78,121,167,0.82)", "..."]
      }]
    },
    "options": {
      "responsive": true,
      "animation": {"duration": 900, "easing": "easeInOutQuart"},
      "plugins": {"tooltip": {"mode": "index", "intersect": false}}
    }
  },
  "description": "Electronics leads revenue at $2.1M, 47% above Office supplies...",
  "metadata": {
    "query_id": "...",
    "query_type": "aggregation",
    "latency_ms": 42000,
    "data_sources": ["financial_data.json"],
    "entity_refs": ["ontology:sales_revenue", "ontology:product_category"]
  }
}
```

### Phase 8: Response Delivery & Frontend Rendering

The NLP Translator assembles the final response with latency breakdown:

```json
{
  "rendered_output": { "...RenderedOutput..." },
  "latency": {
    "nlp_translation_ms": 1200,
    "orchestrator_ms": 500,
    "guardrail_ms": 300,
    "visualization_ms": 40000,
    "total_ms": 42000
  },
  "query_id": "550e8400-...",
  "correlation_id": "req-12345"
}
```

**Frontend Processing:**
1. `queryBackend()` receives HTTP 200 with `rendered_output`
2. Store creates a `CardState` with the chart config and metadata
3. Store creates a system `ChatMessage` linked to the card
4. `ChatThread` component renders the card in the visualization grid
5. `ChartRenderer` initializes Chart.js canvas with the config
6. `StatsPanel` shows column metadata and data quality stats
7. `TraceabilityPanel` shows query rewrite, structured intent, and API call summary
8. Loading indicator dismisses

---

## 4. Agent Capabilities

### 4.1 NLP Translator (Port 8001) — Gateway Agent

| Capability | Description |
|-----------|-------------|
| Query parsing | Extract keywords, resolve ontology entities |
| Intent classification | Bedrock Claude → lookup/aggregation/comparison |
| Visualization hinting | Detect user-requested chart types from natural language |
| Pipeline orchestration | Coordinates calls to all downstream services |
| Input guardrails | Bedrock content filtering on user input |
| Caching | LRU cache for classifications (1000 entries) |
| Parallel execution | Entity resolution + history bias run concurrently |

**LLM Usage**: Direct Bedrock Claude call (not Strands) for classification only.

### 4.2 Orchestrator Hub (Port 8002) — Routing Agent

| Capability | Description |
|-----------|-------------|
| Agent registry | Runtime register/deregister without restart |
| Entity-based routing | Match agents by entity_ref set intersection |
| Result caching | SHA256-keyed LRU cache for repeated queries |
| Intelligent dispatch | Deterministic for simple queries, LLM for complex |
| Result merging | Combine multi-agent responses into unified output |

**Tools** (Strands Agent, used for multi-domain queries):
- `check_result_cache(cache_key)` — LRU cache lookup
- `resolve_available_agents(entity_refs)` — registry query
- `dispatch_to_spoke_agent(agent_id, endpoint_url, intent_json)` — HTTP POST to agents

### 4.3 Spoke Agent (Port 8010) — Data Agent

| Capability | Description |
|-----------|-------------|
| S3 data retrieval | GET JSON and CSV from S3 bucket |
| Entity-based source routing | Financial vs. product data selection |
| Query execution | lookup, aggregation, comparison operations |
| Columnar aggregation | sum, avg, min, max, count on numeric columns |
| Group-by comparison | Categorical grouping with per-group aggregations |

**LLM Usage**: None — purely deterministic.

### 4.4 Guardrail Layer (Port 8003) — Validation Service

| Capability | Description |
|-----------|-------------|
| Schema validation | Pydantic model conformance checking |
| Output content filtering | Bedrock Guardrails API (ML classifier) |
| Fail-open resilience | Allows content if Bedrock unavailable |
| Result caching | LRU cache (500 entries) for guardrail decisions |

**LLM Usage**: None — ML classifier (Bedrock Guardrails API), not generative LLM.

### 4.5 Visualization Renderer (Port 8004) — Rendering Agent

| Capability | Description |
|-----------|-------------|
| Intelligent chart selection | LLM reasons about best visualization type |
| Chart.js config generation | Complete production-quality configs |
| Analytical insights | 2-4 sentence BI narrative per visualization |
| Data normalization | Transforms raw agent payloads into tabular format |
| Rich styling | Tableau-10 palette, animations, tooltips |
| Retry with feedback | Up to 3 attempts with error context |
| Deterministic fallback | Heuristic chart builder when LLM fails |
| Output caching | LRU cache (200 entries) |

**Tools** (Strands Agent, forced tool use):
- `emit_chart(chart_config, title, description)` — produce Chart.js configuration

---

## 5. Data Flow Diagram (Detailed)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER                                             │
│            "show me quarterly revenue by product category"                    │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (React + zustand + Chart.js)                                       │
│  ┌─────────────┐    ┌───────────────┐    ┌─────────────────┐               │
│  │  ChatInput  │───▶│ sessionStore  │───▶│  queryBackend() │               │
│  │  (user types)│    │ submitQuery() │    │  POST /query    │               │
│  └─────────────┘    └───────────────┘    └────────┬────────┘               │
│                                                    │ HTTP                    │
│  ┌─────────────┐    ┌───────────────┐             │                         │
│  │  ChatThread │◀───│  ChartRenderer│◀── response │                         │
│  │  (grid view)│    │  (canvas)     │             │                         │
│  └─────────────┘    └───────────────┘             │                         │
└───────────────────────────────────────────────────┼─────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  NLP TRANSLATOR (Port 8001) — Gateway                                        │
│                                                                               │
│  ┌────────────────────────────────────────────────────────────────┐          │
│  │  PARALLEL EXECUTION                                             │          │
│  │  ┌─────────────────────┐   ┌──────────────────────────────┐   │          │
│  │  │  Input Guardrails   │   │  NLP Translation              │   │          │
│  │  │  (Bedrock API)      │   │  ├─ Entity Resolution         │   │          │
│  │  │  → Allow / Block    │   │  ├─ Specificity Check         │   │          │
│  │  └─────────────────────┘   │  ├─ Query Classification (LLM)│   │          │
│  │                             │  └─ Viz Hint Extraction       │   │          │
│  └────────────────────────────────────────────────────────────────┘          │
│                                        │                                      │
│                                        ▼ StructuredIntent                     │
│                            POST /internal/process                              │
└────────────────────────────────┬──────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATOR HUB (Port 8002) — Router                                       │
│                                                                               │
│  ┌───────────────┐    ┌──────────────────┐    ┌────────────────────┐        │
│  │ Cache Check   │───▶│ Agent Resolution │───▶│ Dispatch Strategy  │        │
│  │ (SHA256 key)  │    │ (entity overlap) │    │ Simple → Direct    │        │
│  │ Hit → Return  │    │                  │    │ Complex → Agentic  │        │
│  └───────────────┘    └──────────────────┘    └─────────┬──────────┘        │
│                                                          │                    │
└──────────────────────────────────────────────────────────┼────────────────────┘
                                                           │
                                 POST /agents/spoke-agent/invoke
                                                           │
                                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  SPOKE AGENT (Port 8010) — Data Retrieval                                    │
│                                                                               │
│  ┌──────────────────────┐    ┌───────────────────────────────────────┐      │
│  │ Source Routing        │    │ Query Execution                       │      │
│  │ Financial entities    │    │ lookup → filter rows                  │      │
│  │   → financial_data.json│   │ aggregation → sum/avg/min/max         │      │
│  │ Product entities      │    │ comparison → group-by + aggregate     │      │
│  │   → product_catalog.csv│   │                                       │      │
│  └──────────────────────┘    └───────────────────────────────────────┘      │
│                                         │                                     │
│                                         ▼ AgentResult                         │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          │ (bubbles back through Orchestrator)
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  GUARDRAIL LAYER (Port 8003) — Validation                                    │
│                                                                               │
│  ┌──────────────────────┐    ┌──────────────────────────────────────┐       │
│  │ Schema Validation    │───▶│ Bedrock Guardrails (source=OUTPUT)   │       │
│  │ (Pydantic models)   │    │ PII / policy filtering               │       │
│  │                      │    │ Fail-open if unavailable             │       │
│  └──────────────────────┘    └──────────────────────────────────────┘       │
│                                         │                                     │
│                                         ▼ ValidatedResponse                   │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          │ POST /internal/render
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  VISUALIZATION RENDERER (Port 8004) — Chart Agent                            │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │ PATH A: Agentic Rendering (primary, 3 retries)                   │       │
│  │  Strands Agent → emit_chart tool (forced)                        │       │
│  │  LLM selects chart type + generates Chart.js config              │       │
│  │  Retry with error feedback on failure                            │       │
│  ├──────────────────────────────────────────────────────────────────┤       │
│  │ PATH B: Deterministic Fallback (after retries exhaust)           │       │
│  │  Heuristic chart selection from data shape                       │       │
│  │  Template-based Chart.js config builder                          │       │
│  └──────────────────────────────────────────────────────────────────┘       │
│                                         │                                     │
│                                         ▼ RenderedOutput                      │
└─────────────────────────────────────────┬─────────────────────────────────────┘
                                          │
                                          │ HTTP 200 to NLP Translator
                                          │ NLP Translator returns to Frontend
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  FRONTEND RENDERING                                                          │
│                                                                               │
│  ┌──────────────┐   ┌───────────────┐   ┌─────────────────────────┐        │
│  │ CardState    │──▶│ ChatThread    │──▶│ ChartRenderer (canvas)  │        │
│  │ created in   │   │ grid layout:  │   │ Chart.js v4 init        │        │
│  │ zustand store│   │ 1→full, 2→2col│   │ Interactive tooltip     │        │
│  └──────────────┘   │ 3→2+1, 4→2x2 │   └─────────────────────────┘        │
│                      └───────────────┘                                        │
│  ┌──────────────┐   ┌───────────────┐                                        │
│  │ StatsPanel   │   │ Traceability  │                                        │
│  │ (metadata)   │   │ Panel (debug) │                                        │
│  └──────────────┘   └───────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Caching Strategy

Caching is layered throughout the system to minimize LLM costs and latency for repeated queries.

| Layer | Cache Type | Key | Size | Effect |
|-------|-----------|-----|------|--------|
| NLP Translator | Query classification | `hash(text + entity_refs)` | 1000 entries | Skip Bedrock call |
| NLP Translator | Input guardrails | Query text | Unbounded | Skip Bedrock Guardrail call |
| Orchestrator Hub | Full orchestrator result | `SHA256(text \| entities)` | Unbounded | Skip dispatch + data retrieval |
| Guardrail Layer | Output validation | Response hash | 500 entries | Skip output guardrail call |
| Visualization Renderer | Rendered output | `SHA256(cols \| rows \| type \| text)` | 200 entries | Skip LLM rendering |

**Invalidation**: All caches are in-memory with no TTL (session-scoped). Service restart clears all caches.

**Cost impact**: A repeated identical query costs $0 (all cached). First query typically costs $0.002–$0.005 in Bedrock invocations.

---

## 7. Error Handling & Resilience

| Stage | Error | HTTP Status | Recovery Strategy |
|-------|-------|-------------|-------------------|
| Input | Empty/whitespace query | — | Frontend prevents submission |
| Input | Content policy violation | 422 | User reformulates query |
| NLP | No ontology match | 422 | User uses more specific terms |
| NLP | Ambiguous intent | 422 | User adds keywords |
| NLP | Bedrock unavailable | — | Heuristic fallback (never fails) |
| Orchestrator | No agents resolved | 422 | Admin registers agents |
| Orchestrator | All agents timed out | 504 | Retry or increase timeout |
| Spoke | S3 unavailable | 500 | Service restart, check AWS |
| Guardrails | Bedrock unavailable | — | Fail-open (allow content) |
| Visualization | LLM fails all retries | — | Deterministic fallback chart |
| Any service | Connection refused | 503 | Start missing service |
| Any service | Timeout | 504 | Increase timeout or retry |

**Design Principles:**
- **Never fail silently**: Every fallback path logs a structured warning
- **Fail-open for safety services**: Guardrails don't block on Bedrock outages
- **Always produce output**: Classification and visualization have deterministic fallbacks
- **Correlation IDs**: Propagated via `X-Correlation-ID` header for end-to-end tracing

---

## 8. Observability & Cost Tracking

### Logging
- Structured JSON to stdout via Python's logging module
- Fields: service_name, operation, event, error_type, error_message, correlation_id
- Example: `{"service_name": "nlp_translator", "event": "llm_classification_failed", "fallback": "heuristic"}`

### Cost Tracking
Every Bedrock invocation is logged to S3:
```
s3://visualization-poc-bucket/costs/{YYYY-MM-DD}/{uuid}.json
{
  "timestamp": "...",
  "model_id": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
  "component": "nlp_translator",
  "input_tokens": 450,
  "output_tokens": 5,
  "cost_usd": 0.0003
}
```

### Correlation IDs
- Generated at the gateway (NLP Translator) if not present in request headers
- Propagated to all downstream services via `X-Correlation-ID` header
- Enables tracing a single user query across all 5 services

---

## 9. Frontend Architecture

### State Management (zustand)

The frontend uses a single zustand store (`useSessionStore`) with localStorage persistence:

| State | Description |
|-------|-------------|
| `chatThread` | Array of `ChatMessage` (user, system, error) |
| `cards` | Map of `CardState` objects (chart configs, metadata) |
| `activeCardId` | Currently selected card for stats/traceability panels |
| `chatHistory` | Up to 50 thread summaries (auto-saved on first message) |
| `savedPrompts` | Up to 50 bookmarked sessions |
| `loading` | True while API call in flight |

### Visualization Grid Layout

Cards are displayed in a structured grid pattern:

| Card Count | Layout |
|-----------|--------|
| 1 | Full width, single row |
| 2 | Full width, stacked vertically |
| 3 | Row 1: 2 cards, Row 2: 1 card |
| 4 | 2×2 grid |
| 5 | Row 1: 2, Row 2: 2, Row 3: 1 |
| 6 | 3×2 grid |
| >6 | Modal prompts user to delete one |

### Key Components

| Component | Role |
|-----------|------|
| `ChatThread` | Renders visualization grid + error messages + typing indicator |
| `DraggableCard` | Wraps cards with react-dnd drag-to-reorder + resize handles |
| `VisualizationCard` | Chart.js canvas + toolbar (pin, fullscreen, export) |
| `ChartRenderer` | Chart.js initialization and lifecycle management |
| `ChatInput` | Query input with voice support (Web Speech API) |
| `Sidebar` | Chat history, saved prompts, new chat |
| `StatsPanel` | Column metadata and data quality stats |
| `TraceabilityPanel` | Query rewrite, structured intent, API call details |
| `SaveSessionModal` | Bookmark current chat to "Saved Prompts" |

---

## 10. Deployment on Amazon Bedrock AgentCore

### What Changes

Deploying on AgentCore fundamentally changes the infrastructure layer while preserving the business logic:

| Aspect | Current (Self-Hosted) | On AgentCore |
|--------|----------------------|--------------|
| Hosting | 5 FastAPI processes on localhost | Managed serverless agents |
| Scaling | Manual (fixed capacity) | Automatic (per-invocation) |
| Inter-service calls | HTTP POST on localhost ports | AgentCore internal routing |
| Cold start | None (always-on) | ~1-2s first request |
| Guardrails | Separate service (port 8003) | Native per-agent configuration |
| Monitoring | Custom JSON logs + S3 cost files | CloudWatch + X-Ray built-in |
| Agent registry | In-memory (lost on restart) | Managed by AgentCore |
| Infrastructure cost | EC2/ECS instances 24/7 | Pay per invocation only |

### Architecture on AgentCore

```
┌──────────────┐       ┌──────────────────────────────────────────────┐
│   Frontend   │       │           Amazon Bedrock AgentCore            │
│   (React)    │       │                                              │
│   hosted on  │       │  ┌─────────────────────────────────────────┐  │
│   CloudFront │       │  │  Gateway Agent (NLP Translator)         │  │
└──────┬───────┘       │  │  - classify_query (tool)                │  │
       │               │  │  - resolve_entities (tool)              │  │
       │  HTTPS        │  │  - invoke_orchestrator (tool)           │  │
       ▼               │  └──────────┬──────────────────────────────┘  │
┌──────────────┐       │             │                                  │
│ API Gateway  │───────│  ┌──────────▼──────────────────────────────┐  │
│ (REST)       │       │  │  Orchestrator Agent                     │  │
└──────────────┘       │  │  - dispatch_to_agent (tool)             │  │
                       │  │  - merge_results (tool)                 │  │
                       │  └──────────┬──────────────────────────────┘  │
                       │             │                                  │
                       │  ┌──────────▼──────────────────────────────┐  │
                       │  │  Spoke Agent(s)                         │  │
                       │  │  - query_financial_data (tool)          │  │
                       │  │  - query_product_catalog (tool)         │  │
                       │  │  - filter_results (new tool)            │  │
                       │  │  - compute_derived_metric (new tool)    │  │
                       │  └──────────┬──────────────────────────────┘  │
                       │             │                                  │
                       │  ┌──────────▼──────────────────────────────┐  │
                       │  │  Visualization Agent                    │  │
                       │  │  - emit_chart (tool, forced)            │  │
                       │  └─────────────────────────────────────────┘  │
                       │                                                │
                       │  ┌─────────────────────────────────────────┐  │
                       │  │  Guardrails (native, per-agent)         │  │
                       │  └─────────────────────────────────────────┘  │
                       └────────────────────────────────────────────────┘
```

### Key Differences on AgentCore

**1. Guardrail Layer becomes native configuration:**
```yaml
# No separate service — guardrails applied per-agent
guardrails:
  id: joes1p3j7sa4
  version: DRAFT
```
The standalone port 8003 service is eliminated entirely.

**2. Spoke Agent gains agentic capabilities:**

On AgentCore, the spoke agent can be upgraded with LLM reasoning for complex derived queries:
- `filter_results(data, conditions)` — post-query filtering
- `compute_derived_metric(data, formula)` — calculate growth rates, percentages, YoY changes

This enables queries like "what's the revenue growth rate quarter over quarter?" without changes to the frontend.

**3. Inter-agent communication is managed:**

Instead of HTTP POST between localhost ports, AgentCore handles agent-to-agent invocation internally. The Gateway Agent calls the Orchestrator Agent which calls Spoke Agents — all managed by the runtime.

**4. Frontend change is minimal:**

```typescript
// Only change: API_BASE URL
// Before:
const API_BASE = 'http://localhost:8001';

// After (via environment variable):
const API_BASE = import.meta.env.VITE_API_URL
  || 'https://your-api-id.execute-api.us-east-1.amazonaws.com/prod';
```

### Migration Steps

1. Package each service's tool functions as standalone Python handlers
2. Define `agent.yaml` for each agent (model, instructions, tools, guardrails)
3. Deploy via AWS CDK or CloudFormation
4. Create API Gateway REST endpoint fronting the Gateway Agent
5. Update frontend `VITE_API_URL` environment variable
6. Configure CloudWatch alarms for error rate and latency
7. Test end-to-end with production data
8. Cut over (DNS update or environment variable swap)

---

## 11. Performance Characteristics

| Stage | Typical Latency | Notes |
|-------|----------------|-------|
| Frontend → NLP Translator | <50ms | Local network |
| Input Guardrails (Bedrock) | 200-500ms | Cached after first call |
| Entity Resolution (Ontology) | 100-300ms | S3 reads |
| Query Classification (LLM) | 800-1500ms | Cached after first call |
| Orchestrator routing | <50ms | In-memory registry |
| Spoke Agent S3 read | 200-500ms | Network to S3 |
| Query execution | <50ms | In-memory filtering |
| Output Guardrails | 200-500ms | Cached |
| Visualization (LLM) | 30-45s | Most expensive step |
| Visualization (cached) | <1ms | LRU cache hit |
| **Total (first query)** | **35-50s** | Dominated by viz LLM |
| **Total (cached query)** | **<100ms** | All layers cached |

---

## 12. Security Model

| Concern | Implementation |
|---------|---------------|
| Input sanitization | Bedrock Guardrails (INPUT source) |
| Output filtering | Bedrock Guardrails (OUTPUT source) |
| PII protection | Bedrock Guardrail content policy |
| CORS | FastAPI middleware (currently `allow_origins=["*"]` for dev) |
| AWS credentials | boto3 profile-based (`PowerUserAccess-654654478821`) |
| Query injection | Entity resolution constrains queries to ontology concepts |
| Data access | S3 bucket policy + IAM role |

---

## 13. Local Development Quick Reference

### Starting All Services

```bash
python run_all.py
# Starts: 8001, 8002, 8003, 8004, 8010

cd frontend && npm run dev
# Vite dev server on port 5173
```

### Service Health Checks

```bash
curl http://localhost:8001/health  # NLP Translator
curl http://localhost:8002/health  # Orchestrator Hub
curl http://localhost:8003/health  # Guardrail Layer
curl http://localhost:8004/health  # Visualization Renderer
curl http://localhost:8010/health  # Spoke Agent
```

### Manual Query Test

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query_text": "show me total revenue by region"}'
```

### Cost Report

```bash
curl http://localhost:8001/cost-report
```

---

## 14. Summary

The system transforms `"show me revenue by region"` into an interactive chart through a 5-service pipeline:

1. **Parse** the natural language into a structured intent (NLP Translator + Bedrock)
2. **Route** the intent to the right data agent (Orchestrator Hub)
3. **Retrieve** data from S3 sources (Spoke Agent)
4. **Validate** the response for safety and schema (Guardrail Layer)
5. **Visualize** the data as a Chart.js config (Visualization Renderer + Bedrock)
6. **Display** the chart in a grid layout with metadata panels (Frontend)

Each service is independently deployable, cacheable, and has graceful degradation. The system is designed to migrate to AgentCore with minimal code changes — primarily infrastructure configuration rather than business logic rewrites.
