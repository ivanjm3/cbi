# Conversational BI System - Project Summary

## Executive Overview

This is a **Conversational Business Intelligence (BI) platform** that transforms natural language questions into interactive data visualizations. Users ask questions like *"show me quarterly sales revenue by region"* and receive instant Chart.js visualizations powered by Amazon Bedrock (Claude 3.5 Haiku) and a sophisticated hub-and-spoke microservices backend.

The system combines **ontology-driven entity resolution**, **multi-layer caching** for cost efficiency, **content safety guardrails**, and **deterministic fallbacks** to ensure reliable, traceable query processing from natural language to visualization.

---

## Key Features

✅ **Natural Language to Chart** — Plain English queries → Interactive visualizations  
✅ **Intelligent Chart Selection** — LLM-driven type reasoning with 10-level decision tree fallback  
✅ **4-Layer Caching** — NLP classification, orchestration, guardrails, rendering caches minimize cost & latency  
✅ **Content Safety** — Amazon Bedrock Guardrails on input/output with fail-open resilience  
✅ **Deterministic Fallbacks** — Every LLM stage has heuristic backup ensuring 100% resolution  
✅ **Ontology-Driven Routing** — Domain concepts drive accurate entity resolution  
✅ **Cooperative Cancellation** — Mid-flight query cancellation prevents resource waste  
✅ **MCP Integration** — Model Context Protocol support for unified data access via mcp-redshift & mcp-s3 servers  
✅ **Property-Based Testing** — Hypothesis-based correctness validation  
✅ **Cost Tracking** — Per-invocation Bedrock costs logged for observability  

---

## System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND (React 19 + TypeScript)                        │
│                                                                                  │
│  ┌────────────┐  ┌────────────┐  ┌───────────────┐  ┌────────────────────────┐   │
│  │ ChatInput  │→ │ queryApi   │→ │ sessionStore  │→ │ ChartRenderer / Cards  │   │
│  │ ChatBar    │  │ (fetch)    │  │ (Zustand +    │  │ VisualizationCard      │   │
│  └────────────┘  └────────────┘  │  localStorage)│  │ StatsPanel             │   │
│                                   └───────────────┘ │ TraceabilityPanel      │   │
│                                                     └────────────────────────┘   │
│                                                                                  │
│  Layout: Sidebar │ ChatThread + ChatInput │ StatsPanel │ TraceabilityPanel       │
└──────────────────────────────────┬───────────────────────────────────────────────┘
                                   │
                                   │ POST /query         (natural language)
                                   │ POST /cancel        (cooperative cancellation)
                                   │ POST /query/follow-up (conversational)
                                   │ POST /api/re-render (chart type conversion)
                                   │ GET  /sessions/:id  (session restore)
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    BACKEND — 7 FastAPI Microservices (Single Container)          │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  NLP Translator (port 8001) — SYSTEM ENTRY POINT                           │  │
│  │  • Natural language → StructuredIntent                                     │  │
│  │  • Input guardrail (Bedrock Guardrails, parallel)                          │  │
│  │  • Entity resolution against Ontology Store (S3)                           │  │
│  │  • Query type classification (LLM + heuristic fallback)                    │  │
│  │  • Visualization hint extraction (regex)                                   │  │
│  │  • Full pipeline orchestration: NLP → Orchestrator → Guardrail → Renderer  │  │
│  │  • Cooperative cancellation via CancellationRegistry                       │  │
│  └──────────────────────────────┬─────────────────────────────────────────────┘  │
│                                 │ HTTP POST (StructuredIntent)               │
│                                 ▼                                            │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  Orchestrator Hub (port 8002) — ROUTING ENGINE                             │  │
│  │  • Deterministic entity_ref → agent resolution (no LLM in hot path)        │  │
│  │  • Result cache (SHA-256 hash of intent)                                   │  │
│  │  • Concurrent agent dispatch via thread pool                               │  │
│  │  • Supports DIRECT (single) + AGENTIC (multi-agent) dispatch modes         │  │
│  │  • Feature-flag routing: legacy agents vs MCP Adapter                      │  │
│  └────────┬──────────────────────┬─────────────────────────┬──────────────────┘  │
│           │                      │                         │                     │
│           ▼                      ▼                         ▼                     │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐     │
│  │ Spoke Agent     │  │ Redshift Spoke   │  │ MCP Adapter Layer            │     │
│  │ (port 8010)     │  │ (port 8011)      │  │ (port 8012)                  │     │
│  │                 │  │                  │  │                              │     │
│  │ • S3 JSON/CSV   │  │ • SQL generation │  │ • Bridges Orchestrator ↔     │     │
│  │ • Deterministic │  │   via LLM        │  │   MCP servers                │     │
│  │   (no LLM)      │  │ • Redshift Data  │  │ • Feature-flag controlled    │     │
│  │ • Lookup /      │  │   API execution  │  │ • Auto-fallback to legacy    │     │
│  │   Aggregate /   │  │ • Parameterized  │  │   agents on MCP failure      │     │
│  │   Compare       │  │   queries        │  │ • Cancellation-aware         │     │
│  └─────────────────┘  └──────────────────┘  └───────────────┬──────────────┘     │
│                                                             │                    │
│                              MCP Protocol (streamable-http)      │
│                                                             │                    │
│                              ┌───────────────────────────────┼────────────────┐  │
│                              │           MCP SERVER LAYER    │                │  │
│                              │                               │                │  │
│                              │  ┌────────────────┐  ┌────────▼───────────┐    │  │
│                              │  │ mcp-redshift   │  │ mcp-s3             │    │  │
│                              │  │ (port 7010)    │  │ (port 7020)        │    │  │
│                              │  │                │  │                    │    │  │
│                              │  │ Tools:         │  │ Tools:             │    │  │
│                              │  │ • list_schemas │  │ • list_datasets    │    │  │
│                              │  │ • list_tables  │  │ • describe_dataset │    │  │
│                              │  │ • describe_tbl │  │ • get_schema       │    │  │
│                              │  │ • execute_query│  │ • sample_dataset   │    │  │
│                              │  │ • explain_query│  │ • read_dataset     │    │  │
│                              │  │ • get_stats    │  │ • read_partition   │    │  │
│                              │  │ • get_rels     │  │ • get_statistics   │    │  │
│                              │  │ • get_semantic │  │ • get_semantic     │    │  │
│                              │  └────────┬───────┘  └─────────┬──────────┘    │  │
│                              │           │                    │               │  │
│                              └───────────┼────────────────────┼───────────────┘  │
│                                          │                    │                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  Guardrail Layer (port 8003) — CONTENT SAFETY                              │  │
│  │  • Schema validation (structural correctness)                              │  │
│  │  • Amazon Bedrock Guardrails (hate, violence, PII, misconduct)             │  │
│  │  • Output cache (SHA-256 of serialized response)                           │  │
│  │  • Fail-open policy: content passes if Bedrock is unreachable              │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │  Visualization Renderer (port 8004) — CHART GENERATION                     │  │
│  │  • Strands Agent generates Chart.js config via LLM tool-calling            │  │
│  │  • 10-level decision tree for chart type selection                         │  │
│  │  • Deterministic fallback (builds chart config without LLM)                │  │
│  │  • 3 retries with error feedback on LLM failure                            │  │
│  │  • Render cache for repeated identical data                                │  │
│  └────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AWS SERVICES                                       │
│                                                                                 │
│  ┌──────────────────┐  ┌──────────────┐  ┌──────────────────┐  ┌─────────────┐  │
│  │ Amazon Bedrock   │  │ Amazon S3    │  │ Bedrock          │  │ Amazon      │  │
│  │                  │  │              │  │ Guardrails       │  │ Redshift    │  │
│  │ • Claude 3.5     │  │ • Ontology   │  │                  │  │             │  │
│  │   Haiku (NLP +   │  │ • Data files │  │ • Input filter   │  │ • Data API  │  │
│  │   visualization) │  │ • Cost logs  │  │ • Output filter  │  │ • SQL exec  │  │
│  │ • Titan Embed V2 │  │ • History    │  │ • PII detection  │  │ • No VPC    │  │
│  │   (embeddings)   │  │ • Sessions   │  │                  │  │   required  │  │
│  └──────────────────┘  └──────────────┘  └──────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## End-to-End Query Lifecycle

### Happy Path Flow

```
User Query: "show me quarterly sales revenue by region"
    ↓
[1] INPUT GUARDRAIL (parallel)
    → Bedrock Guardrails checks for harmful content
    → Fail-open if Bedrock unreachable
    ↓
[2] NLP TRANSLATION (port 8001)
    a. Extract keywords: "quarterly", "sales", "revenue"
    b. Ontology lookup → ontology:sales_revenue, ontology:quarterly_report
    c. Specificity validation
    d. Query type classification (LRU cache) → "aggregation"
    e. Visualization hint extraction
    → Produces StructuredIntent with entity_refs
    ↓
[3] ORCHESTRATOR HUB (port 8002)
    a. Result cache check (SHA-256 hash) → MISS
    b. Resolve agents from entity_refs overlap
    → Spoke Agent (8010) handles financial entities
    c. DIRECT dispatch (single-agent query)
    ↓
[4] DATA RETRIEVAL
    
    Legacy Path (Spoke Agent 8010):
    • Routes to financial_data.json in S3
    • Performs aggregation: sum/avg/min/max
    • Groups by "region"
    • Returns AgentResult with tabular data
    
    OR
    
    MCP Path (MCP Adapter 8012 → mcp-s3):
    • IntentRouter resolves dataset
    • S3Translator builds MCP tool call
    • Calls mcp-s3 server (port 7020)
    • ResponseTransformer → AgentResult
    • Fallback to legacy on MCP failure
    ↓
[5] GUARDRAIL LAYER (port 8003)
    a. Schema validation
    b. Output cache check → MISS
    c. Bedrock Guardrails content filtering
    d. Returns "passed" or rejects with 422
    ↓
[6] VISUALIZATION RENDERER (port 8004)
    a. Render cache check → MISS
    b. Chart type decision tree (10 levels)
       → Analyzes data shape, cardinality
       → Selects optimal chart type (doughnut for this case)
    c. Strands Agent generates Chart.js config
    d. 3 retries with error feedback
    e. Deterministic fallback if LLM fails
    ↓
[7] RESPONSE TO FRONTEND
    • Chart.js configuration
    • Raw data (columns + rows)
    • Metadata (latency, entity resolution path)
    • Analytical insights
    ↓
[8] FRONTEND RENDERS
    • Chart.js canvas with tooltips
    • StatsPanel shows latency breakdown
    • TraceabilityPanel shows full routing path
    • Session auto-saved to localStorage
```

### Latency Profile

| Scenario | Total Latency | Breakdown |
|----------|--------------|-----------|
| **Cold (all caches empty)** | 30-40s | NLP classification 4-6s, Agent dispatch 1-2s, Guardrail 2-3s, Visualization 20-30s |
| **Warm (all caches hit)** | <1s | Cache lookups only |
| **Partial warm** | 5-10s | Mix of cache hits; typically viz rendering is bottleneck |

---

## Technology Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | React 19, TypeScript 6, Vite 8, Zustand (state), Chart.js 4 / Recharts, react-dnd, Tailwind CSS 4 |
| **Backend** | Python 3.11+, FastAPI 0.115+, Pydantic v2, uvicorn, httpx (async HTTP) |
| **AI / LLM** | Amazon Bedrock — Claude 3.5 Haiku (NLP + chart generation), Titan Embeddings V2 |
| **Agent Framework** | Strands SDK (tool-calling AI agents) |
| **MCP Layer** | MCP SDK 1.0+, custom servers (mcp-redshift, mcp-s3) |
| **Content Safety** | Amazon Bedrock Guardrails (input + output filtering) |
| **Storage** | Amazon S3 (ontology, data sources, logs, history) |
| **Data Warehouse** | Amazon Redshift (Data API, no VPC connectivity) |
| **Testing** | pytest, Hypothesis (property-based), pytest-asyncio |
| **Deployment** | Docker (multi-stage), AWS App Runner, CloudFront |

---

## Service Inventory

| Service | Port | LLM? | Role |
|---------|------|------|------|
| NLP Translator | 8001 | Yes | Entry point, pipeline orchestrator |
| Orchestrator Hub | 8002 | No | Routes intents to agents deterministically |
| Guardrail Layer | 8003 | Yes | Content safety (schema + Bedrock Guardrails) |
| Visualization Renderer | 8004 | Yes | Chart.js config generation + fallback |
| Spoke Agent (S3) | 8010 | No | Deterministic S3 JSON/CSV retrieval |
| Redshift Spoke Agent | 8011 | Yes | SQL generation + Redshift Data API execution |
| MCP Adapter | 8012 | No | Bridges to MCP servers, fallback handler |
| MCP Redshift Server | 7010 | No | MCP-compliant Redshift data access |
| MCP S3 Server | 7020 | No | MCP-compliant S3 dataset access |

---

## MCP Integration

The system supports optional Model Context Protocol (MCP) data access via feature flags:

- **USE_MCP_ADAPTER** — Global toggle for MCP routing
- **USE_MCP_REDSHIFT** — Route Redshift queries via mcp-redshift server
- **USE_MCP_S3** — Route S3 queries via mcp-s3 server

**MCP Servers** (in git submodule `./mcps`):
- **mcp-redshift** — Provides tools for schema exploration, SQL execution, statistics
- **mcp-s3** — Provides tools for dataset discovery, schema, sampling, reading

**Resilience**: On MCP server unavailability, FallbackHandler automatically routes to legacy agents (8010/8011).

---

## Project Structure

```
├── frontend/                     # React + TypeScript UI
│   ├── src/
│   │   ├── api/                 # queryApi.ts - HTTP client
│   │   ├── components/          # UI components (ChatThread, ChartRenderer, etc.)
│   │   ├── store/               # Zustand state management
│   │   ├── types/               # TypeScript interfaces
│   │   └── utils/               # Helpers
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── package.json
│
├── src/                          # Python backend
│   ├── config.py                 # Central configuration
│   ├── models/
│   │   ├── shared.py            # Core Pydantic models
│   │   ├── ontology.py          # Ontology schema
│   │   └── redshift_models.py   # Redshift types
│   │
│   ├── agents/
│   │   ├── spoke_agent.py       # S3 data retrieval (port 8010)
│   │   ├── redshift_spoke_agent.py # Redshift SQL execution (port 8011)
│   │   └── mcp_adapter/         # MCP integration layer (port 8012)
│   │       ├── config.py        # MCP configuration
│   │       ├── client_manager.py # MCP client lifecycle
│   │       ├── intent_router.py # Entity-ref routing
│   │       ├── redshift_translator.py
│   │       ├── s3_translator.py
│   │       ├── response_transformer.py
│   │       ├── fallback_handler.py
│   │       ├── models.py
│   │       └── service.py       # FastAPI app
│   │
│   └── services/
│       ├── nlp_api.py           # NLP entry point (port 8001)
│       ├── nlp_translator.py    # NLP logic
│       ├── orchestrator_api.py  # Orchestrator endpoint (port 8002)
│       ├── orchestrator_hub.py  # Routing logic
│       ├── guardrail_api.py     # Guardrail endpoint (port 8003)
│       ├── guardrail_layer.py   # Content safety logic
│       ├── visualization_api.py # Viz endpoint (port 8004)
│       ├── visualization_renderer.py # Chart generation
│       ├── ontology_store.py    # S3-backed ontology
│       ├── bedrock_wrapper.py   # Bedrock client
│       ├── result_cache.py      # Intent hash cache
│       ├── lru_cache.py         # LRU cache utility
│       ├── cost_tracker.py      # Bedrock cost logging
│       ├── cancellation_registry.py # Query cancellation tracking
│       ├── feature_flag_router.py # MCP routing decisions
│       ├── meta_query_detector.py # System question detection
│       ├── text_only_detector.py # Text response detection
│       ├── follow_up_handler.py  # Conversational follow-ups
│       ├── sql_generator.py      # SQL from intents
│       ├── redshift_connector.py # Redshift Data API
│       ├── schema_registry.py    # Ontology → schema mapping
│       └── [+10 more utilities]
│
├── data/
│   ├── ontology/
│   │   └── enterprise_ontology.json  # Domain knowledge graph
│   └── sources/
│       ├── financial_data.json       # Revenue, orders, returns
│       └── product_catalog.csv       # Products, inventory
│
├── tests/
│   ├── unit/                    # pytest unit tests
│   └── properties/              # Hypothesis property-based tests
│
├── docs/
│   ├── END_TO_END_ARCH.md       # Complete architecture ref
│   ├── SYSTEM_OVERVIEW.md       # System overview
│   └── [+5 more guides]
│
├── deploy/
│   ├── Dockerfile              # Multi-stage build
│   ├── deploy.sh               # Deployment orchestration
│   ├── create-apprunner.sh
│   ├── buildspec-*.yaml
│   └── README.md
│
├── scripts/
│   ├── setup_s3.py             # Upload data to S3
│   ├── provision_redshift.py   # Setup Redshift tables
│   └── cost_report.py          # Cost analysis
│
├── run_all.py                  # Starts all 7 services
├── pyproject.toml              # Python config
├── README.md                   # Project README
└── SUMMARY.md                  # This file
```

---

## Ontology (Knowledge Graph)

The enterprise ontology defines 13+ business concepts across domains:

| Domain | Concepts | Data Source | Agent |
|--------|----------|-------------|-------|
| Finance | sales_revenue, order_volume, return_rate, quarterly_report | S3 (financial_data.json) | Spoke (8010) |
| Inventory | product_catalog, inventory_stock, product_pricing | S3 (product_catalog.csv) | Spoke (8010) |
| HR | workforce_metrics | Redshift | Redshift Spoke (8011) |
| Support | support_tickets | Redshift | Redshift Spoke (8011) |
| Marketing | marketing_campaigns | Redshift | Redshift Spoke (8011) |
| Shared | region, product_category, office_location, department | Reference | — |

Each concept includes:
- `concept_id` — Namespaced identifier (e.g., `ontology:sales_revenue`)
- `properties` — Domain, data_source, agent_id, table_name, columns
- `relationships` — Edges to other concepts (contributes_to, contains, grouped_by)

---

## Caching Strategy (4-Layer)

The system minimizes cost and latency via:

1. **NLP Classification Cache** (LRU, 1000 entries) — Query type classification (LLM) cached per query text
2. **Result Cache** (orchestrator) — SHA-256 hash of intent → orchestrator response
3. **Guardrail Cache** — SHA-256 hash of content → pass/reject decision
4. **Render Cache** — Same payload + query → same chart config

**Impact**: Cold → 30-40s, Warm → <1s latency

---

## Key Design Principles

1. **Microservices via Processes** — 7 independent FastAPI services communicate via HTTP
2. **LLM + Deterministic Hybrid** — LLM for intelligence, heuristics for resilience
3. **Ontology-Driven Routing** — No hardcoded rules; domain concepts drive routing
4. **Fail-Open Safety** — Bedrock Guardrails protect; system stays available if Bedrock down
5. **Complete Observability** — Structured JSON logging, correlation IDs, cost tracking per invocation
6. **Cooperative Cancellation** — Users cancel queries mid-flight without resource waste
7. **Property-Based Testing** — Hypothesis validates system invariants

---

## Getting Started

### Backend
```bash
pip install -e ".[dev]"
aws sso login --profile PowerUserAccess-654654478821
python run_all.py
```
Starts all 7 services on ports 8001-8004 + 7010/7020 (MCP servers).

### Frontend
```bash
cd frontend
npm install
npm run dev
```
React dev server at `http://localhost:5173`.

### Docker (Production-like)
```bash
docker build -f deploy/Dockerfile -t conversational-bi .
docker run -p 8001:8001 conversational-bi
```

---

## Deployment Options

1. **Self-Hosted** — All services on localhost via `run_all.py` or Docker
2. **AWS Production** — Container on App Runner (auto-scales), CloudFront CDN, S3/Bedrock/Redshift

See `deploy/README.md` for full deployment guide.

---

## Testing

```bash
pytest                              # All tests
pytest tests/unit/                  # Unit tests only
pytest tests/properties/            # Property-based tests
cd frontend && npm test             # Frontend tests
```

Property-based tests validate:
- Ontology serialization roundtrips
- StructuredIntent schema conformance
- Chart type selection validity
- Guardrail data integrity

---

## Contact & Documentation

- **Architecture Details** — See `docs/END_TO_END_ARCH.md` (1000+ lines)
- **System Overview** — See `docs/SYSTEM_OVERVIEW.md` (690+ lines)
- **Deployment Guide** — See `deploy/README.md`
- **Cost Tracking** — See `docs/COST_TRACKING.md`