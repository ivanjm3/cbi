---
inclusion: auto
---

# Ontology NLP Query System - Project Overview

## System Purpose

This is an ontology-based, NLP-driven query system following a hub-and-spoke architecture. Users submit natural language queries through a web interface, which are translated into structured intents, routed to specialized data-source agents, validated through guardrails, and rendered as visualizations.

## Current Phase: Phase 1 (Development)

Phase 1 prioritizes core logic correctness with minimal infrastructure. AWS services are minimized. The system runs as local Python processes.

### What's In Scope (Phase 1)
- NLP Translator (Bedrock Claude for intent classification)
- Orchestrator Hub (routing + concurrent dispatch)
- 2 Spoke Agents (Strands SDK, local processes)
- Guardrail Layer (schema validation + rule-based policy)
- Visualization Renderer (rule-based chart selection)
- Ontology Store (flat-file JSON only)
- Result Cache (in-memory dict)
- Query History Store (SQLite + numpy cosine similarity)
- Observability Bus (Python structured JSON logging)

### What's Deferred (Future Phase)
- Auth Gateway (JWT, RBAC)
- Event Broker (streaming queries)
- Graph DB / RDBMS ontology backends
- ElastiCache Redis
- RDS PostgreSQL + pgvector
- X-Ray / CloudWatch
- ECS Fargate / AgentCore Runtime deployment
- ReAct reasoning loop for visualization

## Architecture

**Data Flow:** UI → NLP Translator → Orchestrator Hub → Spoke Agents → Guardrail Layer → Visualization Renderer → UI

**Local Services:**
| Service | Port | Role |
|---------|------|------|
| NLP Translator | 8001 | Parse queries into structured intents |
| Orchestrator Hub | 8002 | Route intents to agents, merge results |
| Guardrail Layer | 8003 | Validate responses, apply policy rules |
| Visualization Renderer | 8004 | Generate chart specs from data |
| Spoke Agent A (JSON) | 8010 | Query JSON file data source |
| Spoke Agent B (CSV) | 8011 | Query CSV file data source |

## Key Technology Choices
- **Language:** Python 3.11+
- **Web framework:** FastAPI + uvicorn
- **Agent SDK:** Strands Agents SDK
- **LLM:** Amazon Bedrock (Claude Sonnet for NLP, Titan Embeddings for history)
- **Testing:** pytest + Hypothesis (property-based testing)
- **Data models:** Pydantic v2

## Project Structure
```
src/
  models/         # Shared Pydantic data models
  services/       # Service implementations (NLP, Orchestrator, Guardrail, Viz, Cache, History)
  agents/         # Spoke agent implementations (Strands SDK)
data/
  ontology/       # Flat-file JSON ontology definitions
  sources/        # Demo data source files (JSON, CSV)
  guardrail_rules.json
  history.db      # SQLite query history
tests/
  properties/     # Hypothesis property-based tests
  unit/           # Example-based unit tests
  integration/    # End-to-end integration tests
```
