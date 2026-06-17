# Conversational BI System — Application Overview

## What It Does

A full-stack platform that transforms natural language questions into interactive data visualizations. Users type business questions in plain English and receive Chart.js charts with analytical insights — powered by Amazon Bedrock (Claude 3.5 Haiku) and a hub-and-spoke microservices architecture.

**Live URL:** https://jwxrxfzsjr.us-east-1.awsapprunner.com

---

## Core Capabilities

| Capability | Description |
|-----------|-------------|
| Natural Language to Chart | Ask questions like "show quarterly revenue by region" → get interactive charts |
| Intelligent Chart Selection | LLM-driven chart type reasoning (bar, line, pie, scatter, bubble, etc.) with deterministic fallback |
| Multi-Source Data Retrieval | Queries route to appropriate data sources via ontology-based entity resolution |
| Content Safety | Amazon Bedrock Guardrails validate both input queries and output responses |
| Multi-Layer Caching | NLP, orchestrator, guardrail, and renderer caches minimize cost and latency |
| Deterministic Fallbacks | Every LLM-dependent stage has a heuristic fallback ensuring 100% resolution |
| Cost Tracking | Per-invocation Bedrock costs logged to S3 for observability |
| Session Management | Chat history, saved prompts, and session persistence |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              FRONTEND (React + TypeScript + Chart.js)         │
│  Chat UI → Natural Language Query → Interactive Chart Grid   │
└────────────────────────────┬────────────────────────────────┘
                             │ POST /query
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND (5 FastAPI Microservices)            │
│                                                              │
│  ┌──────────────┐    ┌──────────────────┐                   │
│  │ NLP Translator│───►│ Orchestrator Hub  │                   │
│  │   (port 8001) │    │   (port 8002)    │                   │
│  └──────┬───────┘    └────────┬─────────┘                   │
│         │                     │                              │
│         │              ┌──────▼──────┐                       │
│         │              │ Spoke Agent  │                       │
│         │              │ (port 8010)  │                       │
│         │              └──────┬──────┘                       │
│         │                     │                              │
│  ┌──────▼───────┐    ┌───────▼──────────┐                   │
│  │Guardrail Layer│    │ Visualization    │                   │
│  │  (port 8003)  │    │ Renderer (8004)  │                   │
│  └──────────────┘    └──────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      AWS SERVICES                             │
│  Amazon Bedrock (Claude 3.5 Haiku) │ S3 │ Guardrails        │
└─────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

| Layer | Technologies |
|-------|-------------|
| Frontend | React 18, TypeScript, Vite, zustand, Chart.js v4, react-dnd, Tailwind CSS |
| Backend | Python 3.12, FastAPI, Pydantic v2, httpx (async), Strands Agents SDK |
| LLM | Amazon Bedrock — Claude 3.5 Haiku (us.anthropic.claude-3-5-haiku-20241022-v1:0) |
| Agent Framework | Strands Agents SDK (tool-calling agents for visualization) |
| Content Safety | Amazon Bedrock Guardrails (input + output filtering) |
| Data Storage | Amazon S3 (data sources, ontology, cost logs, query history) |
| Deployment | AWS App Runner (backend + frontend), ECR, CodeBuild |
| Testing | Hypothesis (property-based), pytest, Vitest |

---

## Query Lifecycle

```
User types question
        │
        ▼
1. INPUT GUARDRAILS — Bedrock Guardrails content safety check (parallel with NLP)
        │
        ▼
2. NLP TRANSLATION — Entity resolution, specificity check, intent classification
        │
        ▼
3. ORCHESTRATION — Cache lookup, agent resolution via ontology entity overlap
        │
        ▼
4. DATA RETRIEVAL — Spoke agent loads from S3, executes lookup/aggregation/comparison
        │
        ▼
5. OUTPUT GUARDRAILS — Schema validation + Bedrock content filtering
        │
        ▼
6. VISUALIZATION — Strands Agent generates Chart.js config (3 retries + deterministic fallback)
        │
        ▼
7. RENDERING — Frontend renders Chart.js canvas with interactive tooltips
```

**Average latency:** ~3-25 seconds (depends on LLM response time and caching)

---

## Data Sources

### Financial Data (JSON)
- Quarterly sales revenue, order volume, return rates
- Dimensions: quarter (Q1-Q4 2024), region (North America, Europe), category (Electronics, Office Furniture, Office Supplies)
- Metrics: revenue, orders, avg_order_value, return_rate

### Product Catalog (CSV)
- 30 products with pricing, stock levels, supplier information
- Fields: product_id, name, category, subcategory, unit_price, stock_quantity, unit_cost, supplier, supplier_region, weight_kg, is_active

### Ontology
- Enterprise ontology with 10 concepts covering sales, inventory, and shared dimensions
- Enables semantic routing of queries to appropriate data sources

---

## Deployment Architecture

```
┌────────────────────────────────────────────────┐
│           AWS App Runner                       │
│  (conversational-bi-prod)                      │
│                                                │
│  Single container running:                     │
│  • NLP Translator (8001) ← entry point         │
│  • Orchestrator Hub (8002)                     │
│  • Guardrail Layer (8003)                      │
│  • Visualization Renderer (8004)               │
│  • Spoke Agent (8010)                          │
│  • React frontend (served via FastAPI)         │
│                                                │
│  Auto-deploys from ECR on image push           │
│  Auto-scales based on traffic                  │
│  Built-in HTTPS                                │
└────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────┐
│  CodeBuild (talk2data-build-talk2data-ui)      │
│  Triggered via: bash deploy/deploy.sh          │
│  Builds Docker image → pushes to ECR           │
└────────────────────────────────────────────────┘
```

| Resource | Details |
|----------|---------|
| App Runner Service | conversational-bi-prod (1 vCPU, 2 GB) |
| ECR Repository | conversational-bi-prod |
| S3 (data) | visualization-poc-bucket |
| S3 (frontend assets) | conversational-bi-frontend-prod-654654478821 |
| S3 (build artifacts) | conversational-bi-codebuild-prod-654654478821 |
| Bedrock Model | Claude 3.5 Haiku |
| Bedrock Guardrail | unf4323uxnff (DRAFT) |
| IAM Roles | talk2data-apprunner-role, AppRunnerECRAccessRole |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Hub-and-spoke architecture | Decoupled services allow independent scaling and testing |
| Ontology-based routing | Queries route to agents by semantic entity overlap, not keyword matching |
| Strands Agents for viz | LLM-driven chart generation produces context-aware, visually rich charts |
| Deterministic fallbacks | Every LLM stage has a heuristic fallback — system never fails silently |
| Multi-layer caching | Identical queries resolve in <50ms after first execution |
| Single-container deployment | Simplifies ops while services communicate over localhost |
| Property-based testing | Hypothesis validates system invariants across random inputs |

---

## Testing Strategy

| Test Type | Coverage |
|-----------|----------|
| Property-based (Hypothesis) | Ontology serialization roundtrips, intent schema conformance, chart type validity |
| Unit tests (pytest) | Individual service logic, NLP translation, guardrail rules |
| Frontend tests (Vitest) | Component rendering, API client behavior, store logic |

```bash
# Run all tests
pytest                    # Backend
cd frontend && npm test   # Frontend
```

---

## Operational Commands

```bash
# Deploy backend (code change → Docker build → App Runner auto-deploy)
bash deploy/deploy.sh --build-backend

# Deploy frontend (code change → npm build → included in Docker image)
bash deploy/deploy.sh --build-backend

# Check backend health
curl https://jwxrxfzsjr.us-east-1.awsapprunner.com/health

# View application logs
aws logs tail "/aws/apprunner/conversational-bi-prod/707ab1e1b4c8486f92c877b68444c21d/application" \
  --profile PowerUserAccess-654654478821 --region us-east-1 --no-verify-ssl --since 10m --format short

# Run locally
python run_all.py           # Backend (port 8001)
cd frontend && npm run dev  # Frontend (port 5173)
```

---

## Future Work

### Near-Term Enhancements

| Feature | Description | Effort |
|---------|-------------|--------|
| Meta-query handling | Distinguish "what can you do?" from data queries — respond with text not charts | 1-2 days |
| Cache invalidation on data refresh | Clear stale results when S3 data sources are updated | 1 day |
| Scheduled reports (Step Functions) | Automate saved prompts on a cron schedule, store results in S3 | 2-3 days |
| Error boundary in frontend | Graceful handling when chart config is invalid instead of blank screen | 1 day |
| Multi-turn conversation | Follow-up queries that reference previous results ("now filter that by Europe") | 3-5 days |

### Medium-Term Roadmap

| Feature | Description | Effort |
|---------|-------------|--------|
| Additional data sources | Connect to Redshift, Athena, or RDS for live database queries | 1-2 weeks |
| User authentication | Cognito-based auth with role-based data access | 1 week |
| Dashboard pinning | Save visualizations to a persistent dashboard grid | 3-5 days |
| Export to PDF/PNG | Generate shareable reports from chat sessions | 2-3 days |
| Streaming responses | Show chart building in real-time as the LLM generates config | 3-5 days |
| Cost optimization | Move to Bedrock batch inference for scheduled reports | 2-3 days |

### Long-Term Vision

| Feature | Description |
|---------|-------------|
| Multi-tenant deployment | Separate data access per team/organization |
| Custom ontology editor | UI for non-technical users to map new data sources |
| Anomaly detection | Proactive alerts when metrics deviate from historical norms |
| Natural language write-back | "Set the Q1 target to $500K" → updates source data |
| Cross-source joins | Combine financial + inventory data in a single visualization |
| Fine-tuned model | Domain-specific model for better chart type selection |

---

## Cost Profile (Estimated Monthly)

| Resource | Low Traffic | Active Use |
|----------|-------------|------------|
| App Runner | ~$7 (paused) | ~$40 |
| Bedrock (Claude 3.5 Haiku) | ~$2 | ~$15-30 |
| S3 | < $1 | < $1 |
| CodeBuild (on-demand) | < $1 | ~$2-3 |
| CloudWatch Logs | < $1 | ~$2 |
| **Total** | **~$10** | **~$60-75** |

---

## Contact

Built by Ivan Madathil (ivan.madathil@wipro.com)  
Account: 654654478821 | Region: us-east-1




- SLM use
- GraphRAG ?
- knowledge graph