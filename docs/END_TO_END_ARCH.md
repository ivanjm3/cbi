# Conversational BI System — End-to-End Architecture

> Complete architectural reference covering system design, service topology, data flows, MCP integration, deployment infrastructure, and operational patterns.

---

## 1. Executive Summary

The Conversational BI System is an ontology-based, NLP-driven query platform that transforms natural language business questions into interactive Chart.js visualizations. It uses a **hub-and-spoke microservices architecture** with 7 backend services communicating over HTTP, an AI inference layer powered by Amazon Bedrock (Claude Haiku 4.5), and a React/TypeScript frontend delivering a multi-panel conversational canvas.

The system features a **Model Context Protocol (MCP) integration layer** that provides standardized, tool-calling access to data sources (Amazon Redshift and S3), with automatic fallback to legacy deterministic agents when MCP servers are unavailable.

---

## 2. Technology Stack

| Layer | Technologies |
|-------|-------------|
| **Frontend** | React 19, TypeScript 6, Vite 8, Zustand (state), Chart.js 4 / Recharts, react-dnd, Tailwind CSS 4 |
| **Backend** | Python 3.11+, FastAPI 0.115+, Pydantic v2, uvicorn, httpx (async HTTP) |
| **AI / LLM** | Amazon Bedrock — Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) for NLP classification + chart generation, Amazon Titan Embeddings V2 |
| **Agent Framework** | Strands SDK (tool-calling AI agents for visualization + orchestration) |
| **MCP Layer** | MCP SDK 1.0+, custom MCP servers (mcp-redshift, mcp-s3), MCP Adapter bridge service |
| **Content Safety** | Amazon Bedrock Guardrails (input + output content filtering) |
| **Storage** | Amazon S3 (ontology, data sources, cost logs, query history) |
| **Data Warehouse** | Amazon Redshift (via Data API — no VPC connectivity required) |
| **Testing** | pytest, Hypothesis (property-based), pytest-asyncio, Vitest (frontend), fast-check |
| **Deployment** | Docker (multi-stage), AWS App Runner, CloudFront CDN, AWS CodeBuild |
| **CI/CD** | AWS CodeBuild (buildspec YAML), ECR auto-deploy to App Runner |

---

## 3. High-Level Architecture Diagram

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
│  └──────────────────────────────────┬─────────────────────────────────────────┘  │
│                                     │ HTTP POST (StructuredIntent)               │
│                                     ▼                                            │
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
│                                              MCP Protocol (streamable-http)      │
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
│  │ • Claude Haiku   │  │ • Ontology   │  │                  │  │             │  │
│  │   4.5 (NLP +     │  │ • Data files │  │ • Input filter   │  │ • Data API  │  │
│  │   visualization) │  │ • Cost logs  │  │ • Output filter  │  │ • SQL exec  │  │
│  │ • Titan Embed V2 │  │ • History    │  │ • PII detection  │  │ • No VPC    │  │
│  │   (embeddings)   │  │ • Sessions   │  │                  │  │   required  │  │
│  └──────────────────┘  └──────────────┘  └──────────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Service Inventory

| Service | Port | LLM? | Role |
|---------|------|------|------|
| NLP Translator | 8001 | Yes (classification) | Entry point. NL → StructuredIntent. Pipeline orchestrator. |
| Orchestrator Hub | 8002 | No (deterministic) | Routes intents to agents by entity_ref overlap. Caches results. |
| Guardrail Layer | 8003 | Yes (Bedrock Guardrails) | Content safety on input + output. Schema validation. |
| Visualization Renderer | 8004 | Yes (chart generation) | Data → Chart.js config via Strands Agent + fallback heuristics. |
| Spoke Agent (S3) | 8010 | No (deterministic) | Reads JSON/CSV from S3. Lookup/Aggregate/Compare. |
| Redshift Spoke Agent | 8011 | Yes (SQL generation) | Generates + executes SQL against Redshift Data API. |
| MCP Adapter | 8012 | No (translation) | Bridges Orchestrator ↔ MCP servers. Feature-flag gated. |
| MCP Redshift Server | 7010 | No | MCP-compliant server exposing Redshift tools. |
| MCP S3 Server | 7020 | No | MCP-compliant server exposing S3 dataset tools. |

---

## 5. End-to-End Query Lifecycle

### 5.1 Request Flow (Happy Path)

```
User types: "show me quarterly sales revenue by region"
    │
    ▼
[1] Frontend (React) → POST /query → NLP Translator (8001)
    • Generates X-Correlation-ID (UUID v4) for cancellation tracking
    • 120s client-side timeout
    │
    ▼
[2] INPUT GUARDRAIL (parallel with NLP translation)
    • Bedrock Guardrails API (source=INPUT)
    • Checks: hate speech, violence, PII, sexual content, misconduct
    • Cached per query text (avoids repeat calls)
    • Fail-open: if Bedrock unreachable, allows through
    • If blocked → HTTP 422 CONTENT_POLICY_VIOLATION
    │
    ▼
[3] NLP TRANSLATION
    a. Keyword extraction from query
    b. Ontology Store lookup (S3: enterprise_ontology.json)
       → Matches: ontology:sales_revenue, ontology:quarterly_report
    c. Specificity check (rejects vague queries)
    d. Query type classification via Bedrock Claude:
       → "aggregation" | "lookup" | "comparison"
       → LRU cache (1000 entries) skips Bedrock on repeat
    e. Visualization hint extraction (regex: "bar", "line", "pie", etc.)
    f. Query History bias check (S3, Titan Embeddings similarity)
    g. Produces StructuredIntent:
       {
         query_id: UUID,
         query_type: "aggregation",
         entity_refs: ["ontology:sales_revenue", "ontology:quarterly_report"],
         routing_metadata: { query_text: "...", requested_chart_type: null },
         timestamp: "..."
       }
    │
    ▼
[4] ORCHESTRATOR HUB (8002)
    a. Result cache check (SHA-256 of intent) → MISS
    b. Agent resolution: match entity_refs against registered agents
       → Spoke Agent (8010) has overlapping entity_refs
    c. Feature-flag check: USE_MCP_ADAPTER?
       • If true + USE_MCP_S3=true → route to MCP Adapter (8012)
       • If false → route to Spoke Agent (8010) directly
    d. HTTP dispatch (concurrent, 30s timeout per agent)
    e. Merge AgentResult(s)
    f. Cache successful response
    │
    ▼
[5] DATA RETRIEVAL (Spoke Agent 8010 OR MCP Adapter 8012)
    ┌─────────────────────────────────────────────────────┐
    │ Legacy Path (Spoke Agent):                          │
    │  • Routes by entity_refs to financial_data.json     │
    │  • Performs aggregation (sum, avg, min, max, count) │
    │  • Groups by "region"                               │
    │  • Returns tabular AgentResult                      │
    ├─────────────────────────────────────────────────────┤
    │ MCP Path (MCP Adapter → mcp-s3):                    │
    │  • IntentRouter resolves dataset name               │
    │  • S3Translator builds MCP tool call                │
    │  • Calls mcp-s3 server (port 7020) via MCP SDK     │
    │  • ResponseTransformer → AgentResult                │
    │  • On failure: FallbackHandler → Spoke Agent (8010) │
    └─────────────────────────────────────────────────────┘
    │
    ▼
[6] GUARDRAIL LAYER (8003)
    a. Schema validation (results exist, payloads present)
    b. Output cache check → MISS
    c. Bedrock Guardrails (source=OUTPUT)
    d. Result: "passed" | "rejected" (422) | "error" (500)
    e. Cache validated response
    │
    ▼
[7] VISUALIZATION RENDERER (8004)
    a. Render cache check → MISS
    b. Chart type decision tree (10 levels):
       → Data shape analysis → aggregation type → cardinality → chart type
    c. Strands Agent (Bedrock Claude):
       → Generates Chart.js config JSON
       → 3 retries with error feedback
    d. Deterministic fallback if LLM fails
    e. Produces RenderedOutput:
       {
         chart_data: { type: "bar", data: {...}, options: {...} },
         raw_data: { columns: [...], rows: [...] },
         metadata: { query_type, chart_type, latency_ms, latency_breakdown }
       }
    │
    ▼
[8] RESPONSE → Frontend
    • React renders Chart.js interactive chart
    • StatsPanel shows latency breakdown
    • TraceabilityPanel shows entity resolution + routing path
    • Session auto-saved to localStorage (Zustand)
```

### 5.2 Latency Profile

| Scenario | Total Latency | Breakdown |
|----------|--------------|-----------|
| **Cold (all caches empty)** | ~30-40s | NLP classification 4-6s, Agent dispatch 1-2s, Guardrail 2-3s, Visualization 20-30s |
| **Warm (all caches hit)** | <1s | Cache lookups only, no Bedrock API calls |
| **Partial warm** | 5-10s | Some cache hits, typically viz rendering is the bottleneck |

---

## 6. MCP (Model Context Protocol) Architecture

### 6.1 Overview

The MCP layer provides a standardized, tool-calling interface for data access. It sits between the Orchestrator Hub and the raw data sources, enabling AI agents and external systems to query data through well-defined MCP tools.

```
┌──────────────────────────────────────────────────────────────────┐
│                    MCP INTEGRATION LAYER                           │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ MCP Adapter Service (port 8012)                            │   │
│  │                                                            │   │
│  │  ┌──────────────┐  ┌───────────────┐  ┌────────────────┐  │   │
│  │  │ IntentRouter │  │ Redshift      │  │ S3Translator   │  │   │
│  │  │ (ontology    │  │ Translator    │  │ (dataset       │  │   │
│  │  │  resolution) │  │ (SQL gen +    │  │  resolution +  │  │   │
│  │  │              │  │  tool mapping)│  │  tool mapping) │  │   │
│  │  └──────────────┘  └───────────────┘  └────────────────┘  │   │
│  │                                                            │   │
│  │  ┌──────────────────┐  ┌─────────────────────────────┐    │   │
│  │  │ ClientManager    │  │ FallbackHandler              │    │   │
│  │  │ (connections,    │  │ (routes to legacy agents     │    │   │
│  │  │  reconnection,   │  │  on MCP unavailability)      │    │   │
│  │  │  health tracking)│  │                              │    │   │
│  │  └──────────────────┘  └─────────────────────────────┘    │   │
│  │                                                            │   │
│  │  ┌─────────────────────────────────────────────────────┐   │   │
│  │  │ ResponseTransformer                                  │   │   │
│  │  │ (MCPToolResult → AgentResult normalization)          │   │   │
│  │  └─────────────────────────────────────────────────────┘   │   │
│  └────────────────────────────────────────────────────────────┘   │
│                          │                    │                    │
│          MCP Protocol    │                    │   MCP Protocol     │
│       (streamable-http)  │                    │ (streamable-http)  │
│                          ▼                    ▼                    │
│  ┌─────────────────────────┐  ┌────────────────────────────────┐  │
│  │ mcp-redshift (port 7010)│  │ mcp-s3 (port 7020)            │  │
│  │                         │  │                                │  │
│  │ Python package:         │  │ Python package:                │  │
│  │   mcp_redshift          │  │   mcp_s3                      │  │
│  │                         │  │                                │  │
│  │ Isolated venv:          │  │ Isolated venv:                 │  │
│  │   /app/venv-mcp-rs      │  │   /app/venv-mcp-s3            │  │
│  │                         │  │                                │  │
│  │ Features:               │  │ Features:                      │  │
│  │ • SQL validation        │  │ • YAML dataset registry        │  │
│  │ • Read-only enforcement │  │ • Format readers (CSV, JSON,   │  │
│  │ • Pagination + cursors  │  │   JSONL, Parquet)              │  │
│  │ • Metadata caching      │  │ • Partition-aware reads        │  │
│  │ • Rate limiting         │  │ • Path traversal prevention    │  │
│  │ • IAM auth              │  │ • Metadata caching + LRU       │  │
│  └───────────┬─────────────┘  └──────────────┬─────────────────┘  │
│              │                                │                    │
└──────────────┼────────────────────────────────┼────────────────────┘
               │                                │
               ▼                                ▼
      ┌─────────────────┐             ┌─────────────────┐
      │ Amazon Redshift │             │ Amazon S3       │
      │ (Data API)      │             │ (Object Store)  │
      └─────────────────┘             └─────────────────┘
```

### 6.2 MCP Servers (Git Submodule)

The MCP servers live in a separate repository included as a git submodule at `./mcps`:

```
.gitmodules:
  [submodule "mcps"]
    path = mcps
    url = https://github.com/ivanjm3/mcps
```

**mcp-redshift** — Tools for Amazon Redshift access:

| Tool | Description |
|------|-------------|
| `list_schemas` | List accessible database schemas |
| `list_tables` | List tables within a schema |
| `describe_table` | Column definitions with PK/FK info |
| `execute_query` | Read-only SQL (SELECT/WITH/EXPLAIN) with pagination |
| `execute_parameterized_query` | Pre-defined parameterized templates |
| `explain_query` | Execution plan for a SQL query |
| `get_table_statistics` | Row count, column info, sample values |
| `get_relationships` | Foreign key relationship discovery |
| `get_semantic_metadata` | Business-level metadata (types, descriptions, tags) |

**mcp-s3** — Tools for S3 dataset access:

| Tool | Description |
|------|-------------|
| `list_datasets` | List registered datasets (name, description, format) |
| `describe_dataset` | Schema summary, partition keys, format |
| `get_schema` | Column definitions (name, type, nullable) |
| `sample_dataset` | Preview sample rows |
| `read_dataset` | Read data with pagination (limit/offset) |
| `read_partition` | Filtered reads by partition keys |
| `get_dataset_statistics` | Row count, file count, size, last updated |
| `get_semantic_metadata` | Dimensions, measures, tags |

### 6.3 MCP Feature Flags & Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `USE_MCP_ADAPTER` | `false` | Global toggle — enables MCP routing in Orchestrator |
| `USE_MCP_REDSHIFT` | `false` | Route Redshift queries via MCP (vs legacy agent 8011) |
| `USE_MCP_S3` | `false` | Route S3 queries via MCP (vs legacy agent 8010) |
| `MCP_ADAPTER_REDSHIFT_TRANSPORT` | `stdio` | Transport: `stdio` or `streamable-http` |
| `MCP_ADAPTER_REDSHIFT_HOST` | — | Host for streamable-http mode |
| `MCP_ADAPTER_REDSHIFT_PORT` | — | Port for streamable-http mode |
| `MCP_ADAPTER_REDSHIFT_COMMAND` | — | Executable for stdio mode |
| `MCP_ADAPTER_REDSHIFT_TIMEOUT` | `30` | Tool call timeout (1-300 seconds) |
| `MCP_ADAPTER_S3_TRANSPORT` | `stdio` | Transport: `stdio` or `streamable-http` |
| `MCP_ADAPTER_S3_HOST` | — | Host for streamable-http mode |
| `MCP_ADAPTER_S3_PORT` | — | Port for streamable-http mode |
| `MCP_ADAPTER_S3_COMMAND` | — | Executable for stdio mode |
| `MCP_ADAPTER_S3_TIMEOUT` | `30` | Tool call timeout (1-300 seconds) |

### 6.4 MCP Routing Decision Flow

```
Orchestrator receives StructuredIntent
    │
    ├── USE_MCP_ADAPTER = false?
    │   └── Route to legacy agents (8010 / 8011) directly
    │
    ├── USE_MCP_ADAPTER = true
    │   │
    │   ├── Entity maps to Redshift + USE_MCP_REDSHIFT = true?
    │   │   └── MCP Adapter → mcp-redshift (7010) → Redshift Data API
    │   │       └── On failure → FallbackHandler → Redshift Spoke Agent (8011)
    │   │
    │   ├── Entity maps to S3 + USE_MCP_S3 = true?
    │   │   └── MCP Adapter → mcp-s3 (7020) → S3
    │   │       └── On failure → FallbackHandler → Spoke Agent (8010)
    │   │
    │   └── Feature flag off for that source?
    │       └── Route to legacy agent directly
```

### 6.5 MCP Transport Modes

| Mode | Use Case | Connection |
|------|----------|------------|
| **stdio** | Development, single-machine | Subprocess stdin/stdout |
| **streamable-http** | Production, container | HTTP on localhost:7010/7020 |

In production (Docker container), all processes run in the same container with MCP servers on `localhost` using streamable-http. The Adapter connects to them via HTTP.

### 6.6 MCP Resilience Patterns

- **Auto-reconnection**: Up to 10 attempts, 30s interval between retries
- **Graceful degradation**: If MCP server unavailable at startup, system starts normally using legacy agents
- **Per-request fallback**: If MCP call fails mid-flight, FallbackHandler dispatches to legacy agent
- **Health endpoint**: `/health` on MCP Adapter reports per-server availability status
- **Cancellation-aware**: Checks CancellationRegistry before and after MCP tool calls

---

## 7. Ontology & Data Model

### 7.1 Ontology Structure

The enterprise ontology (`data/ontology/enterprise_ontology.json`) defines 17 concepts organized into domains:

| Domain | Concepts | Data Source | Agent |
|--------|----------|-------------|-------|
| **Finance** | sales_revenue, order_volume, return_rate, quarterly_report | S3 (financial_data.json) | Spoke Agent (8010) |
| **Inventory** | product_catalog, inventory_stock, product_pricing, supplier_info | S3 (product_catalog.csv) | Spoke Agent (8010) |
| **HR** | workforce_metrics | Redshift (workforce_metrics table) | Redshift Spoke (8011) |
| **Customer Support** | support_tickets | Redshift (support_tickets table) | Redshift Spoke (8011) |
| **Marketing** | marketing_campaigns | Redshift (marketing_campaigns table) | Redshift Spoke (8011) |
| **Shared Dimensions** | product_category, region, office_location, department, customer_tier, marketing_channel | Cross-cutting reference | — |

### 7.2 Ontology Concept Schema

Each concept includes:
- `concept_id` — Namespaced identifier (e.g., `ontology:sales_revenue`)
- `label` — Human-readable name
- `properties.domain` — Business domain
Not done — the output got cut off. Here's the rest starting from where it stopped:

```markdown
- `properties.data_source` — Which backing store (financial_data, product_catalog, redshift)
- `properties.agent_id` — Which agent handles this concept
- `properties.table_name` — Logical table name for query routing
- `properties.columns` — Full column-level metadata (type, unit, description)
- `properties.filter_keywords` — Keywords that trigger this concept during NLP entity resolution
- `relationships` — Edges to other concepts (contributes_to, contains, grouped_by)

### 7.3 Relationship Graph

```
quarterly_report ←── contributes_to ─── sales_revenue
                ←── contributes_to ─── order_volume
                ←── contributes_to ─── return_rate

product_catalog ─── contains ──→ inventory_stock
                ─── contains ──→ product_pricing
                ─── contains ──→ supplier_info

sales_revenue   ─── grouped_by ──→ product_category
                ─── grouped_by ──→ region

product_catalog ─── grouped_by ──→ product_category
supplier_info   ─── grouped_by ──→ region

workforce_metrics    ─── grouped_by ──→ office_location
                     ─── grouped_by ──→ department

support_tickets      ─── grouped_by ──→ customer_tier
marketing_campaigns  ─── grouped_by ──→ marketing_channel
```

---

## 8. Frontend Architecture

### 8.1 Component Hierarchy

```
App.tsx
├── Sidebar (session list, saved prompts)
├── ChatThread
│   ├── VisualizationCard (per query result)
│   │   ├── ChartRenderer (Chart.js canvas)
│   │   ├── CardToolbar (export PNG/CSV, chart type switch, fullscreen)
│   │   ├── CardHistoryDropdown (version history per card)
│   │   └── StrandConversation (follow-up thread per card)
│   ├── ErrorCard (error display)
│   └── ErrorMessage
├── ChatInput / ChatBar (query input + send)
├── StatsPanel (latency breakdown, cache status)
├── TraceabilityPanel (entity resolution path, routing decisions)
├── FullscreenModal (expanded chart view)
├── SaveSessionModal (save/name sessions)
├── DraggableCard (react-dnd drag/drop for grid layout)
└── FooterBar
```

### 8.2 State Management

- **Zustand store** (`sessionStore.ts`) — global app state
- **localStorage persistence** — sessions survive page reload
- **Per-card state**: query text, rendered output, loading state, error, conversation history
- **Correlation IDs**: tracked per-query for cancellation support

### 8.3 API Layer (`queryApi.ts`)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query` | POST | Submit natural language query |
| `/cancel` | POST | Cancel in-flight query by correlation ID |
| `/query/follow-up` | POST | Conversational follow-up about a chart |
| `/api/re-render` | POST | Convert chart type (bar → line, etc.) |
| `/sessions/:id` | GET | Restore server-persisted session |

### 8.4 Key Frontend Libraries

| Library | Purpose |
|---------|---------|
| Chart.js 4 + react-chartjs-2 | Interactive chart rendering |
| Recharts | Alternative chart library (some components) |
| react-dnd | Drag-and-drop card grid layout |
| Zustand | Lightweight state management |
| html2canvas | PNG export of charts |
| Tailwind CSS 4 | Utility-first styling |

---

## 9. Caching Strategy

The system employs a **4-layer caching strategy** to minimize LLM costs and reduce latency:

```
Layer 1: NLP Classification Cache (LRU, 1000 entries)
    │     Key: query_text + sorted entity_refs
    │     Skips: Bedrock classification API call
    │
Layer 2: Orchestrator Result Cache (SHA-256)
    │     Key: deterministic hash of StructuredIntent
    │     Skips: Agent dispatch + data retrieval
    │
Layer 3: Guardrail Validation Cache (SHA-256)
    │     Key: hash of serialized orchestrator response
    │     Skips: Bedrock Guardrails API call
    │
Layer 4: Visualization Render Cache
          Key: data payload + chart type
          Skips: Strands Agent LLM chart generation
```

Additionally:
- **Input Guardrail Cache** — same query text skips Bedrock input check
- **Ontology Store Cache** — S3 ontology loaded once, cached in-memory
- **MCP Metadata Cache** — mcp-redshift and mcp-s3 cache table/dataset metadata with configurable TTL

---

## 10. Observability & Tracing

### 10.1 Correlation IDs

Every request is tagged with an `X-Correlation-ID` header (UUID v4) that propagates through all services. This enables:
- End-to-end request tracing across all 7 services
- Cooperative cancellation (any service can check if the query was cancelled)
- Log correlation for debugging

### 10.2 Latency Breakdown

Every response includes per-stage latency metrics:

```json
{
  "metadata": {
    "latency_ms": 12450,
    "latency_breakdown": {
      "nlp_translation_ms": 4200,
      "orchestrator_dispatch_ms": 1500,
      "guardrail_validation_ms": 2800,
      "visualization_rendering_ms": 3950
    }
  }
}
```

### 10.3 Observability Decorator

All service endpoints use `@observability_decorator` which:
- Extracts correlation ID from headers
- Logs entry/exit with timing
- Propagates correlation ID to downstream calls via `propagation_headers()`

### 10.4 Cost Tracking

LLM usage (Bedrock calls) is tracked and logged to S3 for cost monitoring.

---

## 11. Cooperative Cancellation

```
User clicks "Cancel" in frontend
    │
    ▼
Frontend sends POST /cancel { correlation_id: "..." }
    │
    ▼
NLP API registers cancellation in CancellationRegistry (TTL: 300s, max: 1000)
    │
    ▼
All downstream services check registry before expensive I/O:
    • Before Bedrock API calls
    • Before agent HTTP dispatch
    • Before MCP tool invocations
    • Between pipeline stages
    │
    ▼
If cancelled: return QUERY_CANCELLED error immediately
```

Additionally, services check `request.is_disconnected()` to detect client-initiated TCP disconnects.

---

## 12. Deployment Architecture

### 12.1 Production Topology (AWS)

```
┌──────────────────────────────────────────────────────────────────┐
│                         INTERNET                                   │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    AWS CloudFront (CDN)                            │
│                                                                   │
│   ┌────────────────────┐     ┌─────────────────────────────────┐  │
│   │ Origin: S3 Bucket  │     │ Origin: App Runner              │  │
│   │ (/* static assets) │     │ (/query, /cancel, /sessions/*)  │  │
│   │                    │     │ (/api/*, /health)               │  │
│   └────────────────────┘     └─────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│              AWS App Runner (auto-scaling, auto-HTTPS)             │
│              1 vCPU / 2 GB Memory                                 │
│                                                                   │
│   ┌────────────────────────────────────────────────────────────┐  │
│   │ Single Docker Container (multi-process)                     │  │
│   │                                                             │  │
│   │  run_all.py (launcher)                                      │  │
│   │    ├── NLP Translator       (uvicorn, port 8001) ← health  │  │
│   │    ├── Orchestrator Hub     (uvicorn, port 8002)            │  │
│   │    ├── Guardrail Layer      (uvicorn, port 8003)            │  │
│   │    ├── Visualization Renderer (uvicorn, port 8004)          │  │
│   │    ├── Spoke Agent          (uvicorn, port 8010)            │  │
│   │    ├── Redshift Spoke Agent (uvicorn, port 8011)            │  │
│   │    ├── MCP Adapter          (uvicorn, port 8012)            │  │
│   │    ├── mcp-redshift         (subprocess, port 7010)         │  │
│   │    └── mcp-s3               (subprocess, port 7020)         │  │
│   │                                                             │  │
│   │  3 isolated Python venvs:                                   │  │
│   │    /app/venv        — main app (FastAPI, boto3>=1.35)       │  │
│   │    /app/venv-mcp-rs — mcp-redshift (own boto3)             │  │
│   │    /app/venv-mcp-s3 — mcp-s3 (own aiobotocore)            │  │
│   └────────────────────────────────────────────────────────────┘  │
│                                                                   │
│   Instance Role: talk2data-apprunner-role                         │
│   ECR Pull Role: AppRunnerECRAccessRole                           │
│   Health Check: GET /health on port 8001 (15s interval)           │
│   Auto-deploy: ECR push triggers automatic redeploy               │
└──────────────────────────────────────────────────────────────────┘
```

### 12.2 Docker Build (Multi-Stage)

```dockerfile
# Stage 1: Frontend Build
FROM node:20-slim AS frontend-build
  → npm ci + vite build → /frontend/dist/

# Stage 2: Python Runtime
FROM python:3.12-slim
  → Venv 1: /app/venv          (main app + MCP SDK)
  → Venv 2: /app/venv-mcp-rs   (mcp-redshift package)
  → Venv 3: /app/venv-mcp-s3   (mcp-s3 package)
  → Copy frontend/dist, data/, run_all.py
  → HEALTHCHECK on port 8001
  → CMD: /app/venv/bin/python run_all.py
```

The 3 isolated venvs prevent `boto3`/`botocore`/`aiobotocore` version conflicts between the main application and MCP server packages.

### 12.3 CI/CD Pipeline (AWS CodeBuild)

```
Developer pushes code
    │
    ▼
deploy/deploy.sh [--build-backend | --build-frontend | --build-all]
    │
    ├── Backend Pipeline:
    │   1. Package source → zip
    │   2. Upload to S3 artifact bucket
    │   3. Trigger CodeBuild (buildspec-backend.yaml)
    │   4. CodeBuild: docker build → ECR push (tag: latest)
    │   5. App Runner auto-deploys from ECR
    │
    └── Frontend Pipeline:
        1. Package frontend/ → zip
        2. Upload to S3 artifact bucket
        3. Trigger CodeBuild (buildspec-frontend.yaml)
        4. CodeBuild: npm ci → vite build → S3 sync
        5. CloudFront invalidation
```

### 12.4 IAM Roles

| Role | Purpose |
|------|---------|
| `talk2data-apprunner-role` | App Runner instance role — access to Bedrock, S3, Redshift |
| `AppRunnerECRAccessRole` | App Runner ECR pull access |
| `talk2data-codebuild-role` | CodeBuild service role — ECR push, S3 read/write |

### 12.5 Key AWS Resources

| Resource | Name/ID |
|----------|---------|
| ECR Repository | `conversational-bi-prod` |
| App Runner Service | `conversational-bi-prod` |
| S3 Data Bucket | `visualization-poc-bucket` |
| S3 Frontend Bucket | `conversational-bi-frontend-prod-654654478821` |
| S3 Artifact Bucket | `conversational-bi-codebuild-prod-654654478821` |
| Bedrock Guardrail | `unf4323uxnff` (DRAFT version) |
| Bedrock Model | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| Embeddings Model | `amazon.titan-embed-text-v2:0` |

---

## 13. Security Architecture

### 13.1 Content Safety

- **Input filtering**: Bedrock Guardrails checks every user query before processing
- **Output filtering**: Bedrock Guardrails validates all data responses before returning to user
- **Categories blocked**: Hate speech, violence, sexual content, insults, misconduct, PII
- **Fail-open**: If Bedrock Guardrails unavailable, system continues (availability > safety in this context)

### 13.2 Data Access Security

- **MCP servers**: Read-only enforcement (mcp-redshift allows only SELECT/WITH/EXPLAIN)
- **S3 access**: Only registered datasets accessible (YAML registry controls exposure)
- **Path traversal prevention**: mcp-s3 validates all paths against configured prefixes
- **SQL injection prevention**: Parameterized queries + SQL validation in mcp-redshift
- **Rate limiting**: Sliding window rate limiting on both MCP servers

### 13.3 Authentication & Authorization

- **AWS IAM**: All AWS service access via IAM roles (no hardcoded credentials)
- **SSO**: Development uses AWS SSO profiles
- **Container auth**: ECS/App Runner task roles (no profile needed in production)
- **No user auth**: System currently trusts all incoming requests (assumes network-level security via CloudFront)

---

## 14. Project Structure

```
conversational-bi/
├── run_all.py                    # Launcher: starts all 9 processes
├── pyproject.toml                # Python project config (hatchling)
├── .gitmodules                   # MCP servers submodule reference
├── .dockerignore                 # Docker build exclusions
│
├── src/                          # Backend source
│   ├── config.py                 # Central configuration (ports, AWS, models)
│   ├── models/
│   │   ├── shared.py             # Pydantic models (StructuredIntent, AgentResult, etc.)
│   │   ├── ontology.py           # OntologyConcept model
│   │   └── redshift_models.py    # Redshift-specific models
│   ├── services/
│   │   ├── nlp_api.py            # NLP Translator FastAPI app (port 8001)
│   │   ├── nlp_translator.py     # NLP translation logic
│   │   ├── orchestrator_api.py   # Orchestrator Hub FastAPI app (port 8002)
│   │   ├── orchestrator_hub.py   # Routing + dispatch logic
│   │   ├── guardrail_api.py      # Guardrail Layer FastAPI app (port 8003)
│   │   ├── guardrail_layer.py    # Guardrail validation logic
│   │   ├── visualization_api.py  # Viz Renderer FastAPI app (port 8004)
│   │   ├── visualization_renderer.py  # Chart generation logic
│   │   ├── ontology_store.py     # S3-backed ontology access
│   │   ├── result_cache.py       # Orchestrator result cache
│   │   ├── cache_layer.py        # Exact-match result caching
│   │   ├── query_history_store.py # S3-backed query history + embedding similarity lookup
│   │   ├── schema_registry.py    # Redshift schema metadata
│   │   ├── sql_generator.py      # SQL generation for Redshift
│   │   ├── meta_query_detector.py # Detects meta-queries about the system
│   │   ├── cancellation_registry.py # Cooperative cancellation tracking
│   │   ├── observability.py      # Correlation IDs, decorators, tracing
│   │   └── logging_config.py     # Centralized logging setup
│   └── agents/
│       ├── spoke_agent.py        # S3 data agent (port 8010)
│       ├── redshift_spoke_agent.py # Redshift agent (port 8011)
│       └── mcp_adapter/          # MCP bridge service (port 8012)
│           ├── service.py        # FastAPI app + endpoints
│           ├── config.py         # Environment-based configuration
│           ├── client_manager.py # MCP connection lifecycle
│           ├── intent_router.py  # Entity → MCP server routing
│           ├── redshift_translator.py # Intent → Redshift MCP tool calls
│           ├── s3_translator.py  # Intent → S3 MCP tool calls
│           ├── response_transformer.py # MCPToolResult → AgentResult
│           ├── fallback_handler.py # Legacy agent fallback
│           └── models.py         # MCP-specific Pydantic models
│
├── frontend/                     # React SPA
│   ├── package.json              # Dependencies (React 19, Chart.js, Zustand, etc.)
│   ├── vite.config.ts            # Vite build config
│   ├── tsconfig.json             # TypeScript config
│   └── src/
│       ├── main.tsx              # React entry point
│       ├── App.tsx               # Root component
│       ├── api/queryApi.ts       # Backend HTTP client
│       ├── store/sessionStore.ts # Zustand state + persistence
│       ├── types/index.ts        # TypeScript interfaces
│       ├── components/           # 20+ React components
│       └── utils/                # chartSelector, csvExport, pngExport
│
├── mcps/                         # Git submodule (MCP servers)
│   ├── mcp-redshift/             # Redshift MCP server package
│   └── mcp-s3/                   # S3 MCP server package
│
├── data/
│   ├── ontology/
│   │   └── enterprise_ontology.json  # Domain knowledge graph (17 concepts)
│   └── sources/
│       ├── financial_data.json   # Sales/revenue data (S3 source)
│       └── product_catalog.csv   # Product inventory (S3 source)
│
├── deploy/
│   ├── Dockerfile                # Multi-stage production build
│   ├── deploy.sh                 # Main deployment orchestrator
│   ├── create-apprunner.sh       # App Runner creation
│   ├── update-apprunner.sh       # App Runner updates
│   ├── create-cloudfront.sh      # CloudFront CDN setup
│   ├── buildspec-backend.yaml    # CodeBuild spec (Docker → ECR)
│   └── buildspec-frontend.yaml   # CodeBuild spec (Vite → S3)
│
├── tests/
│   ├── unit/                     # Unit tests (ontology, cache, observability)
│   ├── integration/              # Integration tests (routing)
│   └── properties/               # Hypothesis property-based tests
│
├── docs/
│   ├── SYSTEM_OVERVIEW.md        # Comprehensive system guide
│   ├── SYSTEM_ARCHITECTURE.md    # Architecture reference
│   ├── RUNNING_GUIDE.md          # Local development guide
│   └── AGENTCORE_DEPLOYMENT.md   # Bedrock AgentCore deployment
│
└── .kiro/specs/                  # Feature specifications
    ├── agent-multi-source-retrieval/
    ├── conversational-bi-frontend/
    ├── feature-enhancements/
    ├── mcp-data-access-integration/
    ├── ontology-routing-fix/
    ├── query-cancellation/
    └── redshift-data-source-integration/
```

---

## 15. Startup Sequence

```
run_all.py executes:

1. Set MCP environment variables (ports, transports, feature flags)
2. Start NLP Translator (8001) — FIRST (App Runner health check target)
3. Start core services in parallel:
   • Orchestrator Hub (8002)
   • Guardrail Layer (8003)
   • Visualization Renderer (8004)
   • Spoke Agent (8010)
   • Redshift Spoke Agent (8011)
4. Start MCP servers (if USE_MCP_ADAPTER=true):
   • mcp-redshift (7010) — using /app/venv-mcp-rs/bin/python
   • mcp-s3 (7020) — using /app/venv-mcp-s3/bin/python
5. Start MCP Adapter (8012)
6. Health check all services (HTTP GET /health per port)
7. Register spoke agents with Orchestrator Hub:
   • POST /admin/agents with agent_id, endpoint_url, data_source, entity_refs
8. System ready — accepting queries on port 8001
```

---

## 16. Key Architectural Patterns

### 16.1 Hub-and-Spoke Agent Routing
- Orchestrator (hub) resolves agents from ontology entity_refs overlap
- Agents (spokes) handle specific data domains independently
- New data sources added by: creating agent + registering entity_refs

### 16.2 LLM + Deterministic Hybrid
- LLM for intelligence (classification, chart generation, SQL writing)
- Heuristics for resilience (every LLM stage has a deterministic fallback)
- Guarantees 100% query resolution regardless of LLM availability

### 16.3 Feature-Flag Routing
- MCP vs legacy agents controlled entirely by environment variables
- Hot-toggleable without code changes or redeploy (update App Runner env vars)
- Enables incremental migration from legacy to MCP-based data access

### 16.4 Fail-Open Safety
- Guardrails unavailable → content passes through (availability prioritized)
- MCP unavailable → automatic fallback to legacy agents
- LLM unavailable → deterministic fallback produces reasonable result

### 16.5 Multi-Layer Caching
- 4+ independent cache layers minimize cost and latency
- Each layer uses deterministic hashing for cache keys
- Cold start: ~30-40s; Warm: <1s

### 16.6 Cooperative Cancellation
- Correlation IDs propagate through entire call chain
- CancellationRegistry checked before every expensive operation
- Client disconnect detection via `request.is_disconnected()`

---

## 17. Local Development

### Prerequisites
- Python 3.11+
- Node.js 20+
- AWS CLI v2 with SSO configured
- AWS profile: `PowerUserAccess-654654478821`

### Running Locally

```bash
# Backend (all services)
python run_all.py

# Frontend (separate terminal)
cd frontend
npm install
npm run dev    # → http://localhost:5173

# Frontend connects to backend at http://localhost:8001
```

### Running Tests

```bash
# Backend tests
python -m pytest tests/ -v

# Frontend tests
cd frontend
npm run test

# Property-based tests (may take longer)
python -m pytest tests/properties/ -v
```

---

## 18. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Single container, multi-process | Simplifies deployment (App Runner). Services communicate over localhost HTTP. Can split later. |
| 3 isolated Python venvs | Prevents boto3/botocore/aiobotocore version conflicts between main app and MCP servers |
| MCP as optional layer with fallback | Enables incremental adoption without breaking existing functionality |
| Ontology-driven routing (not hardcoded) | Adding new data sources doesn't require code changes to routing logic |
| No user authentication | System assumes CloudFront + network-level security. Auth to be added in future phase. |
| S3 for all persistence | No databases to manage. Ontology, history, cost logs all in S3. |
| Strands SDK for LLM agents | Provides tool-calling, retry, and structured output without custom agent loops |
| Chart.js over D3 | Lower complexity, better React integration, sufficient for BI charts |
| Property-based testing | Hypothesis tests validate system invariants across random inputs |
```
