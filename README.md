# Conversational BI System

A full-stack platform that turns natural-language business questions ("show me quarterly sales revenue by region") into interactive Chart.js visualizations with generated analytical insight. The backend is a hub-and-spoke microservices architecture built on FastAPI: a natural-language layer resolves the question against a domain ontology and classifies its data-source targets, an orchestrator dispatches the resolved intent to one or more "spoke" data agents (S3/JSON/CSV, Redshift, or MCP-protocol servers), and a guardrail-checked, LLM-driven rendering stage converts the raw result set into a chart configuration. A separate scheduling subsystem lets users persist a query and have it re-run and re-delivered on a cron-like schedule via AWS Step Functions/EventBridge in production, or a local always-on scheduler in dev.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![React 19](https://img.shields.io/badge/react-19-61dafb)
![FastAPI](https://img.shields.io/badge/fastapi-0.115%2B-009688)
![Amazon Bedrock](https://img.shields.io/badge/AWS-Bedrock-FF9900)

---

## Features

- **Natural-language querying** — ask business questions in plain English, get structured intent via ontology-based entity resolution + Bedrock (Claude Haiku 4.5) query-type classification, with a heuristic fallback if the LLM call fails or is skipped.
- **Multi-source data access** — a single query can be dispatched to flat-file data (S3/JSON/CSV), a Redshift warehouse (via generated, parameterized SQL against the Redshift Data API), or external MCP servers, selected per-domain and per-environment via feature flags.
- **Multi-domain comparison queries** — when a question spans more than one business domain, a Strands-based agent coordinates dispatch across multiple spoke agents and merges results, instead of a single direct call.
- **LLM-generated visualizations with deterministic fallback** — chart type/config is produced by an agent (`emit_chart` tool call, retried up to 3x); if generation fails or times out, a deterministic chart-type decision tree still produces a usable chart.
- **Guardrails on input and output** — Bedrock Guardrails screen the raw user query and the final response; a schema check runs before rendering.
- **Result and query-history caching** — exact-match result cache plus embedding-similarity (Titan Embed v2, cosine ≥ 0.85) lookup against prior queries to short-circuit repeated work.
- **Scheduled reports** — persist a resolved query and re-run it on a schedule; replays the stored intent through the same pipeline with a cache-skip header so results stay fresh.
- **Query cancellation** — client-disconnect is polled and propagated across the multi-hop pipeline so abandoned queries don't run to completion.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│           FRONTEND — React + TypeScript + Chart.js               │
│      Chat UI → natural language query → interactive viz grid     │
└───────────────────────────────┬──────────────────────────────────┘
                                 │ POST /query
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  NLP API (8001)                                                   │
│    Bedrock Guardrail (INPUT)  +  NLPTranslator                    │
│    ontology entity resolution → Bedrock query-type classification │
│    (LRU cached, heuristic fallback)         → StructuredIntent    │
└───────────────────────────────┬──────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  Orchestrator Hub (8002)                                          │
│    ResultCache lookup → resolve spoke agent(s) by entity_refs     │
│    single domain → direct dispatch                                │
│    multi domain  → Strands agent coordinates parallel dispatch    │
└───────┬───────────────────┬───────────────────┬──────────────────┘
        ▼                   ▼                   ▼
┌───────────────┐  ┌──────────────────┐  ┌────────────────────────┐
│ Spoke Agent    │  │ Redshift Spoke   │  │ MCP Adapter (8012)     │
│ (8010)         │  │ Agent (8011)     │  │ → external MCP servers │
│ S3/JSON/CSV    │  │ SQLGenerator →   │  │   Redshift (7010)      │
│ deterministic  │  │ Redshift Data API│  │   S3       (7020)      │
└───────┬────────┘  └────────┬─────────┘  └───────────┬────────────┘
        └────────────────────┴────────────────────────┘
                                 ▼  OrchestratorResponse
┌─────────────────────────────────────────────────────────────────┐
│  Guardrail Layer (8003) — schema check + Bedrock Guardrail OUTPUT │
└───────────────────────────────┬──────────────────────────────────┘
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  Visualization Renderer (8004)                                    │
│    Strands agent emits Chart.js config (emit_chart, 3 retries)    │
│    falls back to deterministic chart-type decision tree           │
└───────────────────────────────┬──────────────────────────────────┘
                                 ▼  RenderedOutput → frontend

┌─────────────────────────────────────────────────────────────────┐
│  Scheduling API (8005) — parallel subsystem                       │
│    CRUD for scheduled reports (S3-backed)                         │
│    dev:  APScheduler (always-on, local)                           │
│    prod: EventBridge Scheduler + Step Functions                   │
│    replays stored StructuredIntent through pipeline above         │
└─────────────────────────────────────────────────────────────────┘
```

## Tech Stack

**Backend** — Python 3.11+/3.12, FastAPI, Pydantic v2, httpx (async), boto3, Strands SDK (agent/tool-calling), MCP SDK, APScheduler.

**LLM / AI** — Amazon Bedrock, Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`), Bedrock Guardrails, Bedrock Titan Embed v2.

**Data** — Amazon S3 (ontology, source data, scheduled reports), Amazon Redshift (Data API).

**Frontend** — React 19, TypeScript, Vite, Zustand + immer, Tailwind CSS, Chart.js v4 / react-chartjs-2, react-dnd.

**Testing** — Hypothesis (property-based), pytest, Vitest.

**Infrastructure** — Docker (3 isolated venvs per container), AWS App Runner, CloudFront, Step Functions, EventBridge Scheduler, CodeBuild buildspecs.

## Installation

```bash
# Backend
pip install -e ".[dev]"
aws sso login --profile <your-profile>

# Frontend
cd frontend
npm install
```

The `mcps/` directory is a git submodule — pull it with `git submodule update --init --recursive` if you plan to run the MCP servers locally.

## Configuration

Central backend config lives in `src/config.py`, driven by environment variables:

| Variable | Purpose |
|---|---|
| `AWS_REGION` | AWS region for Bedrock/S3/Redshift calls |
| `AWS_PROFILE` | Local credentials profile (default `PowerUserAccess-654654478821`) |
| `S3_BUCKET` | Bucket for ontology, source data, scheduled reports (default `visualization-poc-bucket`) |
| `BEDROCK_MODEL_ID` | Bedrock model for classification/generation |
| `GUARDRAIL_ID` | Bedrock Guardrail identifier |
| `USE_AGENTCORE_VIZ` | Toggle AgentCore-based visualization path |
| `USE_MCP_ADAPTER` / `USE_MCP_REDSHIFT` / `USE_MCP_S3` | Route data access through MCP servers instead of legacy spoke agents, with automatic fallback |
| `STEP_FUNCTIONS_STATE_MACHINE_ARN` | Prod scheduler execution target |
| `EVENTBRIDGE_SCHEDULER_ROLE_ARN` | IAM role EventBridge assumes to trigger schedules |

Frontend configuration is in `frontend/.env` / `.env.development` / `.env.production`.

## Running locally

```bash
# start all backend services (spawns uvicorn subprocesses, health-checks, registers demo agents)
python run_all.py

# or, with MCP servers included
bash run_all_with_mcp.sh

# frontend, separate terminal
cd frontend && npm run dev   # http://localhost:5173
```

Production runs all services inside a single container via `run_all_with_mcp_prod.py` (App Runner).

## Example usage

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query_text": "show me quarterly sales revenue by region"}'
```

Returns a Chart.js configuration, a generated analytical insight, and a per-stage latency breakdown.

Manual smoke test for the scheduling CRUD API: `./test_scheduled_reports_api.sh`.

## Project Structure

```
src/
  services/     5 FastAPI microservices — nlp, orchestrator, guardrail,
                visualization, scheduling — plus supporting logic:
                ontology_store, ontology_validator, sql_generator,
                result_cache, cache_layer, query_history_store,
                scheduled_reports_repository, local_scheduler,
                scheduler_manager, feature_flag_router,
                cancellation_registry
  agents/       spoke_agent.py (S3/JSON/CSV), redshift_spoke_agent.py,
                mcp_adapter/ (routes to external MCP servers)
  models/       Pydantic models shared across services — StructuredIntent,
                AgentResult, OrchestratorResponse, RenderedOutput, ontology types

frontend/src/
  api/          backend client
  components/   ChatThread, ChartRenderer, VisualizationCard, ...
  store/        Zustand sessionStore
  types/        shared TS types
  utils/
  assets/       hero.png

tests/
  properties/   Hypothesis property-based tests (9 files)
  unit/         5 files
  integration/  2 files

data/           local fallback ontology + source data mirroring the S3
                layout, guardrail_rules.json — lets the stack run offline

docs/           9 architecture/deployment docs (system-architecture,
                END_TO_END_ARCH, AGENTCORE_DEPLOYMENT, RUNNING_GUIDE, ...)

infrastructure/ Step Functions state-machine definitions (ASL JSON, full
                + simplified), lambda-functions/, deployment guides

deploy/         3-stage Dockerfile (3 isolated venvs), buildspec-backend.yaml,
                buildspec-frontend.yaml, App Runner/CloudFront scripts

scripts/        setup_s3.py, provision_redshift.py, deploy_step_functions.py,
                deploy_and_configure.sh

mcps/           git submodule — external MCP Redshift/S3 server
                implementations, each with its own venv

.kiro/specs/    8 spec-driven-development folders (agent-multi-source-
                retrieval, scheduled-reports, redshift-data-source-
                integration, mcp-data-access-integration, query-
                cancellation, ontology-routing-fix, ...) — history of
                spec-first feature development
```

## Design Decisions

**Hub-and-spoke over a monolith.** Each data source (flat files, Redshift, MCP servers) is a separately deployable "spoke" behind a uniform `AgentResult` contract. Adding a new data source means writing one new agent and registering it — the orchestrator, guardrails, and renderer are untouched.

**LLM stages always have a deterministic fallback.** Query classification and chart generation both call an LLM but never depend on it succeeding: a heuristic classifier and a chart-type decision tree guarantee the pipeline still returns a usable result under model latency, timeout, or malformed output. This trades a small amount of quality on the fallback path for 100% availability of the core feature.

**Feature-flagged dual data-access paths (legacy spoke vs. MCP).** MCP support was added without a hard cutover — `USE_MCP_*` flags route per-domain, with automatic fallback to the legacy spoke agent if the MCP server is unreachable. This let MCP integration ship incrementally and be rolled back per-domain without a deploy.

**Guardrails at both the input and output boundary**, not just on the user-facing prompt, so a validated user query can't still produce a policy-violating or malformed response after passing through the LLM-driven rendering stage.

**Dual scheduler implementation (APScheduler locally, EventBridge + Step Functions in prod).** Local dev doesn't need — and shouldn't require — AWS IAM/state-machine setup just to iterate on scheduled reports; production needs durability and horizontal scaling APScheduler-in-a-process can't give. Both implement the same interface, so the rest of the system is unaware of which one is active.

**Three isolated virtualenvs in one deploy container.** boto3/aiobotocore pull in mutually incompatible transitive dependency versions across the main app and the two MCP servers; rather than pin around it, each runs in its own venv inside the same image.

## Challenges

- **Correlation-ID propagation and cancellation across a multi-hop pipeline.** A query can traverse 4–5 services before rendering; client disconnects are polled (every 250ms) and the cancellation has to cascade through every hop so an abandoned request doesn't keep consuming Bedrock/Redshift capacity downstream.
- **Keeping LLM-in-the-loop stages non-blocking for correctness.** Classification and chart rendering both use an LLM in a system that has to return *something* correct-shaped even when the model call fails, times out, or hallucinates an invalid tool call — required building and maintaining parallel deterministic logic for both.
- **Incremental protocol migration.** Introducing MCP as a second data-access protocol alongside the original spoke-agent pattern without breaking existing domains meant building the feature-flag/fallback layer rather than a flag-day cutover.
- **Dependency isolation in a single deployable.** Diagnosing and resolving the boto3/aiobotocore conflicts between the main app and MCP servers, ultimately solved with per-service venvs rather than dependency pinning gymnastics.
- **Result correctness under caching and multi-source dispatch.** Exact-match caching, embedding-similarity history lookups, and multi-domain result merging all had to be verified not to silently return stale or mismatched data — covered largely by the Hypothesis property-based test suite.

## Future Improvements

- Replace LRU/embedding-similarity caching with a shared cache service so multiple orchestrator instances don't duplicate cache state.
- Expand the ontology to support cross-domain joins natively instead of only orchestrator-level result merging.
- Add streaming responses for long-running Redshift queries instead of poll-based Data API waiting.
- Broaden Hypothesis property coverage to the orchestrator's multi-agent merge logic.
- Formalize the MCP adapter as the default data-access path once parity with legacy spoke agents is fully validated in prod.

## Screenshots

_No UI screenshots checked into the repo yet — only `frontend/src/assets/hero.png` exists as an image asset. Add screenshots of the chat UI and a rendered visualization here._

| | |
|---|---|
| _Chat UI — placeholder_ | _Rendered chart — placeholder_ |

## Resume Bullet Points

- Designed and built a hub-and-spoke microservices backend (5 FastAPI services) that resolves natural-language queries into structured intents and dispatches them across heterogeneous data sources (S3, Redshift, MCP protocol servers), with feature-flagged routing and automatic fallback enabling zero-downtime rollout of a new data-access protocol.
- Engineered LLM-in-the-loop pipeline stages (query classification, chart generation via Amazon Bedrock) each backed by a deterministic fallback path, guaranteeing 100% response availability independent of model latency or failure, validated with a Hypothesis property-based test suite.
- Implemented a dual-mode scheduling subsystem (local APScheduler / AWS Step Functions + EventBridge in production) behind a shared interface, plus cross-service correlation-ID propagation and cancellation, to support reliable scheduled report delivery and responsive query cancellation across a multi-hop distributed pipeline.
