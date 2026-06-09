# Deploying the Visualization Agent to Amazon Bedrock AgentCore via Console

This guide covers deploying the Visualization Renderer agent (the `viz_agent`) to Amazon Bedrock AgentCore using the AWS Management Console, and integrating the deployed agent with the existing Conversational BI project.

> **Why Console?** The locally installed AWS CLI is not the latest version and may lack AgentCore commands. The console provides full access without CLI version dependencies.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Prepare the Agent Code](#prepare-the-agent-code)
3. [Create the Agent in Bedrock Console](#create-the-agent-in-bedrock-console)
4. [Define the Action Group (emit_chart tool)](#define-the-action-group-emit_chart-tool)
5. [Configure the Lambda Function](#configure-the-lambda-function)
6. [Test the Agent in Console](#test-the-agent-in-console)
7. [Create an Agent Alias for Production](#create-an-agent-alias-for-production)
8. [Integrate with the Project Backend](#integrate-with-the-project-backend)
9. [Integrate with the Frontend](#integrate-with-the-frontend)
10. [Environment Configuration](#environment-configuration)
11. [Rollback Strategy](#rollback-strategy)

---

## Prerequisites

- AWS account with Bedrock access enabled in `us-east-1`
- Bedrock model access granted for `us.anthropic.claude-3-5-haiku-20241022-v1:0`
- IAM permissions: `bedrock:*`, `lambda:*`, `iam:CreateRole`, `iam:AttachRolePolicy`, `s3:GetObject`
- The S3 bucket `visualization-poc-bucket` with data sources already uploaded
- Existing Bedrock Guardrail ID: `joes1p3j7sa4` (DRAFT version)

---

## Prepare the Agent Code

Before going to the console, package the visualization logic as a Lambda function.

### Lambda Handler (`lambda_function.py`)

```python
"""
Lambda handler for the Visualization Agent's emit_chart action group.
Deployed as the backing Lambda for the Bedrock Agent action group.
"""
import json
import logging
from typing import Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context: Any) -> dict:
    """Handle Bedrock Agent action group invocations."""
    logger.info(json.dumps({"event": "action_group_invoked", "body": event}))

    action_group = event.get("actionGroup", "")
    api_path = event.get("apiPath", "")
    parameters = event.get("parameters", [])
    request_body = event.get("requestBody", {})

    # Extract parameters from the agent's tool call
    params = {}
    for param in parameters:
        params[param["name"]] = param["value"]

    # Also check requestBody for POST-style invocations
    if request_body and "content" in request_body:
        body_content = request_body["content"].get("application/json", {})
        if "properties" in body_content:
            for prop in body_content["properties"]:
                params[prop["name"]] = prop["value"]

    if api_path == "/emit_chart" or action_group == "emit_chart_action":
        return _handle_emit_chart(params)
    else:
        return _build_response(400, {"error": f"Unknown action: {api_path}"})


def _handle_emit_chart(params: dict) -> dict:
    """Validate and return the chart configuration."""
    chart_config_str = params.get("chart_config", "")
    title = params.get("title", "Untitled Chart")
    description = params.get("description", "")

    # Validate JSON
    try:
        chart_config = json.loads(chart_config_str)
    except (json.JSONDecodeError, TypeError) as exc:
        return _build_response(400, {
            "error": f"Invalid JSON in chart_config: {exc}",
            "title": title,
            "description": description,
        })

    # Validate required fields
    if "type" not in chart_config:
        return _build_response(400, {
            "error": "chart_config must contain a 'type' field",
            "title": title,
            "description": description,
        })

    if "data" not in chart_config:
        return _build_response(400, {
            "error": "chart_config must contain a 'data' field",
            "title": title,
            "description": description,
        })

    # Success — return validated chart spec
    result = {
        "chart_config": chart_config,
        "title": title,
        "description": description,
    }

    return _build_response(200, result)


def _build_response(status_code: int, body: dict) -> dict:
    """Build the response in Bedrock Agent action group format."""
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": "emit_chart_action",
            "apiPath": "/emit_chart",
            "httpMethod": "POST",
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(body)
                }
            }
        }
    }
```

### OpenAPI Schema (`emit_chart_openapi.json`)

This defines the tool interface that Bedrock Agent uses:

```json
{
  "openapi": "3.0.3",
  "info": {
    "title": "Visualization Agent - emit_chart API",
    "version": "1.0.0",
    "description": "Action group for generating Chart.js configurations"
  },
  "paths": {
    "/emit_chart": {
      "post": {
        "operationId": "emitChart",
        "summary": "Emit a complete Chart.js chart configuration for rendering",
        "description": "Call this ONCE with a complete, production-quality Chart.js config. The config must be valid JSON and must contain a 'type' field.",
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "required": ["chart_config", "title", "description"],
                "properties": {
                  "chart_config": {
                    "type": "string",
                    "description": "Complete Chart.js JSON string — must include 'type', 'data' (with 'labels' and 'datasets'), and 'options'. Use animation, tension, fill, borderWidth, pointRadius to make charts visually rich."
                  },
                  "title": {
                    "type": "string",
                    "description": "A concise, descriptive title for the chart."
                  },
                  "description": {
                    "type": "string",
                    "description": "2-3 sentence BI insight explaining what the data shows."
                  }
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "Successfully generated chart configuration",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "chart_config": {
                      "type": "object",
                      "description": "Parsed Chart.js config object"
                    },
                    "title": {
                      "type": "string"
                    },
                    "description": {
                      "type": "string"
                    }
                  }
                }
              }
            }
          },
          "400": {
            "description": "Invalid chart configuration",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "error": { "type": "string" },
                    "title": { "type": "string" },
                    "description": { "type": "string" }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

---

## Create the Agent in Bedrock Console

### Step 1: Navigate to Bedrock Agents

1. Open the [AWS Management Console](https://console.aws.amazon.com)
2. Navigate to **Amazon Bedrock** → **Agents** (left sidebar under "Orchestration")
3. Click **Create Agent**

### Step 2: Configure Agent Details

| Field | Value |
|-------|-------|
| **Agent name** | `visualization-agent` |
| **Description** | `Generates Chart.js configurations from tabular data using BI reasoning` |
| **Agent resource role** | Create a new service role (or select existing) |
| **Foundation model** | `Anthropic > Claude 3.5 Haiku` (`us.anthropic.claude-3-5-haiku-20241022-v1:0`) |
| **Idle session timeout** | 30 minutes |

### Step 3: Set the Agent Instructions

Paste the following into the **Instructions for the Agent** field:

```
You are a data visualization expert for a conversational BI system. Your job is to analyze tabular data and the user's original query, then produce the most insightful Chart.js v4 configuration by calling emit_chart exactly ONCE.

Rules:
1. ALWAYS call emit_chart with a complete, valid Chart.js JSON config.
2. The chart_config MUST contain: "type", "data" (with "labels" and "datasets"), and "options".
3. Choose the chart type based on data shape and user intent:
   - Time-series data (quarters, months, years) → "line"
   - Comparison with ≤6 groups and single metric → "pie" or "doughnut"
   - Comparison with many groups or multiple metrics → "bar"
   - Two numeric columns suggesting correlation → "scatter"
   - Single aggregation result → provide a styled "bar" with single data point
4. Use rich styling: colors, borderWidth, tension for curves, animation, responsive=true.
5. The description field must contain 2-3 sentences of BI insight explaining what the data reveals.
6. If the user explicitly requests a chart type (e.g., "show me a pie chart"), honor that request.
7. Never return text-only responses — always call emit_chart.
```

### Step 4: Attach Guardrails (Optional but Recommended)

1. Under **Guardrails**, click **Add guardrail**
2. Select guardrail ID: `joes1p3j7sa4`
3. Version: `DRAFT`

### Step 5: Click **Next** to proceed to Action Groups

---

## Define the Action Group (emit_chart tool)

### Step 1: Add Action Group

1. In the agent builder, go to **Action groups**
2. Click **Add action group**

### Step 2: Configure Action Group

| Field | Value |
|-------|-------|
| **Action group name** | `emit_chart_action` |
| **Description** | `Emits a validated Chart.js configuration` |
| **Action group type** | Define with API schemas |
| **API schema** | Upload the `emit_chart_openapi.json` file (from above) |
| **Action group invocation** | Select **Lambda function** |

### Step 3: Create or Select Lambda

- If you haven't created the Lambda yet, click **Create a new Lambda function** — this opens the Lambda console in a new tab
- Otherwise, select the existing function (see next section)

---

## Configure the Lambda Function

### Step 1: Create the Lambda Function

1. Open the [Lambda Console](https://console.aws.amazon.com/lambda)
2. Click **Create function**
3. Select **Author from scratch**

| Field | Value |
|-------|-------|
| **Function name** | `viz-agent-emit-chart` |
| **Runtime** | Python 3.12 |
| **Architecture** | arm64 (cost-efficient) |
| **Execution role** | Create a new role with basic Lambda permissions |

4. Click **Create function**

### Step 2: Add the Code

1. In the Lambda editor, replace the default code with the `lambda_function.py` content from the [Prepare the Agent Code](#prepare-the-agent-code) section
2. Click **Deploy**

### Step 3: Add Resource-Based Policy for Bedrock

Bedrock needs permission to invoke this Lambda. In the Lambda console:

1. Go to **Configuration** → **Permissions**
2. Scroll to **Resource-based policy statements**
3. Click **Add permissions**

| Field | Value |
|-------|-------|
| **Statement ID** | `AllowBedrockAgentInvoke` |
| **Principal** | `bedrock.amazonaws.com` |
| **Source ARN** | `arn:aws:bedrock:us-east-1:<ACCOUNT_ID>:agent/*` |
| **Action** | `lambda:InvokeFunction` |

Replace `<ACCOUNT_ID>` with your AWS account ID (visible in the console top-right dropdown).

### Step 4: Configure Timeout

1. Go to **Configuration** → **General configuration**
2. Set **Timeout** to `30 seconds` (chart generation validation may take time with large configs)

### Step 5: Return to Bedrock Agent

Go back to the Bedrock Agent builder tab and select the `viz-agent-emit-chart` function in the action group's Lambda field.

---

## Test the Agent in Console

### Step 1: Prepare the Agent

1. In the Bedrock Agent builder, click **Prepare** (top-right)
2. Wait for status to show **Prepared**

### Step 2: Open the Test Window

1. Click **Test** (top-right, next to Prepare)
2. The test chat panel opens on the right side

### Step 3: Send a Test Prompt

Paste a prompt like:

```
Here is tabular data from a BI query. The user asked: "show me quarterly sales revenue"

Query type: lookup
Columns: ["Quarter", "Revenue", "Region"]
Data rows:
- ["Q1 2024", 145000, "North"]
- ["Q2 2024", 162000, "North"]
- ["Q3 2024", 158000, "North"]
- ["Q4 2024", 189000, "North"]
- ["Q1 2024", 98000, "South"]
- ["Q2 2024", 112000, "South"]
- ["Q3 2024", 105000, "South"]
- ["Q4 2024", 134000, "South"]

Generate a Chart.js visualization for this data.
```

### Step 4: Verify Response

The agent should:
- Call the `emit_chart` action group
- Return a valid Chart.js JSON config with type "line" or "bar"
- Include a descriptive title and BI insight

If the agent responds with text instead of calling the tool, update the instructions to be more forceful about tool use, then **Prepare** again.

---

## Create an Agent Alias for Production

### Step 1: Create Alias

1. In the Agent detail page, go to **Aliases** section
2. Click **Create alias**

| Field | Value |
|-------|-------|
| **Alias name** | `prod` |
| **Description** | `Production alias for visualization agent` |
| **Associate version** | Create a new version (this snapshots the current config) |

3. Click **Create alias**

### Step 2: Note the IDs

After creation, record:
- **Agent ID**: (e.g., `ABCDE12345`)
- **Agent Alias ID**: (e.g., `TSTALIASID` for the prod alias)

You'll need both for the integration code.

---

## Integrate with the Project Backend

The goal is to replace the local Strands Agent call in `visualization_renderer.py` with a Bedrock Agent Runtime invocation.

### Option A: Replace the Strands Agent in `visualization_renderer.py`

Add a new method that calls the deployed AgentCore agent instead of the local Strands agent:

```python
# Add to src/services/visualization_renderer.py

import boto3
import uuid

# Configuration for deployed agent
AGENTCORE_AGENT_ID = "YOUR_AGENT_ID"       # From console
AGENTCORE_ALIAS_ID = "YOUR_ALIAS_ID"       # From console (prod alias)
AGENTCORE_REGION = "us-east-1"

bedrock_agent_runtime = boto3.client(
    "bedrock-agent-runtime",
    region_name=AGENTCORE_REGION,
)


async def _agentcore_render(
    self,
    normalized_payload: dict,
    query_type: str,
    query_text: str,
    stats_text: str,
    requested_chart_type: str | None,
) -> RenderedOutput:
    """Invoke the deployed Bedrock AgentCore visualization agent."""
    
    # Build the prompt (same format as local Strands agent)
    columns = normalized_payload.get("columns", [])
    rows = normalized_payload.get("rows", [])
    sample_rows = rows[:15]  # Limit context size

    prompt_parts = [
        f"User query: \"{query_text}\"",
        f"Query type: {query_type}",
        f"Columns: {json.dumps(columns)}",
        f"Data rows ({len(rows)} total, showing first {len(sample_rows)}):",
        json.dumps(sample_rows, indent=2),
        f"\nPre-computed statistics:\n{stats_text}",
    ]
    if requested_chart_type:
        prompt_parts.append(
            f"\nThe user explicitly requested a '{requested_chart_type}' chart. Honor this."
        )
    prompt_parts.append("\nGenerate a Chart.js visualization by calling emit_chart.")

    input_text = "\n".join(prompt_parts)
    session_id = str(uuid.uuid4())

    try:
        response = bedrock_agent_runtime.invoke_agent(
            agentId=AGENTCORE_AGENT_ID,
            agentAliasId=AGENTCORE_ALIAS_ID,
            sessionId=session_id,
            inputText=input_text,
        )

        # Parse the streaming response
        completion = ""
        for event in response["completion"]:
            if "chunk" in event:
                chunk_bytes = event["chunk"].get("bytes", b"")
                completion += chunk_bytes.decode("utf-8")

        # Extract chart spec from the response
        chart_spec = self._extract_emit_chart(completion)
        if chart_spec and "chart_config" in chart_spec:
            return self._build_rendered_output(chart_spec, normalized_payload, stats_text)

        # If agent didn't produce valid emit_chart, fall back
        logger.warning(json.dumps({
            "event": "agentcore_emit_chart_not_found",
            "response_length": len(completion),
        }))
        return self._deterministic_render(
            normalized_payload, query_type, query_text, stats_text, requested_chart_type
        )

    except Exception as exc:
        logger.error(json.dumps({
            "event": "agentcore_invoke_failed",
            "error": str(exc),
        }))
        return self._deterministic_render(
            normalized_payload, query_type, query_text, stats_text, requested_chart_type
        )
```

### Option B: Create a Standalone Integration Module

If you prefer to keep the renderer clean, create a separate module:

**`src/services/agentcore_client.py`**

```python
"""Client for invoking the Visualization Agent deployed on Bedrock AgentCore."""
import json
import logging
import uuid
from typing import Any

import boto3

from src.config import settings

logger = logging.getLogger(__name__)

# AgentCore configuration — set these via environment or config
AGENT_ID = settings.get("AGENTCORE_VIZ_AGENT_ID", "")
AGENT_ALIAS_ID = settings.get("AGENTCORE_VIZ_ALIAS_ID", "")
REGION = settings.get("AWS_REGION", "us-east-1")


class AgentCoreVizClient:
    """Wraps Bedrock Agent Runtime invoke_agent for the visualization agent."""

    def __init__(self):
        self._client = boto3.client("bedrock-agent-runtime", region_name=REGION)

    def invoke(self, prompt: str) -> dict[str, Any] | None:
        """
        Send a prompt to the deployed viz agent and return the parsed chart spec.
        
        Returns:
            dict with keys: chart_config, title, description — or None on failure.
        """
        session_id = str(uuid.uuid4())

        try:
            response = self._client.invoke_agent(
                agentId=AGENT_ID,
                agentAliasId=AGENT_ALIAS_ID,
                sessionId=session_id,
                inputText=prompt,
            )

            completion = self._read_stream(response)
            return self._parse_chart_spec(completion)

        except Exception as exc:
            logger.error(json.dumps({
                "event": "agentcore_viz_invoke_failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
            }))
            return None

    def _read_stream(self, response: dict) -> str:
        """Read the streaming response from invoke_agent."""
        parts = []
        for event in response.get("completion", []):
            if "chunk" in event:
                chunk_bytes = event["chunk"].get("bytes", b"")
                parts.append(chunk_bytes.decode("utf-8"))
        return "".join(parts)

    def _parse_chart_spec(self, text: str) -> dict[str, Any] | None:
        """Extract emit_chart JSON from agent response text."""
        # Look for JSON with chart_config key
        json_pattern = r'\{[^{}]*"chart_config"[^{}]*\{.*?\}[^{}]*\}'
        
        # Try to find JSON blocks in the text
        try:
            # First try: parse the whole thing as JSON
            parsed = json.loads(text)
            if "chart_config" in parsed:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass

        # Second try: find JSON blocks between braces
        depth = 0
        start = None
        for i, char in enumerate(text):
            if char == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start : i + 1]
                    try:
                        parsed = json.loads(candidate)
                        if "chart_config" in parsed:
                            return parsed
                    except (json.JSONDecodeError, TypeError):
                        pass
                    start = None

        return None
```

Then in `visualization_renderer.py`, use it:

```python
from src.services.agentcore_client import AgentCoreVizClient

# In VisualizationRenderer.__init__:
self._agentcore_client = AgentCoreVizClient()

# In the render method, call:
result = self._agentcore_client.invoke(prompt)
if result:
    return self._build_rendered_output(result, normalized_payload, stats_text)
```

---

## Integrate with the Frontend

The frontend doesn't need to know about AgentCore directly — it still calls the NLP Translator at `POST /query` and receives the same `RenderedOutput` response. The change is entirely backend.

However, if you want the frontend to call AgentCore directly (bypassing the local backend entirely), you'd need an API Gateway:

### API Gateway Setup (Console)

1. Go to **API Gateway** in the AWS Console
2. Click **Create API** → **REST API** → **Build**
3. Name: `conversational-bi-api`
4. Create a resource `/query` with POST method
5. Integration type: **Lambda function** (create a thin Lambda that invokes the gateway agent)
6. Enable CORS: `*` for origins, `POST,OPTIONS` for methods
7. Deploy to a stage (e.g., `prod`)
8. Note the invoke URL: `https://{api-id}.execute-api.us-east-1.amazonaws.com/prod`

### Update Frontend Environment

```bash
# frontend/.env.production
VITE_API_URL=https://{api-id}.execute-api.us-east-1.amazonaws.com/prod
```

The existing `frontend/src/api/` or query submission code just needs the base URL changed. No structural changes to the React app.

---

## Environment Configuration

### Backend `.env` additions

```bash
# AgentCore Visualization Agent
AGENTCORE_VIZ_AGENT_ID=ABCDE12345
AGENTCORE_VIZ_ALIAS_ID=PRODALIASID
AWS_REGION=us-east-1

# Toggle: use AgentCore vs local Strands agent
USE_AGENTCORE_VIZ=true
```

### Feature Toggle Pattern

Add a toggle so you can switch between local and deployed agent:

```python
# In visualization_renderer.py
USE_AGENTCORE = os.environ.get("USE_AGENTCORE_VIZ", "false").lower() == "true"

async def render(self, ...):
    if USE_AGENTCORE:
        return await self._agentcore_render(...)
    else:
        return await self._agent_render_with_retry(...)
```

This lets you develop locally with the Strands agent and deploy to AgentCore in production without code changes.

---

## Rollback Strategy

If the AgentCore deployment has issues:

1. Set `USE_AGENTCORE_VIZ=false` in your environment
2. The system falls back to the local Strands Agent (or deterministic builder)
3. No code deploy needed — just an env var change

For the frontend (if using API Gateway):
1. Change `VITE_API_URL` back to `http://localhost:8001`
2. Rebuild frontend: `npm run build`

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent returns text but doesn't call emit_chart | Make instructions more forceful; add "You MUST call emit_chart" |
| Lambda timeout | Increase timeout to 30s; check chart_config parsing logic |
| "Access Denied" on invoke_agent | Verify IAM role has `bedrock:InvokeAgent` permission |
| Agent not prepared | Click **Prepare** in the console after any config change |
| Guardrail blocks valid output | Check guardrail config; financial data shouldn't trigger content filters |
| Streaming response empty | Check agent alias is pointed to the correct version |

---

## Summary

| Component | Where it lives after deployment |
|-----------|-------------------------------|
| Visualization Agent logic | Bedrock AgentCore (managed) |
| emit_chart validation | Lambda `viz-agent-emit-chart` |
| Chart type selection intelligence | Claude 3.5 Haiku (via AgentCore) |
| Backend orchestration | Still local (`visualization_renderer.py`) with AgentCore client |
| Frontend | Unchanged — still calls `POST /query` on the NLP Translator |
| Guardrails | Bedrock Guardrails (attached to agent natively) |
