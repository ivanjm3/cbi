---
inclusion: auto
---

# Build, Run, and Test Guide

## Prerequisites

- Python 3.11+
- AWS credentials configured (for Bedrock access)
- pip or uv package manager

## Install Dependencies

```bash
pip install -e ".[dev]"
```

Or with uv:
```bash
uv pip install -e ".[dev]"
```

## Running Services

### Start all services:
```bash
python run_all.py
```

### Start individual services:
```bash
# NLP Translator
uvicorn src.services.nlp_api:app --port 8001

# Orchestrator Hub
uvicorn src.services.orchestrator_api:app --port 8002

# Guardrail Layer
uvicorn src.services.guardrail_api:app --port 8003

# Visualization Renderer
uvicorn src.services.visualization_api:app --port 8004

# Spoke Agent A (JSON)
uvicorn src.agents.spoke_agent_json:app --port 8010

# Spoke Agent B (CSV)
uvicorn src.agents.spoke_agent_csv:app --port 8011
```

## Running Tests

```bash
# All tests
pytest -v

# Property-based tests only
pytest tests/properties/ -v --hypothesis-seed=random

# Unit tests only
pytest tests/unit/ -v

# Integration tests (requires all services running)
pytest tests/integration/ -v --timeout=60

# Specific property test
pytest tests/properties/test_ontology_roundtrip.py -v
```

## Quick Verification

After starting all services, verify the system:

```bash
# Health checks
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health

# Submit a test query
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query_text": "Show me quarterly revenue trends"}'
```

## Data Files

- Ontology definitions: `./data/ontology/`
- Demo data sources: `./data/sources/`
- Guardrail rules: `./data/guardrail_rules.json`
- Query history DB: `./data/history.db` (auto-created)

## Troubleshooting

- **Bedrock access errors**: Ensure AWS credentials are configured and you have access to Claude Sonnet and Titan Embeddings models in your region.
- **Port conflicts**: Check that ports 8001-8004 and 8010-8011 are free.
- **SQLite errors**: Delete `./data/history.db` to reset query history.
- **Ontology errors**: Validate JSON files in `./data/ontology/` against the schema.
