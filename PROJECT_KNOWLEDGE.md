# Project Knowledge: Conversational BI System

## Overview

This is a conversational Business Intelligence (BI) system that lets users ask natural language questions about business data and receive interactive visualizations. The user types a question ("show me revenue by region"), the system resolves the intent, queries the relevant data source, validates the result, renders a chart, and returns it to a React frontend.

The backend is a set of Python FastAPI microservices communicating over HTTP on localhost. The frontend is a React/TypeScript SPA. All persistent state (ontology, history, scheduled reports) is stored in AWS S3. AI capabilities come from Amazon Bedrock (Claude Haiku for LLM, Titan for embeddings).

---

## Service Architecture

All services run on localhost with fixed ports:

| Port | Service | Module |
|------|---------|--------|
| 8001 | NLP Translator (entry point) | `src/services/nlp_api.py` |
| 8002 | Orchestrator Hub | `src/services/orchestrator_api.py` |
| 8003 | Guardrail Layer | `src/services/guardrail_api.py` |
| 8004 | Visualization Renderer | `src/services/visualization_api.py` |
| 8005 | Scheduling API | `src/services/scheduling_api.py` |
| 8010 | Spoke Agent (S3/JSON/CSV) | `src/agents/spoke_agent.py` |
| 8011 | Redshift Spoke Agent | `src/agents/redshift_spoke_agent.py` |
| 8012 | MCP Adapter Layer | `src/agents/mcp_adapter/service.py` |
| 7010 | MCP Redshift Server | External process (separate venv) |
| 7020 | MCP S3 Server | External process (separate venv) |

Started via `run_all.py` using `uvicorn` subprocesses.

---

## Full Query Pipeline (Happy Path)

```
Browser → POST /query (8001)
         │
         ├─ Step 0: Meta-query check (capability questions → text response, no pipeline)
         ├─ Step 1: Input Guardrail (Bedrock ApplyGuardrail source=INPUT, parallel with NLP)
         ├─ Step 1: NLP Translation → StructuredIntent
         │             └─ OntologyStore.search_concepts() → entity_refs
         │             └─ BedrockClassifier.classify_query_type() → lookup|aggregation|comparison
         │             └─ History bias from QueryHistoryStore (optional)
         │
         ├─ Step 2: POST /internal/process (8002, Orchestrator Hub)
         │             └─ ResultCache.get() → CACHE_HIT shortcircuits rest
         │             └─ _resolve_agents(entity_refs) → matching AgentRegistrations
         │             └─ _direct_dispatch or _agent_dispatch (Strands Agent for multi-domain)
         │                  └─ HTTP POST /agents/{agent_id}/invoke (8010 or 8011 or 8012)
         │                  └─ AgentResult accumulated in _dispatch_results
         │
         ├─ Step 3: POST /internal/validate (8003, Guardrail Layer)
         │             └─ Schema validation (structural check)
         │             └─ Bedrock ApplyGuardrail source=OUTPUT
         │
         ├─ Step 3.5: TextOnlyDetector (optional early-exit for non-visual queries)
         │
         └─ Step 4: POST /internal/render (8004, Visualization Renderer)
                       └─ Strands Agent calls emit_chart() tool
                       └─ Returns RenderedOutput with Chart.js config
                       └─ Fallback: deterministic chart builder if agent fails
```

Response to browser: `{ rendered_output: RenderedOutput, latency_breakdown: {...} }`

---

## Data Models

### StructuredIntent
Central routing token passed between services.
```python
query_id: UUID
query_type: "lookup" | "aggregation" | "comparison"
entity_refs: list[str]        # e.g. ["ontology:sales_revenue", "ontology:region"]
routing_metadata: dict         # query_text, group_by_hint, target_columns, filter hints
timestamp: datetime
```

### AgentResult
Returned by every spoke agent.
```python
status: "success" | "error"
payload: dict | None           # data_type, columns, rows, row_count OR aggregations dict
error_type: str | None
error_description: str | None
agent_id: str
data_source: str
```

Payload shapes by data_type:
- `tabular`: `{columns: [...], rows: [[...], ...], row_count: N}`
- `aggregation`: `{aggregations: {col: {sum, avg, min, max, count}}, row_count: N}`
- `comparison`: `{group_by: col, groups: {key: {col: {sum, avg}}}, row_count: N}`

### OrchestratorResponse
Merges all agent results.
```python
query_id: UUID
results: list[AgentResult]
unavailable_agents: list[str]
```

### RenderedOutput
Final response to the frontend.
```python
output_type: "chart" | "text"
chart_type: str | None
chart_data: dict | None        # Full Chart.js v4 config
text_content: str | None
description: str               # BI insight text
metadata: dict                 # query_id, query_type, latency_ms, entity_refs, ...
```

---

## NLP Translation (`src/services/nlp_translator.py`)

**NLPTranslator.translate(query_text)**:
1. Run entity resolution (`_resolve_entities`) and history bias (`_get_history_bias`) concurrently.
2. `_resolve_entities` calls `OntologyStore.search_concepts()` for each keyword extracted from the query. Returns a list of `ontology:*` concept IDs.
3. `BedrockClassifier.classify_query_type()` uses Bedrock Claude Haiku to classify into `lookup | aggregation | comparison`. Falls back to `_heuristic_classify()` on Bedrock error (keyword matching: "by/per/for each" → comparison, "total/avg/sum" → aggregation, else lookup).
4. `_extract_column_hints()` scans ontology concept properties for column metadata to build `group_by_hint`, `target_columns`, `matched_keywords` in `routing_metadata`.
5. `_extract_viz_hints()` detects explicit chart type requests ("scatter plot", "pie chart", etc.) and adds `requested_chart_type` to routing_metadata.
6. Returns `StructuredIntent`.

Classification is LRU-cached (1000 entries) to avoid redundant Bedrock calls.

---

## Orchestrator Hub (`src/services/orchestrator_hub.py`)

**OrchestratorHub.process_intent(intent)**:
1. Check cancellation registry.
2. Guard: empty entity_refs → `NO_AGENTS_RESOLVED` error.
3. `ResultCache.get(cache_key)` — SHA-256 of (query_type, sorted entity_refs, sorted routing_metadata).
4. `_resolve_agents(entity_refs)` — iterates `_agents` dict, returns agents whose entity_refs overlap with intent's entity_refs.
5. Dispatch strategy:
   - **Multi-domain comparison** (entity_refs span agents with different `data_source` values): `_agent_dispatch()` — invokes a Strands Agent (Claude Haiku) with the resolved agents list and intent; the LLM calls `dispatch_to_spoke_agent` tool(s).
   - **Single-domain / same-source**: `_direct_dispatch()` — loops resolved agents, calls `dispatch_to_spoke_agent` directly (no LLM needed).
6. `_build_response_from_results()` builds `OrchestratorResponse` from accumulated `_dispatch_results` list.
7. Caches successful response.

`dispatch_to_spoke_agent` is a Strands `@tool` that does `httpx.Client.post(f"{endpoint_url}/agents/{agent_id}/invoke", json={"structured_intent": ...})`.

**Feature flag routing**: `FeatureFlagRouter` can redirect dispatch to the MCP Adapter (port 8012) instead of legacy spoke agents when `USE_MCP_REDSHIFT` or `USE_MCP_S3` env vars are set.

**Cancellation**: `CancellationRegistry` (in-memory, TTL 300s) is checked before and during dispatch. `POST /internal/cancel` registers a correlation_id as cancelled and propagates to the orchestrator.

---

## Spoke Agent — S3/JSON/CSV (`src/agents/spoke_agent.py`, port 8010)

Handles: `ontology:sales_revenue`, `ontology:order_volume`, `ontology:return_rate`, `ontology:quarterly_report`, `ontology:product_catalog`, `ontology:inventory_stock`, `ontology:product_pricing`, `ontology:supplier_info`.

Data sources in S3:
- `data-sources/financial_data.json` — quarterly sales, revenue, order volume by category/region.
- `data-sources/product_catalog.csv` — products, categories, prices, stock quantities, suppliers.

**Routing**: `_fallback_direct_query()` checks entity_refs against two hardcoded sets (`financial_entities`, `product_entities`) to decide which data source(s) to query.

**Query execution** (`_execute_query`):
- `lookup` → `_execute_lookup()`: returns filtered/sorted rows as tabular data.
- `aggregation` → `_execute_aggregation()`: groups by `group_by_hint` column if present, otherwise returns scalar aggregation dict.
- `comparison` → `_execute_comparison()`: groups by first categorical column (or hinted column).

**Filtering** (`_filter_rows_dict`): Parses `routing_metadata.query_text` with regex to extract quarter, year, region, category, supplier, boolean, and numeric threshold conditions. Falls back to entity-ref keyword matching.

No LLM involved — entirely deterministic.

---

## Redshift Spoke Agent (`src/agents/redshift_spoke_agent.py`, port 8011)

Handles: `ontology:workforce_metrics`, `ontology:support_tickets`, `ontology:marketing_campaigns`.

**Startup**: validates Redshift connectivity and schema registry against actual Redshift tables.

**Flow**:
1. `SQLGenerator.generate(intent)` → `GeneratedQuery` with parameterized SQL.
2. `RedshiftConnector.execute_statement(sql, parameters)` → polls Redshift Data API until FINISHED/FAILED/TIMEOUT (30s timeout, 500ms–2s polling with exponential backoff).
3. `_format_payload(query, result)` → maps to tabular/aggregation/comparison payload.

**SQLGenerator** (`src/services/sql_generator.py`):
- Resolves entity_refs via `SchemaRegistry` to `TableMapping` objects.
- `_generate_lookup()`: SELECT with optional WHERE + ORDER BY (for "top N" queries) + LIMIT.
- `_generate_aggregation()`: SELECT AGG(numeric_cols) [GROUP BY categorical_cols] with WHERE. Only adds GROUP BY when `group_by_hint` is explicitly set.
- `_generate_comparison()`: SELECT categorical_col, AGG(numeric_cols) GROUP BY categorical_col.
- `_build_where_clause()`: maps `routing_metadata.filters` to parameterized conditions via `table.filter_mappings`.
- All SQL uses `:param_name` placeholders (safe from injection).

---

## MCP Adapter Layer (`src/agents/mcp_adapter/`, port 8012)

Optional layer that routes traffic through MCP servers instead of direct boto3 calls. Activated when `USE_MCP_REDSHIFT=true` or `USE_MCP_S3=true`.

- **MCP Redshift Server** (port 7010): exposes SQL execution tools over streamable-HTTP MCP protocol.
- **MCP S3 Server** (port 7020): exposes S3 data access tools.
- **MCPClientManager**: manages persistent MCP connections with reconnect logic.
- **IntentRouter**: maps entity_refs via OntologyStore `data_source` property to `("s3"|"redshift", dataset_name)`.
- **RedshiftTranslator**: converts StructuredIntent → SQL via SQLGenerator → calls MCP tool.
- **S3Translator**: converts StructuredIntent → MCP tool call for S3 file access.
- **FallbackHandler**: on MCP unavailability, falls back to legacy spoke agents (HTTP call to port 8010/8011).

---

## Guardrail Layer (`src/services/guardrail_layer.py`, port 8003)

Two-step validation:
1. **Schema validation**: checks `OrchestratorResponse` structure — at least one result, success payloads not null, error results have error_type.
2. **Bedrock Guardrails** (OUTPUT mode): calls `apply_guardrail` with concatenated JSON of all agent payloads. If `action == "GUARDRAIL_INTERVENED"` → rejected with 422. On Bedrock error → fail open (pass through).

Results are cached by SHA-256 hash of serialized response (LRU 500 entries).

Returns `GuardrailResult` with status `passed | redacted | rejected | error`.

---

## Visualization Renderer (`src/services/visualization_renderer.py`, port 8004)

**Primary path**: Strands Agent (Claude Haiku) with a single `emit_chart` tool. The agent is prompted with normalized tabular data and asked to produce a complete Chart.js v4 config. Retries up to 3 times with error feedback on failure.

**emit_chart tool**: stores result in module-level `_last_emit_chart_result`. Agent must provide `chart_config` (valid JSON with `type`, `data`, `options`), `title`, and `description` (BI insight text).

**Chart selection heuristics** (`_guess_chart_type`): decision tree used as a hint to the agent:
- Part-of-whole + 1 numeric: doughnut (≤6 groups) or polarArea (>6 groups).
- Time-series column (date/month/year/quarter): line_area (single metric) or line (multi).
- 2 numeric axes, ≥6 rows: scatter.
- 3 numeric axes, 4–30 rows: bubble.
- Multi-metric, ≤8 entities: radar.
- 1 numeric, ≤12 items: horizontal bar.
- Else: bar (last resort).

**Fallback** (`_build_fallback_chart`): deterministic chart builder from columns + rows, handles scatter, bubble, doughnut, pie, polarArea, radar, horizontal bar, line, bar. Used when agent output is invalid after 3 retries.

**Caching**: LRU cache (200 entries) keyed by SHA-256 of payload + query_type + query_text. Also checks render cache before calling the agent.

The renderer normalizes payloads first (`_normalize_payload`) before passing to agent, converting aggregation/comparison dicts to tabular columns+rows format.

---

## Ontology Store (`src/services/ontology_store.py`)

S3-backed store at `s3://visualization-poc-bucket/ontology/*.json`. Falls back to `data/ontology/*.json` local files when S3 is unavailable.

Each ontology definition is an `OntologyDefinition` with:
- `concepts: list[OntologyConcept]` — each has `concept_id`, `label`, `properties` (arbitrary dict including `columns`, `filter_keywords`, `categorical_properties`, `data_source`), and `relationships`.
- `relationships: list[OntologyRelationship]`.

**search_concepts(keyword)**: multi-tier scoring (exact concept_id → exact label → concept_id words → stemmed → filter_keywords → description). Stems: strips `s`, `es`, `ing`, `tion`, `sion`, `ment`, `ance`, `ence`.

**lookup_concept(concept_id)**: exact match.

---

## Result Cache (`src/services/result_cache.py`)

In-memory Python dict. Key = SHA-256 of `(query_type, sorted(entity_refs), sorted(flattened_routing_metadata))`. No TTL — cleared on restart. Invalidated per-key when `X-Skip-Cache: true` header is present (used by scheduled executions to force fresh data).

---

## Scheduled Reports (`src/services/scheduling_api.py`, port 8005)

Full CRUD REST API for scheduled reports.

**Storage**: `ScheduledReportsRepository` persists `ScheduledReportConfig` objects to S3 at `scheduled-reports/{user_id}/{report_id}.json` with an index at `scheduled-reports-index.json`.

**Scheduling**: dual-mode:
1. **APScheduler** (`local_scheduler.py`): always runs in-process. `CronTrigger` jobs call `execute_scheduled_report()` directly. Syncs jobs from S3 on startup. Works without IAM PassRole.
2. **EventBridge Scheduler** (`scheduler_manager.py`): creates rules targeting a Step Functions state machine. Used when AWS IAM permits it. Failures are caught and logged — local scheduler always wins.

**Execution**: `execute_scheduled_report(body)` replays each `structured_intent` stored on the report through the NLP pipeline:
1. Normalizes stored intent via `_normalize_structured_intent()` (maps arbitrary query_type to `lookup|aggregation|comparison`, backfills missing fields).
2. Posts to Orchestrator Hub (`/internal/process`) with `X-Skip-Cache: true` header.
3. Posts to Guardrail Layer.
4. Posts to Visualization Renderer.
5. Stores `ExecutionRecord` in S3 and updates `last_run_timestamp` / `last_run_status` on the report.

**Recurrence patterns**: `daily`, `weekday`, `weekly`, `monthly`, `custom`. Timezone-aware via `ZoneInfo`. Next execution validated to be ≤30 days in future.

**Control endpoints**: pause (sets `is_active=false`), resume (recomputes next execution), retry (immediate execution), delete (soft-delete: sets `deleted_at`, preserves execution history).

**Auth**: `X-User-ID` header (or `Authorization: Bearer` token). Ownership enforced on all mutation endpoints.

---

## Frontend (`frontend/src/`)

React 19 SPA, TypeScript, Tailwind CSS, Vite. Served at `http://localhost:8001/` by the NLP API (FastAPI `FileResponse` from `frontend/dist/`).

**State management**: Zustand store (`sessionStore.ts`) with `immer` middleware + localStorage persistence. Holds chat thread, cards (visualization state), strands (multi-turn conversations), sidebar history, saved prompts.

**Routing** (`main.tsx`):
- `/` → `App` (main chat interface)
- `/scheduled-reports` → `ScheduledReportsListPage`
- `/scheduled-reports/new` → `ScheduledReportDetailPage`
- `/scheduled-reports/:reportId` → `ScheduledReportDetailPage`

Drag-and-drop card reordering via `react-dnd`.

**Query flow** (`sessionStore.submitQuery`):
1. Generate UUID correlation ID.
2. `queryBackend(queryText, correlationId, abortSignal)` → `POST http://localhost:8001/query`.
3. 120s client timeout. Returns `RenderedOutput`.
4. Appends `CardState` to store with rendered output.
5. On cancel: calls `cancelQuery(correlationId)` → `POST /cancel`.

**Follow-up queries** (`submitFollowUpQuery`): `POST /query/follow-up` with chart context and conversation history. LLM explains the existing chart; no new data pipeline run.

**Visualization cards** (`VisualizationCard.tsx`):
- Renders Chart.js charts via `react-chartjs-2` + `ChartRenderer.tsx`.
- Dropdown to change chart type (calls `convertChartType` → `POST /api/re-render`).
- Pin/unpin, resize (50%/100%), CSV export, PNG export, fullscreen modal.
- Traceability panel shows raw structured intent and agent call summary.

**Scheduled reports frontend** (`scheduledReportsApi.ts`):
- Calls `http://localhost:8005/scheduled-reports` API.
- Persistent per-browser user ID from `localStorage` (`cbi_user_id`) used as `X-User-ID` header.
- Full CRUD + pause/resume/retry + execution history pagination.

---

## AWS Dependencies

| Service | Usage |
|---------|-------|
| S3 (`visualization-poc-bucket`) | Ontology files, financial/product data, scheduled reports, execution history |
| Bedrock (Claude Haiku `us.anthropic.claude-haiku-4-5-20251001-v1:0`) | NLP query classification, visualization agent, follow-up LLM, guardrail output check |
| Bedrock Guardrails (ID: `unf4323uxnff`) | Input/output content policy enforcement |
| Bedrock Titan Embed (`amazon.titan-embed-text-v2:0`) | Query history similarity (cosine matching at 0.85 threshold) |
| Redshift Data API (`talktodata` cluster, `analytics` DB) | workforce/support/marketing data |
| EventBridge Scheduler | Cron-based scheduled report triggering (optional, falls back to APScheduler) |

AWS credentials: uses `boto3.Session(profile_name="PowerUserAccess-654654478821")` locally. In ECS, uses task role (detected via `ECS_CONTAINER_METADATA_URI` env var). SSL verification disabled for corporate proxy environments.

---

## Cancellation Flow

1. Frontend calls `POST /cancel` with `correlation_id`.
2. NLP API registers cancellation in `_cancellation_registry` (TTL 300s).
3. Background task propagates to `POST {ORCHESTRATOR_URL}/internal/cancel`.
4. Orchestrator registers in its own `CancellationRegistry`.
5. Orchestrator checks registry before each agent dispatch iteration.
6. Each spoke agent checks `request.is_disconnected()` before expensive I/O (S3 fetch or Redshift query).
7. Client disconnect (not just explicit cancel) is also detected: `_monitor_client_disconnect` polls `request.is_disconnected()` every 250ms while the orchestrator request is in flight.

---

## Key Data Flow Diagram

```
User Query
    │
    ▼
NLP API (8001)
  ├─ MetaQueryDetector → text response (no pipeline)
  ├─ Bedrock Guardrail (INPUT) ──────────┐
  ├─ NLPTranslator.translate()           │ parallel
  │    ├─ OntologyStore.search_concepts()│
  │    ├─ BedrockClassifier (Haiku)      │
  │    └─ column/viz hint extraction     │
  └──────────────────────────────────────┘
    │
    ▼ StructuredIntent
Orchestrator Hub (8002)
  ├─ ResultCache (hit → skip agents)
  ├─ resolve agents by entity_refs
  └─ dispatch
       ├─ Single-domain → direct HTTP to spoke agent
       └─ Multi-domain comparison → Strands Agent (Haiku) calls dispatch tool
              │
              ▼ HTTP POST /agents/{id}/invoke
         Spoke Agent (8010) or Redshift Agent (8011) or MCP Adapter (8012)
              │
              ▼ AgentResult {payload: {columns, rows, ...}}
    │
    ▼ OrchestratorResponse
Guardrail Layer (8003)
  ├─ Schema validation
  └─ Bedrock Guardrail (OUTPUT)
    │
    ▼ GuardrailResult {status: passed}
Visualization Renderer (8004)
  ├─ Normalize payload → columns + rows
  ├─ Strands Agent (Haiku) calls emit_chart(chart_config, title, description)
  └─ Returns RenderedOutput {chart_data: Chart.js config, description: insight}
    │
    ▼ RenderedOutput
NLP API → HTTP 200 → Browser
```

---

## Configuration (`src/config.py`)

All ports, AWS config, model IDs, and S3 keys defined here. Key values:

- `DEFAULT_MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"`
- `S3_BUCKET = "visualization-poc-bucket"` (override via `S3_BUCKET` env)
- `AWS_PROFILE = "PowerUserAccess-654654478821"` (override via `AWS_PROFILE` env)
- `AGENT_TIMEOUT_DEFAULT = 30` seconds
- `SIMILARITY_THRESHOLD = 0.85` (cosine similarity for query history)

---

## Observability

`observability_decorator` wraps FastAPI endpoints, logs structured JSON with `service_name`, `operation`, `correlation_id`, `latency_ms`, and status. Correlation ID (`X-Correlation-ID` header) is generated at the NLP API entry point and propagated downstream via `propagation_headers()`.

Logging config (`logging_config.py`) uses `configure_logging()` called at the top of every service module.

---

## Feature Flags (MCP Routing)

| Env Var | Effect |
|---------|--------|
| `USE_MCP_ADAPTER=true` | Registers both MCP adapter agents |
| `USE_MCP_REDSHIFT=true` | Registers `mcp-redshift-adapter` (port 8012) |
| `USE_MCP_S3=true` | Registers `mcp-s3-adapter` (port 8012) |

When enabled, `register_agents.py` registers MCP adapter agents alongside (not replacing) the legacy agents. `FeatureFlagRouter` in the orchestrator hub determines which endpoint URL to use when dispatching.

When MCP server is unavailable, `FallbackHandler` transparently falls back to legacy spoke agents via HTTP.
