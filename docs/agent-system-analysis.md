# Conversational BI — Agent System Analysis & Deployment Guide

## Part A: Current Agent Architecture

The system follows a **hub-and-spoke** pattern with 5 distinct services, 3 of which use LLM reasoning (Strands SDK or direct Bedrock calls):

### Service Map

| Service | Port | Role | LLM Usage |
|---------|------|------|-----------|
| **NLP Translator** | 8001 | Gateway — translates NL queries → StructuredIntent, orchestrates the full pipeline | Direct Bedrock Claude call for query-type classification (`lookup` / `aggregation` / `comparison`) |
| **Orchestrator Hub** | 8002 | Routes StructuredIntents to spoke agents based on entity_ref matching | Strands Agent instance with 3 tools — but **currently bypassed** (see Part B) |
| **Guardrail Layer** | 8003 | Validates orchestrator responses against schema + Bedrock Guardrails content filter | Bedrock ApplyGuardrail API (not LLM reasoning — ML content classification) |
| **Visualization Renderer** | 8004 | Transforms validated data into Chart.js configs | Strands Agent with `emit_chart` tool — **falls back to deterministic builder** frequently |
| **Spoke Agent** | 8010 | Queries S3 data sources (JSON financial data + CSV product catalog) | **None** — purely deterministic entity_ref-based routing |

### Data Flow

```
User Query
    │
    ▼
┌─────────────────────┐
│  NLP Translator     │  Bedrock Claude: classify query type
│  (port 8001)        │  Ontology Store: resolve entity_refs
└────────┬────────────┘
         │ POST /internal/process
         ▼
┌─────────────────────┐
│  Orchestrator Hub   │  Resolves agents by entity_ref overlap
│  (port 8002)        │  Dispatches to spoke agents via HTTP
└────────┬────────────┘
         │ POST /agents/spoke-agent/invoke
         ▼
┌─────────────────────┐
│  Spoke Agent        │  Deterministic S3 queries
│  (port 8010)        │  (financial_data.json / product_catalog.csv)
└────────┬────────────┘
         │ Results bubble back up
         ▼
┌─────────────────────┐
│  Guardrail Layer    │  Schema validation + Bedrock Guardrails
│  (port 8003)        │  (content policy filtering)
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Visualization      │  Strands Agent: emit_chart tool
│  Renderer (8004)    │  Fallback: deterministic Chart.js builder
└─────────────────────┘
         │
         ▼
    Rendered Chart.js config → Frontend
```

### Agent Capabilities Summary

**1. NLP Translator (Gateway Agent)**
- Extracts keywords from natural language, resolves against Ontology Store
- Classifies query type via Bedrock Claude (lookup/aggregation/comparison)
- Extracts chart-type hints from user query (regex-based)
- Caches classification results (LRU, 1000 entries)
- Parallel execution: entity resolution + history bias run concurrently

**2. Orchestrator Hub (Routing Agent)**
- Maintains in-memory agent registry (register/deregister at runtime)
- Checks result cache before dispatching
- Resolves agents by entity_ref set intersection
- Dispatches structured intents via HTTP POST to spoke agents
- Has a Strands Agent with tools: `check_result_cache`, `resolve_available_agents`, `dispatch_to_spoke_agent`

**3. Guardrail Layer (Validation Agent)**
- Schema validation (structural correctness)
- Bedrock Guardrails `ApplyGuardrail` API with source=OUTPUT
- LRU cache for guardrail results (500 entries)
- Fail-open on Bedrock unavailability

**4. Visualization Renderer (Rendering Agent)**
- Strands Agent prompted to call `emit_chart` with Chart.js config
- Receives normalized tabular data + user query context
- LRU cache for rendered outputs (200 entries)
- Deterministic fallback builds charts from data shape

**5. Spoke Agent (Data Agent)**
- Purely deterministic — no LLM
- Queries S3-hosted JSON/CSV files
- Supports lookup, aggregation, comparison query types
- Entity_ref-based source routing (financial vs. product entities)

---

## Part B: Agents That Don't Execute Agentically (Rely on Fallbacks)

### 1. Orchestrator Hub — Strands Agent Completely Bypassed

**What happens:** The `OrchestratorHub.process_intent()` method calls `_direct_dispatch()` instead of `_agent_dispatch()`. The Strands Agent (with its LLM reasoning about which agents to call) is **never invoked** in the actual request path.

**Evidence from code:**
```python
# In process_intent():
# Step 3: Direct dispatch to all resolved agents (Requirement 4.4)
return self._direct_dispatch(intent, resolved_agents, cache_key)
```

The `_agent_dispatch()` method exists but is dead code — it's never called from `process_intent()`.

**Why this occurs:**
- The NLP Translator already resolves entity_refs deterministically. By the time the orchestrator receives the intent, the target agents are already known.
- Direct dispatch is faster (no LLM round-trip), cheaper, and more predictable.
- The system was likely prototyped with LLM routing, then optimized to deterministic dispatch once entity_ref resolution proved sufficient.
- The fallback inside `_build_response_from_results()` shows even the Strands path had reliability issues — if the LLM didn't call `dispatch_to_spoke_agent`, it fell back to dispatching to all agents anyway.

**Impact:** The Orchestrator's "intelligence" adds zero value — it's a glorified HTTP dispatcher with a registry lookup.

### 2. Visualization Renderer — Agent Path Frequently Falls Back

**What happens:** The Strands Agent is invoked but frequently fails to produce a valid `emit_chart` call, triggering the deterministic `_deterministic_render()` fallback.

**Evidence from code:**
```python
try:
    result = await self._agent_render(...)
except Exception as exc:
    logger.warning(json.dumps({"event": "agent_render_failed", ...}))
    result = self._deterministic_render(...)
```

Additionally, inside `_agent_render()` itself:
```python
chart_spec = self._extract_emit_chart(agent_text)
if chart_spec and "chart_config" in chart_spec:
    # success path
else:
    # Agent didn't produce a valid emit_chart — fall back deterministically
    logger.warning(json.dumps({"event": "emit_chart_not_found_in_agent_response"}))
    return self._deterministic_render(...)
```

**Why this occurs:**
- **Syntax error in the code:** Line with `track_agent_invocation(...)` has a stray `x` at the end (`logger.warning(f"Visualization cost tracking failed: {e}")x`), which causes a `SyntaxError` — the entire module may fail to import cleanly in some contexts.
- The Strands Agent must output valid JSON in a specific format (`emit_chart` tool result). LLMs occasionally produce malformed JSON, miss required fields, or respond with text instead of calling the tool.
- The `_extract_emit_chart()` parser searches for JSON blobs containing `chart_config` in free-text agent output — this is fragile.
- Network/throttling errors from Bedrock trigger the outer exception handler.

### 3. NLP Translator — Classification Can Fail Silently

**What happens:** If Bedrock is unavailable or the LLM response is unparseable, `classify_query_type` returns `None`, which causes `translate()` to return an `AMBIGUOUS_INTENT` error to the user.

**Evidence:**
```python
query_type = self.classifier.classify_query_type(query_text, ontology_context)
if query_type is None:
    return NLPError(error_code="AMBIGUOUS_INTENT", ...)
```

**Why this occurs:**
- No local fallback classification exists. If Bedrock is throttled, down, or returns garbage, the entire query fails.
- The classifier doesn't have a rule-based fallback that could use keyword heuristics (e.g., "total", "sum" → aggregation, "compare" → comparison).

### Summary Table

| Agent | Intended Behavior | Actual Behavior | Root Cause |
|-------|-------------------|-----------------|------------|
| Orchestrator Hub | LLM reasons about which agents to call | Direct dispatch to all resolved agents (LLM never called) | Entity_ref resolution makes LLM routing redundant; direct dispatch is faster |
| Visualization Renderer | LLM generates Chart.js config via `emit_chart` tool | Frequently falls back to deterministic chart builder | LLM output parsing fragility, potential syntax error in module, Bedrock failures |
| NLP Translator | LLM classifies query type | Returns error if LLM fails (no fallback) | No heuristic fallback classifier |

---

## Part C: Making Agents Truly Agentic

### Strategy: Graduated Autonomy

The goal isn't to make everything LLM-powered — it's to make agents that **reason when reasoning adds value** and fall back gracefully when it doesn't.

### 1. Orchestrator Hub → Intelligent Multi-Agent Routing

**Current state:** Dumb dispatch to all resolved agents.

**Agentic redesign:**

```python
# The orchestrator should reason about:
# 1. Whether the query needs data from one source or multiple
# 2. Whether results should be merged, compared, or filtered
# 3. Whether a previous partial result answers the query already

ORCHESTRATOR_SYSTEM_PROMPT = """
You are a query routing agent. Given a structured intent and available agents:
1. Determine the MINIMUM set of agents needed
2. Decide the dispatch strategy (parallel vs sequential)
3. If results from Agent A inform whether Agent B is needed, dispatch sequentially
4. Merge or select results based on the user's actual question
"""
```

**Key changes:**
- Actually call `_agent_dispatch()` from `process_intent()` — but only for complex queries (comparison across domains)
- Keep direct dispatch for single-domain queries (fast path)
- Add a complexity classifier: single-entity queries → direct; multi-entity → agent reasoning
- Make the agent capable of **selective merge** (not just concatenation)

```python
async def process_intent(self, intent, correlation_id=""):
    # Fast path: single-domain query
    if self._is_single_domain(intent):
        return self._direct_dispatch(intent, resolved_agents, cache_key)
    
    # Agentic path: multi-domain or ambiguous routing
    return self._agent_dispatch(intent, resolved_agents, cache_key)
```

### 2. Visualization Renderer → Reliable Agent with Structured Output

**Current state:** Agent sometimes produces valid Chart.js; falls back to deterministic builder.

**Agentic redesign:**

- **Use structured output / tool-use constraints:** Configure the Strands Agent so `emit_chart` is the ONLY way it can respond (force tool use). The Strands SDK supports `tool_choice` configuration.
- **Validate before accepting:** Parse and validate the Chart.js config against a schema before accepting it.
- **Retry with feedback:** If the first attempt produces invalid JSON, retry once with the error message as feedback.
- **Fix the syntax error:** Remove the stray `x` on the tracking line.

```python
# Force tool use — agent MUST call emit_chart
self._agent = Agent(
    system_prompt=VISUALIZER_SYSTEM_PROMPT,
    tools=[emit_chart],
    tool_choice={"tool": "emit_chart"},  # Force this tool
    callback_handler=None,
    model=get_strands_bedrock_model(model_id, max_tokens=2000),
)
```

```python
# Retry pattern with structured validation
async def _agent_render(self, ...):
    for attempt in range(2):
        agent_result = self._agent(prompt)
        chart_spec = self._extract_emit_chart(str(agent_result))
        if chart_spec and self._validate_chartjs(chart_spec["chart_config"]):
            return self._build_rendered_output(chart_spec, metadata, stats_text)
        # Retry with error feedback
        prompt += f"\n\nYour previous response was invalid: {self._last_error}. Try again."
    
    return self._deterministic_render(...)  # Only after 2 failed attempts
```

### 3. NLP Translator → Resilient Classification with Heuristic Fallback

**Current state:** Returns error if Bedrock is unavailable.

**Agentic redesign:**

- Add a rule-based fallback classifier that uses keyword patterns
- Make the LLM path the primary (better accuracy) and the rule-based path the fallback
- Log when fallback is used for monitoring

```python
def classify_query_type(self, query_text, ontology_context):
    # Try LLM classification first
    llm_result = self._llm_classify(query_text, ontology_context)
    if llm_result:
        return llm_result
    
    # Fallback: keyword-based heuristic
    return self._heuristic_classify(query_text)

def _heuristic_classify(self, query_text: str) -> str:
    text = query_text.lower()
    aggregation_signals = ["total", "sum", "average", "avg", "count", "how many", "trend", "over time"]
    comparison_signals = ["compare", "versus", "vs", "difference", "between", "against"]
    
    if any(s in text for s in comparison_signals):
        return "comparison"
    if any(s in text for s in aggregation_signals):
        return "aggregation"
    return "lookup"  # Safe default
```

### 4. Spoke Agent → Add Tool-Use Capability for Complex Queries

**Current state:** Purely deterministic — fine for simple lookups but can't handle follow-up reasoning.

**Agentic redesign for AgentCore:**

When deployed on AgentCore, the spoke agent should become a Strands Agent with tools:
- `query_financial_data` (existing function, promoted to tool)
- `query_product_catalog` (existing function, promoted to tool)
- `filter_results` (new tool for post-query filtering)
- `compute_derived_metric` (new tool for calculations like growth rate, percentage)

This lets the agent handle queries like "what's the revenue growth rate quarter over quarter" by calling the data tool, then computing the derived metric.

### Architecture Summary After Redesign

```
┌──────────────────────────────────────────────────────────┐
│                    When to be Agentic?                     │
├──────────────────┬───────────────────────────────────────┤
│ NLP Translator   │ Always (LLM classify) + heuristic     │
│                  │ fallback on failure                     │
├──────────────────┼───────────────────────────────────────┤
│ Orchestrator     │ Only for multi-domain queries;         │
│                  │ fast deterministic path for simple      │
├──────────────────┼───────────────────────────────────────┤
│ Visualization    │ Always (forced tool-use) with           │
│                  │ retry + validation                      │
├──────────────────┼───────────────────────────────────────┤
│ Spoke Agent      │ Deterministic locally; agentic on       │
│                  │ AgentCore for complex derived queries    │
├──────────────────┼───────────────────────────────────────┤
│ Guardrail        │ Keep as-is (ML classifier, not          │
│                  │ agent reasoning)                         │
└──────────────────┴───────────────────────────────────────┘
```

---

## Part D: Deploying Agents on Amazon Bedrock AgentCore & Connecting to Frontend

### Overview

Amazon Bedrock AgentCore is a managed runtime for deploying AI agents. It handles:
- Agent hosting and scaling
- Tool orchestration and memory
- Secure credential management
- Observability and tracing

### Architecture on AgentCore

```
┌──────────────┐       ┌──────────────────────────────────────────────┐
│   Frontend   │       │           Amazon Bedrock AgentCore            │
│   (React)    │◄─────►│                                              │
│              │       │  ┌─────────────────────────────────────────┐  │
└──────────────┘       │  │  Gateway Agent (NLP Translator)         │  │
       │               │  │  - Query classification                 │  │
       │  HTTPS        │  │  - Entity resolution                    │  │
       ▼               │  │  - Pipeline orchestration               │  │
┌──────────────┐       │  └──────────┬──────────────────────────────┘  │
│  API Gateway │───────│             │                                  │
│  (REST/WS)   │       │  ┌──────────▼──────────────────────────────┐  │
└──────────────┘       │  │  Orchestrator Agent                     │  │
                       │  │  - Multi-agent routing                  │  │
                       │  │  - Result merging                       │  │
                       │  └──────────┬──────────────────────────────┘  │
                       │             │                                  │
                       │  ┌──────────▼──────────────────────────────┐  │
                       │  │  Spoke Agent(s)                         │  │
                       │  │  - Data retrieval tools                 │  │
                       │  │  - S3 access                            │  │
                       │  └──────────┬──────────────────────────────┘  │
                       │             │                                  │
                       │  ┌──────────▼──────────────────────────────┐  │
                       │  │  Visualization Agent                    │  │
                       │  │  - Chart generation (emit_chart tool)   │  │
                       │  └─────────────────────────────────────────┘  │
                       │                                                │
                       │  ┌─────────────────────────────────────────┐  │
                       │  │  Guardrail (Bedrock Guardrails native)  │  │
                       │  └─────────────────────────────────────────┘  │
                       └────────────────────────────────────────────────┘
```

### Step-by-Step Deployment Guide

#### Prerequisites

1. AWS Account with Bedrock AgentCore access enabled
2. AWS CLI v2 configured with appropriate IAM permissions
3. S3 bucket with data sources already uploaded (you have `visualization-poc-bucket`)
4. Bedrock model access enabled for Claude 3.5 Haiku

#### Step 1: Define Agent Schemas

Each agent needs a schema definition that AgentCore uses to understand its tools and capabilities.

**NLP Gateway Agent — `agents/nlp-gateway/agent.yaml`:**
```yaml
name: nlp-gateway-agent
description: "Translates natural language queries into structured intents and orchestrates the BI pipeline"
model: us.anthropic.claude-3-5-haiku-20241022-v1:0
instructions: |
  You are the gateway for a conversational BI system. Your job:
  1. Parse the user's natural language query
  2. Resolve entity references against the ontology
  3. Classify the query type (lookup, aggregation, comparison)
  4. Route to the appropriate downstream agent

tools:
  - name: resolve_entities
    description: "Resolve ontology entity references from keywords"
    parameters:
      query_text:
        type: string
        required: true

  - name: classify_query
    description: "Classify query type based on text and context"
    parameters:
      query_text:
        type: string
        required: true
      entity_refs:
        type: array
        items: string
        required: true

  - name: invoke_orchestrator
    description: "Send structured intent to the orchestrator agent"
    parameters:
      structured_intent:
        type: object
        required: true

guardrails:
  id: unf4323uxnff
  version: DRAFT
```

**Orchestrator Agent — `agents/orchestrator/agent.yaml`:**
```yaml
name: orchestrator-agent
description: "Routes structured intents to spoke agents and merges results"
model: us.anthropic.claude-3-5-haiku-20241022-v1:0
instructions: |
  You route data queries to the correct spoke agents based on entity_refs.
  For single-domain queries, dispatch directly.
  For cross-domain comparisons, dispatch to multiple agents and merge.

tools:
  - name: dispatch_to_agent
    description: "Dispatch a structured intent to a specific spoke agent"
    parameters:
      agent_id:
        type: string
        required: true
      structured_intent:
        type: object
        required: true

  - name: merge_results
    description: "Merge results from multiple agents into unified response"
    parameters:
      results:
        type: array
        items: object
        required: true
```

**Data Spoke Agent — `agents/spoke-data/agent.yaml`:**
```yaml
name: spoke-data-agent
description: "Queries financial and product data from S3"
model: us.anthropic.claude-3-5-haiku-20241022-v1:0
instructions: |
  You retrieve data from S3-hosted sources. Use the appropriate tool
  based on the entity_refs in the structured intent.

tools:
  - name: query_financial_data
    description: "Query financial JSON data for sales/revenue metrics"
    parameters:
      query_type:
        type: string
        enum: [lookup, aggregation, comparison]
        required: true
      entity_refs:
        type: array
        items: string
        required: true

  - name: query_product_catalog
    description: "Query product catalog CSV for product information"
    parameters:
      query_type:
        type: string
        enum: [lookup, aggregation, comparison]
        required: true
      entity_refs:
        type: array
        items: string
        required: true
```

**Visualization Agent — `agents/visualization/agent.yaml`:**
```yaml
name: visualization-agent
description: "Generates Chart.js configurations from data"
model: us.anthropic.claude-3-5-haiku-20241022-v1:0
instructions: |
  You are a data visualization expert. Given tabular data and a user query,
  produce a Chart.js v4 configuration by calling emit_chart exactly once.

tools:
  - name: emit_chart
    description: "Emit a complete Chart.js chart configuration"
    parameters:
      chart_config:
        type: string
        description: "Complete Chart.js JSON config"
        required: true
      title:
        type: string
        required: true
      description:
        type: string
        required: true

tool_choice:
  tool: emit_chart  # Force the agent to always use this tool
```

#### Step 2: Package Agent Code

Each agent's business logic is packaged as a Lambda-compatible handler or container.

**Directory structure:**
```
agentcore-deployment/
├── agents/
│   ├── nlp-gateway/
│   │   ├── agent.yaml
│   │   ├── handler.py
│   │   └── requirements.txt
│   ├── orchestrator/
│   │   ├── agent.yaml
│   │   ├── handler.py
│   │   └── requirements.txt
│   ├── spoke-data/
│   │   ├── agent.yaml
│   │   ├── handler.py
│   │   └── requirements.txt
│   └── visualization/
│       ├── agent.yaml
│       ├── handler.py
│       └── requirements.txt
├── infrastructure/
│   ├── template.yaml          # SAM/CloudFormation
│   └── agentcore-config.json
└── frontend/
    └── src/api/queryApi.ts    # Updated to point to AgentCore endpoint
```

**Example handler (spoke-data/handler.py):**
```python
"""AgentCore handler for the Data Spoke Agent."""
import json
import boto3

s3 = boto3.client("s3")
BUCKET = "visualization-poc-bucket"

def query_financial_data(query_type: str, entity_refs: list[str]) -> dict:
    """Tool implementation — same logic as current spoke_agent.py."""
    response = s3.get_object(Bucket=BUCKET, Key="data-sources/financial_data.json")
    data = json.loads(response["Body"].read().decode())
    rows = data.get("rows", [])
    columns = data.get("columns", [])
    filtered = _filter_rows(rows, entity_refs)
    return _execute_query(query_type, filtered, columns)

def query_product_catalog(query_type: str, entity_refs: list[str]) -> dict:
    """Tool implementation — same logic as current spoke_agent.py."""
    # ... (same as existing implementation)
    pass
```

#### Step 3: Deploy with AWS CLI / CDK

**Using AWS CDK (recommended):**

```typescript
// infrastructure/lib/agentcore-stack.ts
import * as cdk from 'aws-cdk-lib';
import * as bedrock from 'aws-cdk-lib/aws-bedrock';

export class AgentCoreStack extends cdk.Stack {
  constructor(scope: cdk.App, id: string) {
    super(scope, id);

    // Spoke Data Agent
    const spokeAgent = new bedrock.CfnAgent(this, 'SpokeDataAgent', {
      agentName: 'spoke-data-agent',
      foundationModel: 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
      instruction: 'You retrieve data from S3-hosted sources...',
      agentResourceRoleArn: agentRole.roleArn,
    });

    // Visualization Agent
    const vizAgent = new bedrock.CfnAgent(this, 'VisualizationAgent', {
      agentName: 'visualization-agent',
      foundationModel: 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
      instruction: 'You are a data visualization expert...',
      agentResourceRoleArn: agentRole.roleArn,
    });

    // Gateway Agent (orchestrates the others)
    const gatewayAgent = new bedrock.CfnAgent(this, 'GatewayAgent', {
      agentName: 'nlp-gateway-agent',
      foundationModel: 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
      instruction: 'You are the gateway for a conversational BI system...',
      agentResourceRoleArn: agentRole.roleArn,
    });
  }
}
```

#### Step 4: Create API Gateway Endpoint

The frontend needs a single HTTPS endpoint to talk to the deployed agents:

```typescript
// infrastructure/lib/api-stack.ts
const api = new apigateway.RestApi(this, 'BiAgentApi', {
  restApiName: 'conversational-bi-api',
  defaultCorsPreflightOptions: {
    allowOrigins: apigateway.Cors.ALL_ORIGINS,
    allowMethods: ['POST', 'OPTIONS'],
  },
});

const queryResource = api.root.addResource('query');
queryResource.addMethod('POST', new apigateway.LambdaIntegration(
  gatewayLambda  // Lambda that invokes the AgentCore gateway agent
));
```

#### Step 5: Update Frontend API Client

**`frontend/src/api/queryApi.ts` changes:**

```typescript
// Before (localhost):
const API_BASE = 'http://localhost:8001';

// After (AgentCore via API Gateway):
const API_BASE = import.meta.env.VITE_API_URL || 'https://abc123.execute-api.us-east-1.amazonaws.com/prod';

export async function submitQuery(queryText: string): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query_text: queryText }),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new ApiError(response.status, error);
  }
  
  return response.json();
}
```

#### Step 6: Environment Configuration

```bash
# .env.production
VITE_API_URL=https://your-api-id.execute-api.us-east-1.amazonaws.com/prod

# .env.development (keep local)
VITE_API_URL=http://localhost:8001
```

### Guardrails Integration

Bedrock Guardrails integrate natively with AgentCore — no separate service needed:

```yaml
# In each agent.yaml:
guardrails:
  id: unf4323uxnff
  version: DRAFT
  # Applied automatically to all agent I/O
```

This replaces the standalone Guardrail Layer service (port 8003).

### Monitoring & Observability on AgentCore

AgentCore provides built-in:
- **CloudWatch Metrics:** Invocation count, latency, token usage
- **X-Ray Tracing:** End-to-end request tracing across agents
- **CloudWatch Logs:** Structured agent logs

### Cost Comparison

| Component | Current (Self-hosted) | AgentCore |
|-----------|----------------------|-----------|
| Compute | 5 FastAPI processes on EC2/ECS | Serverless (pay per invocation) |
| Scaling | Manual | Automatic |
| Bedrock calls | Same | Same (pricing unchanged) |
| Infra management | You | AWS managed |
| Cold start | None (always-on) | ~1-2s first request |

### Migration Checklist

- [ ] Package each agent's tool logic as standalone functions
- [ ] Create agent.yaml definitions for each agent
- [ ] Deploy agents via CDK/CloudFormation
- [ ] Create API Gateway endpoint
- [ ] Update frontend `queryApi.ts` to use new endpoint
- [ ] Configure Bedrock Guardrails at agent level
- [ ] Set up CloudWatch alarms for error rates
- [ ] Test end-to-end with production data
- [ ] Cutover DNS / update VITE_API_URL

---

## Quick Reference: Service Port Map (Local Development)

| Service | Port | Health Check |
|---------|------|-------------|
| NLP Translator | 8001 | GET /health |
| Orchestrator Hub | 8002 | GET /health |
| Guardrail Layer | 8003 | GET /health |
| Visualization Renderer | 8004 | GET /health |
| Spoke Agent | 8010 | GET /health |

---

## Appendix: Changes Applied to Make Agents Agentic

### Files Modified

1. **`src/services/visualization_renderer.py`**
   - Added `MAX_AGENT_RETRIES = 2` class constant
   - Replaced `_agent_render()` + silent fallback with `_agent_render_with_retry()` that:
     - Retries up to 2 times with error feedback to the agent
     - Validates Chart.js config structure before accepting (`_validate_chart_config()`)
     - Returns an error RenderedOutput on total failure (no silent fallback)
   - Commented out `_deterministic_render()` — the agent MUST succeed
   - The deterministic code remains available as comments for easy re-enablement

2. **`src/services/orchestrator_hub.py`**
   - `process_intent()` now uses intelligent dispatch strategy:
     - Multi-domain comparison queries → `_agent_dispatch()` (LLM reasoning)
     - Single-domain queries → `_direct_dispatch()` (fast path, no LLM)
   - The Strands Agent is no longer dead code — it activates for complex queries

3. **`src/services/nlp_translator.py`**
   - `classify_query_type()` now NEVER returns `None`
   - Added `_heuristic_classify()` keyword-based fallback
   - If Bedrock fails or returns garbage → heuristic takes over
   - Removed the `AMBIGUOUS_INTENT` error case from `translate()` since classification always succeeds
