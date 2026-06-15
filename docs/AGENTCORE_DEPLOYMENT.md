# System Workflow & AgentCore Deployment Guide

## 1. System Workflow Overview

This system is an ontology-driven, NLP-powered conversational BI platform. A user asks a natural language question, and the system classifies it, fetches data, validates it, generates a visualization, and returns an interactive chart — all in one request cycle.

### End-to-End Data Flow

```
┌──────────────┐     POST /query      ┌──────────────────┐
│  React SPA   │ ──────────────────→  │  NLP Translator  │ (port 8001)
│  (Vite:5173) │                      │  + Input Guard   │
└──────────────┘                      └────────┬─────────┘
                                               │
                                  StructuredIntent (JSON)
                                               │
                                               ▼
                                      ┌──────────────────┐
                                      │ Orchestrator Hub │ (port 8002)
                                      │  (deterministic  │
                                      │   routing)       │
                                      └────────┬─────────┘
                                               │
                                  Dispatch to spoke agent(s)
                                               │
                                               ▼
                                      ┌──────────────────┐
                                      │   Spoke Agent    │ (port 8010)
                                      │  (deterministic  │
                                      │   data retrieval)│
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
                                      │  Renderer (LLM)  │
                                      └────────┬─────────┘
                                               │
                              RenderedOutput (Chart.js spec + BI insights)
                                               │
                                               ▼
                                      ┌──────────────────┐
                                      │  React SPA       │
                                      │  Chart.js render │
                                      └──────────────────┘
```

### Request Lifecycle (Step by Step)

1. **User submits query** — React SPA sends `POST /query` to NLP Translator (port 8001)
2. **Input guardrail** — Bedrock Guardrails checks content safety (parallel with NLP)
3. **NLP Translation** — Extracts keywords, resolves ontology entities, classifies query type (lookup/aggregation/comparison) via Claude Haiku
4. **Orchestrator dispatch** — Resolves which spoke agent(s) handle the entity_refs, dispatches concurrently via HTTP
5. **Spoke Agent retrieval** — Deterministic data fetch from S3 (JSON/CSV), no LLM needed
6. **Guardrail validation** — Schema check + Bedrock Guardrails output safety scan
7. **Visualization rendering** — Strands Agent analyzes data shape, generates Chart.js config with BI insights. Falls back to rule-based chart selection if LLM fails.
8. **Response returned** — Chart spec + stats + latency breakdown sent to frontend

### Service Inventory

| Service | Port | File | Uses LLM? | Framework |
|---------|------|------|-----------|-----------|
| NLP Translator | 8001 | `src/services/nlp_api.py` | Yes (Bedrock invoke_model) | FastAPI |
| Orchestrator Hub | 8002 | `src/services/orchestrator_api.py` | No (deterministic dispatch) | FastAPI + Strands (inactive) |
| Guardrail Layer | 8003 | `src/services/guardrail_api.py` | Yes (Bedrock Guardrails) | FastAPI |
| Visualization Renderer | 8004 | `src/services/visualization_api.py` | Yes (Strands Agent) | FastAPI + Strands |
| Spoke Agent | 8010 | `src/agents/spoke_agent.py` | No (deterministic S3 fetch) | FastAPI |

### Strands Agents in the System

Two services use the Strands SDK:

1. **Visualization Renderer** (actively using LLM) — A Strands `Agent` with a custom `emit_chart` tool. The agent receives normalized tabular data and produces a complete Chart.js configuration with analytical insights.

2. **Orchestrator Hub** (Strands available but inactive) — Has a Strands `Agent` configured with `check_result_cache`, `resolve_available_agents`, `dispatch_to_spoke_agent` tools. The **active code path** uses direct deterministic dispatch (no LLM). The Strands agent exists as a more intelligent fallback.

---

## 2. What is Amazon Bedrock AgentCore?

Amazon Bedrock AgentCore provides a managed runtime for deploying AI agents in production. Key capabilities:

- **Managed Runtime** — Auto-scaling, session management, idle timeout
- **Framework Agnostic** — Works with Strands Agents, LangGraph, CrewAI, or any custom agent
- **Built-in Observability** — Tracing, debugging, monitoring via CloudWatch
- **Security** — IAM-based auth, execution roles, network isolation options
- **Session Management** — Configurable idle timeouts and max lifetime per session

Source: [AWS AgentCore Documentation](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html)

---

## 3. AgentCore Runtime Contract Requirements

Every agent deployed to AgentCore must satisfy:

| Requirement | Details |
|-------------|---------|
| **`/invocations` endpoint** | POST — receives agent requests (REQUIRED) |
| **`/ping` endpoint** | GET — health check (REQUIRED) |
| **Docker container** | ARM64 architecture (`linux/arm64`) |
| **Port** | Application runs on port `8080` |
| **Credentials** | Strands agents need AWS credentials (provided by execution role) |

Content rephrased for compliance with licensing restrictions. Source: [AgentCore Custom Deploy Guide](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/getting-started-custom.html)

---

## 4. Deployment Strategy: Which Agents to Deploy on AgentCore

### Recommended Deployment Model

Given this system's architecture, the optimal AgentCore deployment targets the two LLM-powered services that benefit most from managed scaling:

| Component | Deploy to AgentCore? | Rationale |
|-----------|---------------------|-----------|
| **Visualization Renderer** | ✅ Yes (primary) | Strands Agent, LLM-heavy, 20-30s per cold call, benefits from session caching |
| **Orchestrator Hub** | ✅ Yes (if activating Strands path) | Has a Strands Agent with tools, currently using deterministic fallback |
| NLP Translator | ⚠️ Optional | Uses Bedrock `invoke_model` directly, not a Strands agent. Could be wrapped. |
| Guardrail Layer | ❌ No | Uses Bedrock Guardrails API, no Strands agent |
| Spoke Agent | ❌ No | Deterministic, no LLM. Deploy as normal container (ECS/Fargate) |
| Frontend | ❌ No | Static React SPA. Deploy to CloudFront/S3 |

### Proposed Architecture on AWS

```
┌─────────────────────────────────┐
│         CloudFront + S3         │  ← React SPA (frontend/dist)
└────────────────┬────────────────┘
                 │ POST /query
                 ▼
┌─────────────────────────────────┐
│     ECS Fargate / Lambda        │  ← NLP Translator (port 8001)
│  (or AgentCore if wrapped)      │     + Input Guardrail
└────────────────┬────────────────┘
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
┌──────────┐ ┌────────┐ ┌─────────────────────────┐
│Orchestrat│ │Guardrail│ │  AgentCore Runtime      │
│Hub (ECS) │ │(ECS)   │ │  Visualization Renderer │
└─────┬────┘ └────────┘ │  (Strands Agent)        │
      │                  └─────────────────────────┘
      ▼
┌──────────┐
│Spoke Agent│  ← ECS Fargate (deterministic S3 fetch)
│  (ECS)   │
└──────────┘
```

---

## 5. What's Required to Deploy on AgentCore

### 5.1 Prerequisites

- AWS Account with Bedrock AgentCore access (us-east-1 or us-west-2)
- Python 3.10+
- Docker with buildx (for ARM64 cross-compilation)
- ECR repository for container images
- IAM execution role with AgentCore trust policy
- `BedrockAgentCoreFullAccess` managed policy attached to deployer identity

### 5.2 IAM Execution Role

The AgentCore runtime needs an execution role. This role must have:

**Trust policy** (allows AgentCore service to assume it):
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "bedrock-agentcore.amazonaws.com" },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": { "aws:SourceAccount": "<ACCOUNT_ID>" },
      "ArnLike": { "aws:SourceArn": "arn:aws:bedrock-agentcore:<REGION>:<ACCOUNT_ID>:*" }
    }
  }]
}
```

**Permissions policy** (what the agent can do at runtime):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
      "Resource": [
        "arn:aws:bedrock:<REGION>::foundation-model/us.anthropic.claude-3-5-haiku-*",
        "arn:aws:bedrock:<REGION>::foundation-model/amazon.titan-embed-text-v2*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["bedrock:ApplyGuardrail"],
      "Resource": "arn:aws:bedrock:<REGION>:<ACCOUNT_ID>:guardrail/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::visualization-poc-bucket",
        "arn:aws:s3:::visualization-poc-bucket/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:<REGION>:<ACCOUNT_ID>:log-group:/aws/bedrock-agentcore/*"
    }
  ]
}
```

Content rephrased for compliance with licensing restrictions. Source: [AgentCore IAM Permissions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html)

### 5.3 Adapting the Visualization Renderer for AgentCore

The current renderer runs on port 8004 with endpoints `/health` and `/internal/render`. AgentCore requires port 8080 with `/ping` and `/invocations`. Here's what needs to change:

**Current endpoints:**
- `GET /health` → must become `GET /ping`
- `POST /internal/render` → must become `POST /invocations`

**Required adapter code** (`agentcore_app.py`):

```python
"""AgentCore-compatible wrapper for the Visualization Renderer."""
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any

from src.models.shared import OrchestratorResponse, StructuredIntent
from src.services.visualization_renderer import VisualizationRenderer

app = FastAPI(title="Visualization Renderer — AgentCore", version="1.0.0")
renderer = VisualizationRenderer()


class InvocationRequest(BaseModel):
    input: dict[str, Any]


@app.get("/ping")
async def ping():
    return {"status": "healthy"}


@app.post("/invocations")
async def invocations(request: InvocationRequest):
    """AgentCore invocation endpoint.
    
    Expected input format:
    {
      "input": {
        "validated_response": { ... OrchestratorResponse dict ... },
        "structured_intent": { ... StructuredIntent dict ... }
      }
    }
    """
    try:
        data = request.input
        response = OrchestratorResponse.model_validate(data["validated_response"])
        intent = StructuredIntent.model_validate(data["structured_intent"])

        intent_metadata = {
            "query_id": str(intent.query_id),
            "query_type": intent.query_type,
            "query_text": intent.routing_metadata.get("query_text", ""),
            "requested_chart_type": intent.routing_metadata.get("requested_chart_type"),
        }

        rendered = await renderer.render(response, intent_metadata)
        return JSONResponse(
            status_code=200,
            content={"output": rendered.model_dump(mode="json")},
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"output": {"error": str(e)}},
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

### 5.4 Dockerfile (ARM64)

```dockerfile
# ARM64 base image required by AgentCore
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-cache

# Copy application code
COPY src/ ./src/
COPY agentcore_app.py ./

# Expose AgentCore's required port
EXPOSE 8080

# Run the AgentCore-adapted application
CMD ["uv", "run", "uvicorn", "agentcore_app:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 5.5 Build & Push to ECR

```bash
# Create ECR repository
aws ecr create-repository \
  --repository-name viz-renderer-agentcore \
  --region us-east-1

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Build ARM64 image and push
docker buildx build --platform linux/arm64 \
  -t <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/viz-renderer-agentcore:latest \
  --push .
```

### 5.6 Deploy to AgentCore Runtime

```python
"""Deploy the Visualization Renderer to AgentCore Runtime."""
import boto3

client = boto3.client('bedrock-agentcore-control', region_name='us-east-1')

response = client.create_agent_runtime(
    agentRuntimeName='visualization-renderer',
    agentRuntimeArtifact={
        'containerConfiguration': {
            'containerUri': '<ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/viz-renderer-agentcore:latest'
        }
    },
    networkConfiguration={"networkMode": "PUBLIC"},
    roleArn='arn:aws:iam::<ACCOUNT_ID>:role/VizRendererAgentCoreRole',
    lifecycleConfiguration={
        'idleRuntimeSessionTimeout': 300,   # 5 min idle before shutdown
        'maxLifetime': 1800                  # 30 min max session
    },
)

print(f"Agent Runtime ARN: {response['agentRuntimeArn']}")
print(f"Status: {response['status']}")
```

### 5.7 Invoke the Deployed Agent

```python
"""Invoke the deployed Visualization Renderer via AgentCore."""
import boto3
import json

client = boto3.client('bedrock-agentcore', region_name='us-east-1')

payload = json.dumps({
    "input": {
        "validated_response": {
            "query_id": "abc-123",
            "results": [{
                "status": "success",
                "payload": {
                    "data_type": "comparison",
                    "group_by": "category",
                    "columns": ["revenue", "orders"],
                    "groups": {
                        "Electronics": {"revenue": {"sum": 3600000}, "orders": {"sum": 12400}, "count": 4},
                        "Office": {"revenue": {"sum": 890000}, "orders": {"sum": 31600}, "count": 4}
                    },
                    "row_count": 8
                },
                "agent_id": "spoke-agent",
                "data_source": "financial_data.json"
            }],
            "unavailable_agents": []
        },
        "structured_intent": {
            "query_id": "abc-123",
            "query_type": "comparison",
            "entity_refs": ["ontology:sales_revenue"],
            "routing_metadata": {"query_text": "compare revenue by category"},
            "timestamp": "2026-06-09T10:00:00Z"
        }
    }
})

response = client.invoke_agent_runtime(
    agentRuntimeArn='arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:runtime/visualization-renderer-xxx',
    runtimeSessionId='viz-session-' + 'a' * 30,  # Must be 33+ chars
    payload=payload,
    qualifier="DEFAULT"
)

result = json.loads(response['response'].read())
print(json.dumps(result, indent=2))
```

---

## 6. Migration Checklist

### Phase 1: Prepare (No code changes to existing system)

- [ ] Create ECR repository for the viz renderer
- [ ] Create IAM execution role with trust + permissions policies
- [ ] Enable CloudWatch Transaction Search for AgentCore observability
- [ ] Verify Bedrock model access in the target region

### Phase 2: Adapt & Test Locally

- [ ] Create `agentcore_app.py` adapter (maps `/ping` + `/invocations`)
- [ ] Create ARM64 Dockerfile
- [ ] Build and test locally: `docker run --platform linux/arm64 -p 8080:8080 ...`
- [ ] Verify `/ping` returns 200
- [ ] Verify `/invocations` produces valid Chart.js configs

### Phase 3: Deploy

- [ ] Push ARM64 image to ECR
- [ ] Run `create_agent_runtime` to deploy
- [ ] Test invocation via AWS SDK
- [ ] Update the NLP Translator to call AgentCore instead of `http://localhost:8004`
- [ ] Monitor via CloudWatch Transaction Search

### Phase 4: Production Hardening

- [ ] Configure session timeout based on observed latency patterns
- [ ] Set up IAM policies following least-privilege principle
- [ ] Add retry logic in NLP Translator for AgentCore invocations
- [ ] Set up CloudWatch alarms for error rates
- [ ] Consider deploying Orchestrator Hub to AgentCore (if re-enabling Strands path)

---

## 7. Key Considerations

### Service Communication Changes

Currently, all services communicate via HTTP on localhost. In a distributed deployment:

- **NLP Translator** (entry point) must call AgentCore's `invoke_agent_runtime` SDK method instead of `POST http://localhost:8004/internal/render`
- The `httpx` call in `nlp_api.py` needs to be replaced with a boto3 `bedrock-agentcore` client call
- Session IDs should map to the user's query session for cache benefits

### Environment Variables

The AgentCore container needs these environment variables (or they'll come from the execution role):

| Variable | Purpose |
|----------|---------|
| `AWS_REGION` | Region for Bedrock calls (us-east-1) |
| `S3_BUCKET` | Data source bucket name |
| `DEFAULT_MODEL_ID` | Claude model for visualization agent |
| `BEDROCK_GUARDRAIL_ID` | Guardrail identifier (if renderer validates) |

### Cost Implications

- AgentCore charges per invocation + compute time
- The renderer's LRU cache resets on cold start — consider using AgentCore's shared memory or DynamoDB-backed cache for persistence
- Session keepalive (`idleRuntimeSessionTimeout`) trades cost for latency — 5 min is a good starting point

### What Stays the Same

- The Strands Agent code (`VisualizationRenderer` class) is unchanged
- The `emit_chart` tool, system prompt, and fallback logic all work as-is
- Only the HTTP wrapper (FastAPI routing) changes for AgentCore compatibility
