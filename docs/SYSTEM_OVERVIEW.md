# Conversational BI System — Comprehensive System Overview

> A complete guide for anyone unfamiliar with the project. Covers what the system does, how it works, its architecture, every file's purpose, and how data flows from a user's question to an interactive chart.

---

## 1. What Is This System?

This is a **Conversational Business Intelligence (BI) platform**. Users type natural language questions like *"show me quarterly sales revenue by region"* and the system:

1. Understands the question using NLP + an ontology (knowledge graph of business concepts)
2. Routes it to the right data source (CSV files, JSON files, or Amazon Redshift)
3. Retrieves and aggregates the data
4. Generates an interactive Chart.js visualization
5. Returns it in a React chat UI with analytical insights

Think of it as a "ChatGPT for your company's data" — but with a structured, traceable pipeline instead of a single monolithic LLM call.

---

## 2. Technology Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | React 18, TypeScript, Vite, Zustand (state), Chart.js v4, react-dnd, Tailwind CSS |
| **Backend** | Python 3.11+, FastAPI, Pydantic v2, httpx (async HTTP), uvicorn |
| **LLM** | Amazon Bedrock — Claude 3.5 Haiku (classification + chart generation) |
| **Agent Framework** | Strands SDK (tool-calling AI agents) |
| **Content Safety** | Amazon Bedrock Guardrails (input + output filtering) |
| **Storage** | Amazon S3 (ontology, data sources, cost logs, history) |
| **Data Warehouse** | Amazon Redshift (optional, via Data API) |
| **Testing** | pytest, Hypothesis (property-based), Vitest (frontend) |
| **Deployment** | Docker, AWS App Runner, CloudFront |

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + TypeScript)                          │
│                                                                              │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ ChatInput│→ │ queryApi  │→ │ sessionStore │→ │ ChartRenderer / Cards │  │
│  └──────────┘  └───────────┘  └──────────────┘  └───────────────────────┘  │
│                                                                              │
│  Layout: Sidebar | ChatThread + ChatInput | StatsPanel | TraceabilityPanel   │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │ POST /query (JSON)
                                     │ POST /cancel
                                     │ POST /query/follow-up
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    BACKEND — 5 FastAPI Microservices                          │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  NLP Translator (port 8001) — ENTRY POINT                              │ │
│  │  • Accepts user query                                                  │ │
│  │  • Input guardrail check (Bedrock Guardrails)                          │ │
│  │  • Entity resolution against Ontology Store                            │ │
│  │  • Query type classification (LLM + heuristic fallback)                │ │
│  │  • Produces StructuredIntent                                           │ │
│  │  • Orchestrates full pipeline: NLP → Orchestrator → Guardrail → Viz   │ │
│  └──────────────────────────────┬─────────────────────────────────────────┘ │
│                                  │                                           │
│  ┌───────────────────────────────▼────────────────────────────────────────┐ │
│  │  Orchestrator Hub (port 8002) — ROUTING                                │ │
│  │  • Strands Agent with tool-calling LLM                                 │ │
│  │  • Checks result cache                                                 │ │
│  │  • Resolves agents from entity_refs (ontology overlap)                 │ │
│  │  • Dispatches to spoke agents via HTTP                                 │ │
│  │  • Supports DIRECT (single-agent) + AGENTIC (multi-agent) dispatch     │ │
│  └──────┬─────────────────────────────────────────────────────────┬───────┘ │
│         │                                                         │         │
│  ┌──────▼──────────────────┐              ┌───────────────────────▼───────┐ │
│  │  Spoke Agent (port 8010)│              │ Redshift Spoke Agent (8011)   │ │
│  │  • Queries S3 JSON/CSV  │              │ • Generates SQL via LLM       │ │
│  │  • Deterministic (no LLM)│             │ • Executes via Redshift Data  │ │
│  │  • Lookup/Aggregate/    │              │   API (boto3)                 │ │
│  │    Compare operations   │              │ • Returns tabular/aggregated  │ │
│  └─────────────────────────┘              └───────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Guardrail Layer (port 8003) — CONTENT SAFETY                          │ │
│  │  • Schema validation (structural correctness)                          │ │
│  │  • Amazon Bedrock Guardrails (hate, violence, PII filtering)           │ │
│  │  • Fail-open on Bedrock unavailability                                 │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  Visualization Renderer (port 8004) — CHART GENERATION                 │ │
│  │  • Strands Agent generates Chart.js config via LLM                     │ │
│  │  • 10-level decision tree for chart type selection                     │ │
│  │  • Deterministic fallback (builds chart without LLM)                   │ │
│  │  • 3 retries with error feedback on failure                            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AWS SERVICES                                        │
│                                                                              │
│  ┌──────────────────┐  ┌──────────┐  ┌──────────────────┐  ┌────────────┐  │
│  │ Amazon Bedrock   │  │ Amazon   │  │ Bedrock          │  │ Amazon     │  │
│  │ (Claude 3.5      │  │ S3       │  │ Guardrails       │  │ Redshift   │  │
│  │  Haiku)          │  │          │  │                  │  │ (optional) │  │
│  └──────────────────┘  └──────────┘  └──────────────────┘  └────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Query Lifecycle (End-to-End Data Flow)

Here's exactly what happens when a user types "show me quarterly sales revenue":

```
User types query in ChatInput
        │
        ▼
[1] Frontend sends POST /query to NLP API (port 8001)
    with X-Correlation-ID header for cancellation tracking
        │
        ▼
[2] INPUT GUARDRAIL CHECK (parallel with NLP)
    → Bedrock Guardrails (source=INPUT) checks for harmful content
    → If blocked: returns 422 CONTENT_POLICY_VIOLATION
    → If Bedrock is down: fail-open (allow through)
        │
        ▼
[3] NLP TRANSLATION
    a. Extract keywords from query ("quarterly", "sales", "revenue")
    b. Search Ontology Store for matching concepts
       → Finds: ontology:sales_revenue, ontology:quarterly_report
    c. Specificity check: ensures strong keyword match (not vague)
    d. Classify query type via Bedrock Claude:
       → "aggregation" (could also be "lookup" or "comparison")
    e. Check Query History for similar past queries (routing bias)
    f. Build StructuredIntent:
       {
         query_id: UUID,
         query_type: "aggregation",
         entity_refs: ["ontology:sales_revenue", "ontology:quarterly_report"],
         routing_metadata: {query_text: "...", requested_chart_type: null},
         timestamp: "2025-..."
       }
        │
        ▼
[4] ORCHESTRATOR HUB (port 8002)
    a. Check Result Cache → MISS (first time for this intent)
    b. Resolve agents: entity_refs overlap with registered agents
       → spoke-agent handles ontology:sales_revenue ✓
    c. Single-domain query → DIRECT dispatch (skip LLM reasoning)
    d. POST to http://localhost:8010/agents/spoke-agent/invoke
       with the StructuredIntent JSON
        │
        ▼
[5] SPOKE AGENT (port 8010)
    a. Parse StructuredIntent
    b. Deterministic routing: entity_refs contain financial entities
       → Call query_financial_data()
    c. Fetch s3://visualization-poc-bucket/data-sources/financial_data.json
    d. Filter rows matching "sales_revenue" / "quarterly_report" keywords
    e. Execute aggregation: compute sum, avg, min, max per numeric column
    f. Return AgentResult:
       {
         status: "success",
         payload: {data_type: "aggregation", columns: [...], aggregations: {...}},
         agent_id: "spoke-agent",
         data_source: "financial_data.json"
       }
        │
        ▼
[6] GUARDRAIL LAYER (port 8003)
    a. Schema validation: response has results, no inconsistencies
    b. Bedrock Guardrails (source=OUTPUT): content safety check
    c. Returns GuardrailResult: {status: "passed", validated_response: ...}
        │
        ▼
[7] VISUALIZATION RENDERER (port 8004)
    a. Normalize payload into columns + rows format
    b. Invoke Strands Agent (Claude 3.5 Haiku):
       - Feed data, query context, chart type decision tree
       - Agent calls emit_chart() tool with Chart.js config
    c. If LLM fails (3 retries exhausted):
       - Deterministic fallback builds chart from data shape
    d. Returns RenderedOutput:
       {
         output_type: "chart",
         chart_type: "doughnut",
         chart_data: {type: "doughnut", data: {...}, options: {...}},
         description: "Revenue dominated by Electronics at $3.6M (54%)...",
         metadata: {query_id, latency_ms, ...}
       }
        │
        ▼
[8] NLP API assembles final response, adds latency breakdown
        │
        ▼
[9] Frontend receives response, creates CardState, renders Chart.js canvas
    in the ChatThread with the description as analytical insight
```

---

## 5. Project Structure — File-by-File Reference

### Root Files

| File | Purpose |
|------|---------|
| `run_all.py` | Launcher script — starts all 5 FastAPI services, waits for health, registers agents |
| `pyproject.toml` | Python project config — dependencies, build system, test config |
| `README.md` | Project overview with setup instructions |
| `.dockerignore` | Files excluded from Docker build |
| `.gitignore` | Files excluded from Git |
| `prompt_examples` | Sample queries for testing |

### `src/` — Python Backend

#### `src/config.py`
Central configuration: port assignments, AWS settings (S3 bucket, Bedrock model IDs, Guardrail IDs), Redshift config, boto3 session/client factories.

#### `src/models/`

| File | Purpose |
|------|---------|
| `shared.py` | Core Pydantic models: StructuredIntent, AgentResult, OrchestratorResponse, OrchestratorError, NLPError, GuardrailResult, RenderedOutput, AgentRegistration |
| `ontology.py` | Ontology schema models: OntologyConcept, OntologyRelationship, OntologyDefinition |
| `redshift_models.py` | Redshift-specific models: GeneratedQuery, RedshiftResult, RedshiftError, SQLGeneratorError |

#### `src/agents/`

| File | Purpose |
|------|---------|
| `spoke_agent.py` | FastAPI app (port 8010) — deterministic data agent that queries S3 JSON/CSV based on entity_refs without using LLM |
| `redshift_spoke_agent.py` | FastAPI app (port 8011) — generates SQL, executes against Redshift Data API, formats results for the viz pipeline |

#### `src/services/`

| File | Purpose |
|------|---------|
| `nlp_api.py` | FastAPI app (port 8001) — main entry point; accepts queries, orchestrates full pipeline, serves frontend, handles cancellation |
| `nlp_translator.py` | NLP translation logic — keyword extraction, ontology entity resolution, query type classification via Bedrock + heuristic fallback |
| `orchestrator_api.py` | FastAPI app (port 8002) — HTTP endpoints for the orchestrator (process, cancel, agent registration) |
| `orchestrator_hub.py` | Core routing logic — Strands Agent with tools for cache check, agent resolution, spoke dispatch; supports direct + agentic modes |
| `guardrail_api.py` | FastAPI app (port 8003) — HTTP endpoint for content validation |
| `guardrail_layer.py` | Guardrail logic — schema validation + Bedrock Guardrails content filtering with fail-open resilience |
| `visualization_api.py` | FastAPI app (port 8004) — HTTP endpoint for chart rendering |
| `visualization_renderer.py` | Chart generation — Strands Agent builds Chart.js config via LLM; 10-level decision tree; deterministic fallback; 3 retries |
| `ontology_store.py` | S3-backed ontology store — loads concepts from S3 (or local fallback), provides keyword search, lookup, CRUD |
| `ontology_validator.py` | Validates entity refs exist in the ontology before routing |
| `bedrock_wrapper.py` | Thin wrapper around AWS Bedrock client calls with cost tracking |
| `cache_layer.py` | Generic caching utilities |
| `result_cache.py` | Deterministic hash-based result cache for orchestrator responses |
| `lru_cache.py` | Generic LRU cache implementation used by multiple services |
| `cost_tracker.py` | Logs every Bedrock invocation cost (input/output tokens) to S3 for observability |
| `query_history_store.py` | Stores past queries + intents for similarity matching and routing bias |
| `register_agents.py` | Startup script that registers spoke agents with the Orchestrator Hub via HTTP |
| `cancellation_registry.py` | In-memory registry tracking cancelled query correlation IDs for cooperative cancellation |
| `meta_query_detector.py` | Detects capability/system questions ("what can you do?") and returns text responses without running the data pipeline |
| `text_only_detector.py` | Detects queries that should return text summaries instead of charts |
| `follow_up_handler.py` | Handles conversational follow-up questions about existing charts |
| `observability.py` | Observability decorator for structured logging with correlation IDs |
| `logging_config.py` | Centralized logging configuration |
| `redshift_connector.py` | Boto3 wrapper for Redshift Data API (execute queries, poll for results) |
| `schema_registry.py` | Maps ontology concept_ids to Redshift table schemas for SQL generation |
| `sql_generator.py` | Generates parameterized SQL from StructuredIntents using the schema registry |

### `frontend/` — React + TypeScript UI

#### Core Files

| File | Purpose |
|------|---------|
| `index.html` | HTML entry point for Vite |
| `vite.config.ts` | Vite bundler config |
| `tailwind.config.ts` | Tailwind CSS theme + design tokens |
| `package.json` | NPM dependencies and scripts |

#### `frontend/src/`

| File | Purpose |
|------|---------|
| `App.tsx` | Root component — layout shell: Sidebar, ChatThread, FooterBar, ChatInput, StatsPanel, TraceabilityPanel |
| `main.tsx` | React entry point (renders App) |
| `index.css` | Global CSS (Tailwind base) |

#### `frontend/src/api/`

| File | Purpose |
|------|---------|
| `queryApi.ts` | HTTP client — sends queries to backend, handles cancellation, follow-ups, chart type conversion, timeout (120s) |

#### `frontend/src/store/`

| File | Purpose |
|------|---------|
| `sessionStore.ts` | Zustand store — manages chat thread, cards, strands, saved prompts, sidebar, panels; persists to localStorage |
| `sessionStore.test.ts` | Unit tests for the session store |

#### `frontend/src/types/`

| File | Purpose |
|------|---------|
| `index.ts` | TypeScript interfaces — RenderedOutput, CardState, ChatMessage, SessionState, TransparencyData, etc. |

#### `frontend/src/components/`

| File | Purpose |
|------|---------|
| `ChatInput.tsx` | Text input bar with submit and cancel buttons |
| `ChatThread.tsx` | Scrollable thread of user messages + visualization cards |
| `ChatBar.tsx` | Chat header/toolbar component |
| `ChartRenderer.tsx` | Renders Chart.js canvas from chart_data config |
| `VisualizationCard.tsx` | Card wrapper for a single chart/text result with toolbar |
| `DraggableCard.tsx` | Drag-and-drop wrapper for card reordering |
| `CardToolbar.tsx` | Per-card actions: pin, resize, chart type switching |
| `CardHistoryDropdown.tsx` | Dropdown showing previous chart types for a card |
| `Sidebar.tsx` | Left sidebar — chat history, saved prompts, new chat button |
| `StatsPanel.tsx` | Right panel showing metadata stats for the active card |
| `TraceabilityPanel.tsx` | Right panel showing full query trace (intent, routing, agents) |
| `FooterBar.tsx` | Bottom bar with traceability toggle |
| `ErrorMessage.tsx` | Error display component with retry option |
| `ErrorCard.tsx` | Full error card in the chat thread |
| `FullscreenModal.tsx` | Fullscreen chart viewing modal |
| `SaveSessionModal.tsx` | Modal for saving/bookmarking the current session |
| `StrandConversation.tsx` | Multi-turn conversation UI for follow-up questions on a card |

### `data/` — Data Sources and Ontology

| File | Purpose |
|------|---------|
| `ontology/enterprise_ontology.json` | The domain knowledge graph — 13 concepts (sales_revenue, product_catalog, customer_segments, etc.) with relationships and agent mappings |
| `sources/financial_data.json` | Quarterly financial data — revenue, orders, return rates by category and region |
| `sources/product_catalog.csv` | Product inventory — names, categories, prices, stock, suppliers |
| `guardrail_rules.json` | Local guardrail rule definitions (legacy, now using Bedrock Guardrails) |

### `scripts/` — Utilities

| File | Purpose |
|------|---------|
| `setup_s3.py` | Uploads local data files and ontology to S3 bucket |
| `provision_redshift.py` | Creates Redshift tables and loads sample data for the Redshift agent |
| `cost_report.py` | Generates a cost report from S3 cost logs |

### `deploy/` — Deployment

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build — Node frontend build → Python backend with all 5 services |
| `deploy.sh` | Main deployment orchestration script |
| `create-apprunner.sh` | Creates/updates AWS App Runner service |
| `update-apprunner.sh` | Updates an existing App Runner deployment |
| `create-cloudfront.sh` | Sets up CloudFront distribution for the frontend |
| `buildspec-backend.yaml` | AWS CodeBuild spec for backend container |
| `buildspec-frontend.yaml` | AWS CodeBuild spec for frontend build |
| `test-iam.sh` | Tests IAM permissions for deployment |
| `README.md` | Deployment instructions |

### `tests/` — Testing

| File | Purpose |
|------|---------|
| `unit/test_ontology_store.py` | Unit tests for ontology store operations |
| `unit/test_result_cache.py` | Unit tests for the result cache |
| `unit/test_observability.py` | Unit tests for observability/logging |
| `integration/test_ontology_routing_fix.py` | Integration test for ontology-based routing |
| `properties/` | Property-based tests using Hypothesis (validates invariants like roundtrip serialization, schema conformance) |

### `docs/` — Documentation

| File | Purpose |
|------|---------|
| `SYSTEM_ARCHITECTURE.md` | High-level system architecture |
| `APPLICATION_OVERVIEW.md` | Application overview and feature list |
| `RUNNING_GUIDE.md` | How to run the system locally |
| `COST_TRACKING.md` | Cost tracking and observability docs |
| `AGENTCORE_DEPLOYMENT.md` | Amazon Bedrock AgentCore deployment guide |
| `agentcore-console-deployment-guide.md` | Step-by-step AgentCore setup |
| `agent-system-analysis.md` | Analysis of the agent architecture |

---

## 6. Key Concepts

### 6.1 Ontology (Knowledge Graph)

The **enterprise ontology** (`data/ontology/enterprise_ontology.json`) is the system's brain for understanding business language. It maps:

- **Concepts** → business entities (e.g., "Sales Revenue", "Product Catalog", "Customer Segments")
- **Properties** → each concept knows its domain, data_source, agent_id, whether it's aggregatable
- **Relationships** → how concepts relate (e.g., sales_revenue `contributes_to` quarterly_report, sales_revenue `grouped_by` region)

When a user says "revenue", the system finds `ontology:sales_revenue`, knows it lives in `financial_data`, and is handled by `spoke-agent-json`.

### 6.2 Structured Intent

The canonical intermediate format produced by NLP translation:

```json
{
  "query_id": "uuid",
  "query_type": "lookup | aggregation | comparison",
  "entity_refs": ["ontology:sales_revenue", "ontology:quarterly_report"],
  "routing_metadata": {"query_text": "...", "requested_chart_type": "line"},
  "timestamp": "ISO-8601"
}
```

Every downstream service operates on this — it's the contract between NLP and the rest of the pipeline.

### 6.3 Hub-and-Spoke Architecture

- **Hub** = Orchestrator Hub (decides who to ask)
- **Spokes** = Data agents (answer questions from specific sources)

The Hub resolves which Spoke(s) can answer a query by comparing `entity_refs` in the intent against registered agent `entity_refs`. If the query spans multiple data domains (e.g., "compare product revenue with inventory"), the Hub uses LLM reasoning to dispatch to multiple agents.

### 6.4 Caching Layers

The system caches at 4 levels to minimize LLM cost and latency:

1. **NLP Classification Cache** — same query text + entities → same query_type (LRU, in-memory)
2. **Result Cache** — same StructuredIntent hash → same orchestrator response
3. **Guardrail Cache** — same content hash → same pass/reject decision
4. **Render Cache** — same payload + query → same chart output

### 6.5 Cooperative Cancellation

If a user cancels a query mid-flight:
1. Frontend aborts the HTTP request + sends POST /cancel with correlation_id
2. NLP API registers cancellation + propagates to Orchestrator
3. Orchestrator checks cancellation registry before each agent dispatch
4. Spoke agents check `request.is_disconnected()` before expensive I/O

### 6.6 Deterministic Fallbacks

Every LLM-dependent stage has a heuristic fallback ensuring the system **never fails** due to Bedrock outages:

- NLP classification: keyword-based heuristic → always returns lookup/aggregation/comparison
- Visualization: deterministic chart builder from data shape (no LLM needed)
- Guardrails: fail-open policy (allow content if Bedrock is down)

---

## 7. Data Sources

| Source | Location | Contents |
|--------|----------|----------|
| Financial JSON | S3: `data-sources/financial_data.json` | Quarterly revenue, order volume, return rates by category + region |
| Product CSV | S3: `data-sources/product_catalog.csv` | Product names, categories, prices, stock quantities, suppliers |
| Redshift | AWS Redshift cluster `talktodata` | Sales transactions, customer segments, employee performance (optional) |

---

## 8. Service Ports Summary

| Service | Port | Role |
|---------|------|------|
| NLP Translator | 8001 | Entry point, full pipeline orchestration, frontend serving |
| Orchestrator Hub | 8002 | Agent resolution and dispatch routing |
| Guardrail Layer | 8003 | Content safety validation |
| Visualization Renderer | 8004 | Chart.js config generation |
| Spoke Agent (JSON/CSV) | 8010 | Data retrieval from S3 files |
| Redshift Spoke Agent | 8011 | SQL generation + execution against Redshift |

---

## 9. How to Run

### Backend
```bash
pip install -e ".[dev]"
aws sso login --profile PowerUserAccess-654654478821
python run_all.py
```
This starts all 5 services, waits for health checks, and registers agents.

### Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend at `http://localhost:5173`, proxies API calls to `http://localhost:8001`.

### Docker (production-like)
```bash
docker build -f deploy/Dockerfile -t conversational-bi .
docker run -p 8001:8001 conversational-bi
```
Single container runs all services + serves the built frontend.

---

## 10. Deployment Architecture

Two models supported:

1. **Self-hosted (dev/demo)** — All services on localhost via `run_all.py` or Docker
2. **AWS Production** — Docker container on AWS App Runner (auto-scales), CloudFront CDN for frontend assets, S3 for data, Bedrock for LLM, Redshift for warehouse queries

---

## 11. Design Principles

1. **Microservices via processes** — Each service is a separate FastAPI/uvicorn process; communicates via HTTP. Can be split to separate containers later.
2. **LLM + Deterministic hybrid** — LLM for intelligence, heuristics for resilience.
3. **Ontology-driven routing** — No hardcoded routing rules; the ontology defines what data exists and who owns it.
4. **Fail-open content safety** — Bedrock Guardrails protect against harmful content, but system stays available if Bedrock is down.
5. **Complete observability** — Structured JSON logging, correlation IDs through every service, cost tracking per invocation.
6. **Caching everywhere** — 4-layer cache strategy minimizes cost ($) and latency.
7. **Cooperative cancellation** — Users can cancel any query mid-flight without wasting resources.
