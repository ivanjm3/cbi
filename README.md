# Conversational BI System

A full-stack platform that transforms natural language questions into interactive data visualizations. Users type questions like *"show me Q4 revenue by region"* and receive Chart.js charts with analytical insights — powered by Amazon Bedrock (Claude 3.5 Haiku) and a hub-and-spoke microservices backend.

![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![React 18](https://img.shields.io/badge/react-18-61dafb)
![FastAPI](https://img.shields.io/badge/fastapi-0.115%2B-009688)
![Amazon Bedrock](https://img.shields.io/badge/AWS-Bedrock-FF9900)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              FRONTEND (React + TypeScript + Chart.js)         │
│  Chat UI → Natural Language Query → Interactive Viz Grid     │
└────────────────────────────┬────────────────────────────────┘
                             │ POST /query
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                  BACKEND (5 FastAPI Services)                 │
│                                                              │
│  NLP Translator (8001) ──→ Orchestrator Hub (8002)          │
│        │                         │                           │
│        │                   Spoke Agent (8010)                │
│        │                         │                           │
│        ├── Guardrail Layer (8003) ←──┘                      │
│        │                                                     │
│        └── Visualization Renderer (8004)                    │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                      AWS SERVICES                             │
│  Amazon Bedrock (Claude 3.5 Haiku) │ S3 │ Guardrails        │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

- **Natural language to chart** — Ask business questions in plain English; get interactive visualizations
- **Intelligent chart selection** — LLM-driven chart type reasoning with 10-level decision tree fallback
- **Multi-layer caching** — NLP, orchestrator, guardrail, and renderer caches minimize cost and latency
- **Content safety** — Amazon Bedrock Guardrails on input and output with fail-open resilience
- **Deterministic fallbacks** — Every LLM-dependent stage has a heuristic fallback ensuring 100% resolution
- **Ontology-driven** — Domain concepts stored in S3 enable accurate entity resolution
- **Property-based testing** — Hypothesis-based correctness properties validate system invariants
- **Cost tracking** — Per-invocation Bedrock costs logged to S3 for observability
- **Session management** — Chat history, saved prompts, and session persistence via localStorage

---

## Technology Stack

| Layer | Technologies |
|-------|-------------|
| Frontend | React 18, TypeScript, Vite, zustand, Chart.js v4, react-dnd, Tailwind CSS |
| Backend | Python 3.11+, FastAPI, Pydantic, httpx (async), Strands SDK |
| LLM | Amazon Bedrock — Claude 3.5 Haiku |
| Agent Framework | Strands SDK (tool-calling agents) |
| Content Safety | Amazon Bedrock Guardrails |
| Storage | Amazon S3 |
| Testing | Hypothesis (PBT), pytest, Vitest |

---

## Project Structure

```
├── frontend/               # React + TypeScript + Vite frontend
│   └── src/
│       ├── api/            # Backend API client
│       ├── components/     # UI components (ChatThread, ChartRenderer, etc.)
│       ├── store/          # zustand state management
│       ├── types/          # TypeScript type definitions
│       └── utils/          # Helper utilities
├── src/                    # Python backend
│   ├── agents/             # Spoke data retrieval agents
│   ├── models/             # Pydantic models (ontology, shared types)
│   └── services/           # All microservice implementations
│       ├── nlp_api.py              # NLP Translator API (port 8001)
│       ├── nlp_translator.py       # NLP translation logic
│       ├── orchestrator_api.py     # Orchestrator Hub API (port 8002)
│       ├── orchestrator_hub.py     # Routing and dispatch logic
│       ├── guardrail_api.py        # Guardrail Layer API (port 8003)
│       ├── guardrail_layer.py      # Content safety logic
│       ├── visualization_api.py    # Viz Renderer API (port 8004)
│       ├── visualization_renderer.py  # Chart generation logic
│       ├── ontology_store.py       # Ontology entity resolution
│       ├── bedrock_wrapper.py      # AWS Bedrock client
│       └── cost_tracker.py         # LLM cost logging
├── tests/
│   ├── properties/         # Property-based tests (Hypothesis)
│   └── unit/               # Unit tests
├── data/                   # Local data sources
├── docs/                   # Architecture & deployment docs
├── scripts/                # Utility scripts
├── run_all.py              # Launches all 5 services
└── pyproject.toml          # Python project config
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- AWS account with Bedrock access enabled (us-east-1)
- Bedrock model access for Claude 3.5 Haiku
- S3 bucket with data sources and ontology files

### Backend Setup

```bash
# Install Python dependencies
pip install -e ".[dev]"

# Configure AWS credentials
aws sso login --profile your-profile

# Start all backend services
python run_all.py
```

This launches all 5 services, waits for health checks, and registers the spoke agents.

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:5173`.

---

## Usage

Once all services are running, either use the frontend chat UI or call the API directly:

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query_text": "show me quarterly sales revenue by region"}'
```

The response includes a complete Chart.js configuration, analytical insights, and latency metadata.

---

## Query Lifecycle

1. **Input Guardrails** — Content safety check via Bedrock Guardrails (parallel with NLP)
2. **NLP Translation** — Entity resolution, specificity check, intent classification, viz hints
3. **Orchestration** — Cache lookup, agent resolution via entity overlap, dispatch
4. **Data Retrieval** — Spoke agent loads from S3, executes lookup/aggregation/comparison
5. **Output Guardrails** — Schema validation + Bedrock content filtering
6. **Visualization** — LLM agent generates Chart.js config (3 retries + deterministic fallback)
7. **Rendering** — Frontend renders Chart.js canvas with interactive tooltips

---

## Testing

```bash
# Run all tests
pytest

# Run property-based tests only
pytest tests/properties/

# Run unit tests only
pytest tests/unit/

# Frontend tests
cd frontend && npm test
```

Property-based tests validate correctness properties such as:
- Ontology serialization roundtrip consistency
- Structured intent schema conformance for all valid inputs
- Chart type selection always produces valid Chart.js types
- Guardrail validation preserves data integrity

---

## Configuration

| Environment Variable | Description |
|---------------------|-------------|
| `AWS_REGION` | AWS region (default: `us-east-1`) |
| `AWS_PROFILE` | AWS SSO profile name |
| `S3_BUCKET` | Data lake bucket (default: `visualization-poc-bucket`) |
| `BEDROCK_MODEL_ID` | Model for classification (default: Claude 3.5 Haiku) |
| `GUARDRAIL_ID` | Bedrock Guardrail ID |
| `USE_AGENTCORE_VIZ` | Toggle AgentCore deployment (`true`/`false`) |

---

## Deployment

The system supports two deployment models:

1. **Self-hosted** — All 5 FastAPI services on localhost (development/demo)
2. **Amazon Bedrock AgentCore** — Managed serverless agents with Return Control pattern (production)

See [docs/agentcore-console-deployment-guide.md](docs/agentcore-console-deployment-guide.md) for the AgentCore deployment walkthrough.

---

## License

Private / Internal use.
