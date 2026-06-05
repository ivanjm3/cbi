# System Architecture — Ontology NLP Query System

## Overview

This system is an ontology-based, NLP-driven query platform built on a hub-and-spoke microservices architecture. A user submits a natural language question through a web UI. The system classifies the query against a domain ontology, routes it to the appropriate data-retrieval agent, applies content guardrails, generates a visualization, and returns the result — all in a single request cycle.

All AI inference runs on Amazon Bedrock. The default LLM is Claude 3.5 Haiku; embeddings use Amazon Titan Embeddings V2. Persistent storage is entirely S3-backed (no local databases).

---

## High-Level Data Flow

```
┌──────────┐     POST /query      ┌──────────────────┐
│  Web UI  │ ──────────────────→  │  NLP Translator  │ (port 8001)
│  (HTML)  │                      │  + Input Guard   │
└──────────┘                      └────────┬─────────┘
                                           │
                              StructuredIntent (JSON)
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │ Orchestrator Hub │ (port 8002)
                                  │  (routing agent) │
                                  └────────┬─────────┘
                                           │
                              Dispatch to spoke agent(s)
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │   Spoke Agent    │ (port 8010)
                                  │  (data retrieval)│
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
                                  │    Renderer      │
                                  └────────┬─────────┘
                                           │
                              RenderedOutput (chart spec + stats)
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  Web UI renders  │
                                  │  Chart.js chart  │
                                  └──────────────────┘
```

---

## Services

### 1. NLP Translator (port 8001)

**File:** `src/services/nlp_api.py`, `src/services/nlp_translator.py`

**Role:** Entry point for all user queries. Translates natural language into a machine-readable `StructuredIntent`.

**Pipeline:**
1. **Input guardrail** (Bedrock Guardrails, `source=INPUT`) — runs in parallel with NLP translation. If input is blocked, returns 422 immediately.
2. **Entity resolution** — extracts keywords from the query text, searches the ontology for matching concepts. If no concepts match → `NO_ONTOLOGY_MATCH` error.
3. **History bias** (optional) — queries the Query History Store for similar past intents (cosine similarity ≥ 0.85) to extract routing hints.
4. **Query type classification** — calls Claude Haiku via Bedrock `invoke_model` API with ontology context. Classifies into one of: `lookup`, `aggregation`, `comparison`. If unclassifiable → `AMBIGUOUS_INTENT` error.
5. **Produces** a `StructuredIntent` containing: `query_id`, `query_type`, `entity_refs`, `routing_metadata`, `timestamp`.

**Efficiency features:**
- LRU classification cache (1000 entries) — identical query+entity combos skip the Bedrock call.
- Entity resolution and history bias run concurrently (`asyncio.gather`).
- Exact token counts captured from Bedrock response `usage` field for cost tracking.

**Also serves:** The frontend HTML (`GET /`) and orchestrates the full downstream pipeline (Orchestrator → Guardrail → Renderer) before returning to the client.

---

### 2. Orchestrator Hub (port 8002)

**File:** `src/services/orchestrator_api.py`, `src/services/orchestrator_hub.py`

**Role:** Central routing engine. Receives a StructuredIntent, resolves which spoke agents can handle it, dispatches concurrently, and merges results.

**Pipeline:**
1. **Cache check** — computes a deterministic SHA-256 hash of the intent (query_type + sorted entity_refs + sorted routing_metadata). If cached → returns immediately.
2. **Agent resolution** — matches the intent's `entity_refs` against all registered agents' `entity_refs`. An agent is selected if there's any overlap.
3. **Direct dispatch** — sends the StructuredIntent via HTTP POST to all resolved agents concurrently (thread pool). Collects results with per-agent timeout (default 30s).
4. **Merge** — combines successful `AgentResult` objects into an `OrchestratorResponse`. Tracks unavailable/failed agents separately.
5. **Cache store** — caches successful responses for identical future intents.

**Agent registration:** Spoke agents register at startup via `POST /admin/agents` with their `agent_id`, `endpoint_url`, `data_source`, and `entity_refs`. Registration is runtime — no restart needed.

**Note:** The orchestrator has a Strands Agent-based dispatch path (`_agent_dispatch`) where the LLM reasons about which agents to call, but the active code path uses deterministic entity-ref matching (`_direct_dispatch`) without an LLM call.

---

### 3. Spoke Agent (port 8010)

**File:** `src/agents/spoke_agent.py`

**Role:** A unified Strands Agent that retrieves data from multiple sources. Uses LLM tool-calling to decide which data source to query based on the intent.

**Data sources:**
- `financial_data.json` (S3) — quarterly revenue, order volume by category/region
- `product_catalog.csv` (S3) — products, categories, prices, stock, suppliers

**Tools:**
- `query_financial_data(query_type, entity_refs, filters)` — loads the JSON from S3, filters rows by entity keywords, executes lookup/aggregation/comparison logic.
- `query_product_catalog(query_type, entity_refs, filters)` — loads the CSV from S3, parses into dicts, filters, executes query logic.

**Query execution:**
- **Lookup** — returns filtered rows as tabular data (columns + rows).
- **Aggregation** — computes sum, avg, min, max, count for all numeric columns.
- **Comparison** — groups by a categorical column, then aggregates within each group.

**Fallback:** If the Strands Agent doesn't return structured data (LLM didn't produce parseable JSON), the system falls back to deterministic entity-ref matching: financial entities → `query_financial_data`, product entities → `query_product_catalog`.

---

### 4. Guardrail Layer (port 8003)

**File:** `src/services/guardrail_api.py`, `src/services/guardrail_layer.py`

**Role:** Validates the merged orchestrator response before it reaches the visualization renderer. Applies structural schema validation and Amazon Bedrock Guardrails (ML-based content filtering).

**Pipeline:**
1. **Schema validation** — checks structural correctness (results exist, success payloads have data, errors have types).
2. **Cache check** — SHA-256 of the serialized response. If previously validated → returns cached result.
3. **Bedrock Guardrails** (`apply_guardrail` API, `source=OUTPUT`) — checks for hate speech, violence, sexual content, insults, misconduct, PII in the response payload.

**Outcomes:**
- `passed` — content is safe, returns validated response.
- `rejected` — content blocked, returns 422 with triggered policy details.
- `error` — internal failure, returns 500.

**Fail-open policy:** If Bedrock Guardrails are unavailable (network error, service error), the content passes through with a logged warning.

---

### 5. Visualization Renderer (port 8004)

**File:** `src/services/visualization_api.py`, `src/services/visualization_renderer.py`

**Role:** Transforms validated data payloads into interactive Chart.js-compatible chart specifications with statistical annotations.

**Pipeline:**
1. **Payload normalization** — converts aggregation/comparison/tabular/multi-source payloads into a uniform `columns + rows` format.
2. **Statistics generation** — computes key stats (totals, averages, ranges, group breakdowns) as text description.
3. **Strands Agent rendering** — the agent analyzes data shape (temporal vs. categorical vs. numeric patterns) and produces a chart spec with type, datasets, labels, colors, and options.
4. **Fallback** — if the agent fails, a deterministic rule-based engine selects chart type:
   - Time series data → line chart
   - Categories + numbers → bar chart
   - Two numeric columns → scatter plot
   - ≤8 proportional categories → pie chart
   - Everything else → table

**Output:** `RenderedOutput` with `output_type` (chart/text), `chart_type`, `chart_data` (Chart.js spec), `text_content` (stats), `description` (insights), and `metadata`.

---

### 6. Frontend (served from port 8001)

**File:** `frontend/index.html`

**Role:** Single-page HTML application with a query input box. Sends `POST /query` requests to the NLP Translator, receives `RenderedOutput`, and renders charts using Chart.js or displays text/table results.

---

## Cross-Cutting Concerns

### Observability

**File:** `src/services/observability.py`

Every service endpoint is wrapped with `@observability_decorator` which emits structured JSON logs containing:
- `service_name`, `operation_name`, `correlation_id`, `timestamp`, `request_duration_ms`
- On errors: `exception_type`, `exception_message`, `stack_trace`

Correlation IDs are propagated between services via the `X-Correlation-ID` header. If absent on the inbound request, a UUID is generated.

### Cost Tracking

**File:** `src/services/cost_tracker.py`, `src/services/bedrock_wrapper.py`

Every Bedrock API call is logged to S3 at `costs/{YYYY-MM-DD}/{uuid}.json` with:
- Model ID, component name, input/output tokens, estimated cost USD, correlation ID.

The NLP Translator captures **exact** token counts from the Bedrock response. Agent-based components (orchestrator, spoke agent, renderer) use the Strands SDK which doesn't expose tokens directly — these use estimated counts (output tokens ≈ response length / 4, input tokens hardcoded at 100).

Reports are generated via `python scripts/cost_report.py` (today/daily/monthly/all-time).

### Caching (In-Memory)

| Cache | Location | Key | Purpose |
|-------|----------|-----|---------|
| Classification LRU | NLP Translator | SHA-256(query + entity_refs) | Skip repeat Bedrock classification calls |
| Result Cache | Orchestrator Hub | SHA-256(query_type + entity_refs + metadata) | Skip repeat agent dispatches |
| Guardrail Cache | Guardrail Layer | SHA-256(response JSON) | Skip repeat guardrail evaluations |

All caches are in-memory (cleared on service restart). Max size: 500–1000 entries.

### Query History Store

**File:** `src/services/query_history_store.py`

Persists successful query→intent pairs to S3 (`history/{uuid}.json`) with embeddings (Titan V2). Enables similarity search for routing bias — if a past query with ≥0.85 cosine similarity exists, its routing metadata is injected into the new intent as a hint.

---

## Ontology

**File:** `src/services/ontology_store.py`, `src/models/ontology.py`

**Storage:** S3 at `ontology/{name}.json`. Loaded into memory on startup.

**Structure:**
```
OntologyDefinition
├── concepts: [OntologyConcept]
│   ├── concept_id (e.g., "ontology:sales_revenue")
│   ├── label (e.g., "Sales Revenue")
│   ├── properties (domain, unit, description, data_source, ...)
│   └── relationships (outgoing edges)
├── relationships: [OntologyRelationship]
│   ├── source_id → target_id
│   ├── relation_type (contributes_to, contains, grouped_by)
│   └── properties
└── metadata (name, version, timestamps)
```

**Current ontology (`enterprise_ontology`)** defines 10 concepts across two domains:
- **Finance:** sales_revenue, order_volume, return_rate, quarterly_report
- **Inventory:** product_catalog, inventory_stock, product_pricing, supplier_info
- **Shared dimensions:** product_category, region

The ontology acts as a gatekeeper — queries that don't match any ontology concept are rejected with `NO_ONTOLOGY_MATCH`.

---

## Data Sources

| Source | Format | S3 Key | Domain |
|--------|--------|--------|--------|
| Financial Data | JSON | `data-sources/financial_data.json` | Sales revenue, order volume, return rates by quarter/region/category |
| Product Catalog | CSV | `data-sources/product_catalog.csv` | Product names, categories, prices, stock, suppliers |

Both sources are flat files stored in S3. The spoke agent loads them on each query (no local caching of data files).

---

## Models Used

| Model | Model ID | Usage |
|-------|----------|-------|
| Claude 3.5 Haiku | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Default for all LLM calls (classification, orchestrator, spoke agent, visualization) |
| Amazon Titan Embeddings V2 | `amazon.titan-embed-text-v2:0` | Query history embeddings for similarity search |

---

## AWS Dependencies

- **S3 bucket:** `visualization-poc-bucket` (ontology, data sources, cost records, query history)
- **Bedrock:** Claude 3.5 Haiku + Titan Embeddings V2 (us-east-1)
- **Bedrock Guardrails:** ID `joes1p3j7sa4` (DRAFT version) — content filtering policies
- **AWS Profile:** `PowerUserAccess-654654478821`

---

## Startup Sequence

`python run_all.py` launches 5 uvicorn processes in order:

1. Orchestrator Hub (8002)
2. Guardrail Layer (8003)
3. Visualization Renderer (8004)
4. Spoke Agent (8010)
5. NLP Translator (8001)

After all health checks pass, `register_agents.py` registers the spoke agent with the orchestrator hub via `POST /admin/agents`.

---

## Request Lifecycle (End-to-End)

```
1. User types: "show me quarterly sales revenue"
2. POST /query → NLP Translator (8001)
3. [Parallel] Input guardrail check (Bedrock) + NLP translation
4. NLP: extract keywords → search ontology → resolve "ontology:sales_revenue", "ontology:quarterly_report"
5. NLP: classify query type via Bedrock → "lookup"
6. NLP: produce StructuredIntent {query_type: "lookup", entity_refs: [...], ...}
7. NLP → POST /internal/process → Orchestrator Hub (8002)
8. Orchestrator: check result cache → MISS
9. Orchestrator: resolve agents → spoke-agent (entity_refs overlap)
10. Orchestrator: dispatch → POST /agents/spoke-agent/invoke → Spoke Agent (8010)
11. Spoke Agent: Strands Agent calls query_financial_data tool
12. Tool: loads financial_data.json from S3, filters rows, returns tabular data
13. Spoke Agent → returns AgentResult {status: "success", payload: {...}}
14. Orchestrator: merges results → OrchestratorResponse, caches it
15. NLP → POST /internal/validate → Guardrail Layer (8003)
16. Guardrail: schema validation ✓, Bedrock Guardrails ✓ → "passed"
17. NLP → POST /internal/render → Visualization Renderer (8004)
18. Renderer: normalize payload → columns + rows
19. Renderer: Strands Agent analyzes data, selects "bar" chart, generates Chart.js spec
20. Renderer → returns RenderedOutput {chart_type: "bar", chart_data: {...}, description: "..."}
21. NLP → returns full response to client (200 OK)
22. Frontend renders bar chart using Chart.js
```

**Typical latency:** 2–5 seconds (dominated by 4 sequential Bedrock calls).
**Typical cost:** ~$0.001–$0.003 per query at Haiku pricing.

---

## Error Handling

| Error | Produced by | HTTP Status | Code |
|-------|-------------|-------------|------|
| Empty/whitespace query | NLP Translator | 422 | `UNPARSEABLE_QUERY` |
| No ontology match | NLP Translator | 422 | `NO_ONTOLOGY_MATCH` |
| Ambiguous classification | NLP Translator | 422 | `AMBIGUOUS_INTENT` |
| Input content blocked | NLP Translator | 422 | `CONTENT_POLICY_VIOLATION` |
| No agents resolved | Orchestrator | 422 | `NO_AGENTS_RESOLVED` |
| All agents timed out | Orchestrator | 422 | `ALL_AGENTS_TIMED_OUT` |
| Output content blocked | Guardrail Layer | 422 | `rejected` + policy details |
| Service unavailable | Any downstream | 503 | `SERVICE_UNAVAILABLE` |
| Timeout | Any downstream | 504 | `GATEWAY_TIMEOUT` |

---

## Configuration

All configuration lives in `src/config.py`:

| Setting | Value | Purpose |
|---------|-------|---------|
| `NLP_PORT` | 8001 | NLP Translator + Frontend |
| `ORCHESTRATOR_PORT` | 8002 | Orchestrator Hub |
| `GUARDRAIL_PORT` | 8003 | Guardrail Layer |
| `VIZ_PORT` | 8004 | Visualization Renderer |
| `AGENT_A_PORT` | 8010 | Spoke Agent |
| `S3_BUCKET` | `visualization-poc-bucket` | All S3 storage |
| `DEFAULT_MODEL_ID` | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | LLM for all agents |
| `EMBEDDINGS_MODEL_ID` | `amazon.titan-embed-text-v2:0` | Query history embeddings |
| `AGENT_TIMEOUT_DEFAULT` | 30s | Per-agent dispatch timeout |
| `SIMILARITY_THRESHOLD` | 0.85 | Minimum cosine similarity for history matching |

SSL verification is disabled globally (`verify=False`) for corporate proxy compatibility.

---

## Dependencies

```
fastapi>=0.115.0       — Web framework for all services
uvicorn>=0.34.0        — ASGI server
pydantic>=2.10.0       — Data validation and serialization
numpy>=1.26.0          — Cosine similarity computation
httpx>=0.28.0          — Async HTTP client for inter-service calls
boto3>=1.35.0          — AWS SDK (S3, Bedrock)
strands-agents>=0.1.0  — AI agent framework (Bedrock tool-calling)
```

Dev dependencies: `hypothesis`, `pytest`, `pytest-asyncio`

---

## Known Limitations

1. **No RDBMS source** — both data sources are S3 flat files. The original design called for one source in an AWS RDS.
2. **Visualization is separate from data retrieval** — the spoke agent returns raw data; a separate service generates visuals. Originally the data agent was to produce both.
3. **Input guardrails run in parallel with NLP** — they don't block before the classification Bedrock call fires, so a rejected input still incurs one LLM call cost.
4. **In-memory caches** — classification, result, and guardrail caches are lost on restart. Not S3-persisted.
5. **Agent cost tracking is estimated** — Strands SDK doesn't expose token counts, so orchestrator/spoke/renderer costs are approximate.
6. **Query history similarity search is O(n)** — loads all embeddings from S3 on every search. Fine for POC volume.
7. **No authentication** — all endpoints are open (suitable for local dev only).
