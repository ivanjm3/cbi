# Deploying the Visualization Agent to Amazon Bedrock via Console (Return Control)

This guide covers deploying the Visualization Renderer agent to Amazon Bedrock using the **Return Control** pattern — no Lambda function, no IAM role required. The agent returns tool call parameters directly to your application, which handles chart validation locally.

> **Why Return Control?** Eliminates the need for Lambda deployment, `iam:PassRole`, and `iam:CreateRole` permissions. Your PowerUserAccess SSO role with `bedrock:*` permissions is all you need.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Architecture Overview](#architecture-overview)
3. [Create the Agent in Bedrock Console](#create-the-agent-in-bedrock-console)
4. [Define the Action Group with Return Control](#define-the-action-group-with-return-control)
5. [Test the Agent in Console](#test-the-agent-in-console)
6. [Create an Agent Alias for Production](#create-an-agent-alias-for-production)
7. [Integrate with the Project Backend](#integrate-with-the-project-backend)
8. [Integrate with the Frontend](#integrate-with-the-frontend)
9. [Environment Configuration](#environment-configuration)
10. [Rollback Strategy](#rollback-strategy)

---

## Prerequisites

- AWS account with Bedrock access enabled in `us-east-1`
- Bedrock model access granted for `us.anthropic.claude-3-5-haiku-20241022-v1:0`
- IAM permissions: `bedrock:*` (that's it — no Lambda or IAM role permissions needed)
- The S3 bucket `visualization-poc-bucket` with data sources already uploaded
- Existing Bedrock Guardrail ID: `joes1p3j7sa4` (DRAFT version)
- Python 3.12+ with `boto3` installed locally for the backend integration

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     YOUR APPLICATION                         │
│                                                             │
│  1. Send prompt to agent  ──────►  Bedrock Agent            │
│                                    (Claude 3.5 Haiku)       │
│                                         │                   │
│  3. Receive returnControl  ◄────────────┘                   │
│     (chart_config, title,     Agent decides to call         │
│      description params)      emit_chart tool               │
│            │                                                │
│  4. Validate & render chart locally                         │
│            │                                                │
│  5. Return chart to frontend                                │
└─────────────────────────────────────────────────────────────┘
```

**Key difference from Lambda approach:** Instead of the agent invoking a Lambda to process the tool call, it returns the parameters directly to your calling code. Your app handles validation and rendering.

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
| **Agent resource role** | Create a new service role (auto-created by Bedrock — no manual IAM needed) |
| **Foundation model** | `Anthropic > Claude 3.5 Haiku` (`us.anthropic.claude-3-5-haiku-20241022-v1:0`) |
| **Idle session timeout** | 30 minutes |

> **Note:** Bedrock automatically creates the agent's service role when you select "Create and use a new service role." This does NOT require `iam:CreateRole` from you — Bedrock's service handles it.

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

## Define the Action Group with Return Control

This is the key difference — instead of pointing to a Lambda, you select **Return Control**.

### Step 1: Add Action Group

1. In the agent builder, go to **Action groups**
2. Click **Add action group**

### Step 2: Configure Action Group

| Field | Value |
|-------|-------|
| **Action group name** | `emit_chart_action` |
| **Description** | `Emits a validated Chart.js configuration` |
| **Action group type** | Define with API schemas |
| **API schema** | Upload or paste the OpenAPI schema (below) |
| **Action group invocation** | Select **Return Control** (NOT Lambda function) |

> **Critical:** Under "Action group invocation", choose **"Return control to the user/calling application"** instead of "Lambda function." This is what eliminates the IAM requirement.

### Step 3: Upload the OpenAPI Schema

Save this as `emit_chart_openapi.json` and upload it:

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
          }
        }
      }
    }
  }
}
```

### Step 4: Save and Prepare

1. Click **Save** on the action group
2. Click **Prepare** (top-right of the agent builder)
3. Wait for status to show **Prepared**

---

## Test the Agent in Console

### Step 1: Open the Test Window

1. Click **Test** (top-right, next to Prepare)
2. The test chat panel opens on the right side

### Step 2: Send a Test Prompt

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

### Step 3: Verify Response

With Return Control, the test console will show the agent attempting to call `emit_chart` and display the parameters it would pass. You'll see something like:

```
Action Group: emit_chart_action
API Path: /emit_chart
Parameters:
  - chart_config: {"type": "line", "data": {...}, "options": {...}}
  - title: "Quarterly Sales Revenue by Region"
  - description: "Revenue shows consistent growth..."
```

> **Note:** In the console test, Return Control actions show as "function call" outputs. The actual processing happens in your application code (next section).

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

With Return Control, your application receives the agent's tool call parameters directly and processes them locally. No Lambda involved.

### Backend Client: `src/services/agentcore_client.py`

```python
"""
Client for invoking the Visualization Agent via Bedrock Return Control.
No Lambda required — the agent returns tool call params directly to this code.
"""
import json
import logging
import uuid
from typing import Any

import boto3

logger = logging.getLogger(__name__)


class AgentCoreVizClient:
    """
    Invokes the Bedrock Agent and handles Return Control responses.
    
    Flow:
    1. Send prompt to agent
    2. Agent decides to call emit_chart → returns control with params
    3. We validate the chart_config locally
    4. Return the validated result
    """

    def __init__(self, agent_id: str, alias_id: str, region: str = "us-east-1"):
        self.agent_id = agent_id
        self.alias_id = alias_id
        self._client = boto3.client("bedrock-agent-runtime", region_name=region)

    def invoke(self, prompt: str) -> dict[str, Any] | None:
        """
        Send a prompt to the viz agent and return the chart spec.
        
        Returns:
            dict with keys: chart_config (parsed), title, description
            None on failure
        """
        session_id = str(uuid.uuid4())

        try:
            response = self._client.invoke_agent(
                agentId=self.agent_id,
                agentAliasId=self.alias_id,
                sessionId=session_id,
                inputText=prompt,
            )

            # Process the event stream
            return self._process_response_stream(response)

        except Exception as exc:
            logger.error(json.dumps({
                "event": "agentcore_viz_invoke_failed",
                "error": str(exc),
                "error_type": type(exc).__name__,
            }))
            return None

    def _process_response_stream(self, response: dict) -> dict[str, Any] | None:
        """
        Process the streaming response from invoke_agent.
        
        With Return Control, we look for 'returnControl' events that contain
        the agent's tool call parameters.
        """
        for event in response.get("completion", []):
            # Return Control event — the agent wants to call emit_chart
            if "returnControl" in event:
                return self._handle_return_control(event["returnControl"])

            # Text chunk — agent responded with text instead of tool call
            if "chunk" in event:
                chunk_text = event["chunk"].get("bytes", b"").decode("utf-8")
                logger.warning(json.dumps({
                    "event": "agent_returned_text_not_tool",
                    "text_preview": chunk_text[:200],
                }))

        return None

    def _handle_return_control(self, return_control: dict) -> dict[str, Any] | None:
        """
        Extract and validate parameters from the Return Control event.
        
        The event structure looks like:
        {
            "invocationInputs": [{
                "apiInvocationInput": {
                    "actionGroup": "emit_chart_action",
                    "apiPath": "/emit_chart",
                    "httpMethod": "POST",
                    "requestBody": {
                        "content": {
                            "application/json": [
                                {"name": "chart_config", "type": "string", "value": "..."},
                                {"name": "title", "type": "string", "value": "..."},
                                {"name": "description", "type": "string", "value": "..."}
                            ]
                        }
                    }
                }
            }]
        }
        """
        invocation_inputs = return_control.get("invocationInputs", [])
        if not invocation_inputs:
            logger.warning("Return control event has no invocation inputs")
            return None

        # Get the first invocation (we only have one action group)
        invocation = invocation_inputs[0]
        api_input = invocation.get("apiInvocationInput", {})

        # Extract parameters from the request body
        request_body = api_input.get("requestBody", {})
        content = request_body.get("content", {})
        json_params = content.get("application/json", [])

        # Build params dict
        params = {}
        for param in json_params:
            params[param["name"]] = param["value"]

        # Validate and parse chart_config
        return self._validate_chart_config(params)

    def _validate_chart_config(self, params: dict) -> dict[str, Any] | None:
        """
        Validate the chart_config JSON — same logic that was in the Lambda.
        Now runs locally in your application.
        """
        chart_config_str = params.get("chart_config", "")
        title = params.get("title", "Untitled Chart")
        description = params.get("description", "")

        # Parse JSON
        try:
            chart_config = json.loads(chart_config_str)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error(json.dumps({
                "event": "invalid_chart_config_json",
                "error": str(exc),
            }))
            return None

        # Validate required fields
        if "type" not in chart_config:
            logger.error("chart_config missing 'type' field")
            return None

        if "data" not in chart_config:
            logger.error("chart_config missing 'data' field")
            return None

        return {
            "chart_config": chart_config,
            "title": title,
            "description": description,
        }
```

### Usage in `visualization_renderer.py`

```python
import os
from src.services.agentcore_client import AgentCoreVizClient

# Configuration
AGENT_ID = os.environ.get("AGENTCORE_VIZ_AGENT_ID", "")
ALIAS_ID = os.environ.get("AGENTCORE_VIZ_ALIAS_ID", "")
USE_AGENTCORE = os.environ.get("USE_AGENTCORE_VIZ", "false").lower() == "true"

# Initialize client
viz_client = AgentCoreVizClient(agent_id=AGENT_ID, alias_id=ALIAS_ID)


async def render_chart(
    normalized_payload: dict,
    query_type: str,
    query_text: str,
    stats_text: str,
    requested_chart_type: str | None = None,
) -> dict:
    """Render a chart using the Bedrock Agent with Return Control."""
    
    # Build prompt
    columns = normalized_payload.get("columns", [])
    rows = normalized_payload.get("rows", [])
    sample_rows = rows[:15]

    prompt_parts = [
        f'User query: "{query_text}"',
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

    prompt = "\n".join(prompt_parts)

    # Invoke agent — returns parsed chart spec directly (no Lambda)
    result = viz_client.invoke(prompt)

    if result:
        return result
    else:
        # Fallback to deterministic rendering
        return deterministic_render(normalized_payload, query_type, query_text, stats_text)
```

---

## Integrate with the Frontend

The frontend remains unchanged — it still calls your backend's `POST /query` endpoint and receives the same chart config response. The only difference is the backend now gets that config from Bedrock Return Control instead of a Lambda.

No API Gateway changes needed either.

---

## Environment Configuration

### Backend `.env`

```bash
# AgentCore Visualization Agent (Return Control — no Lambda)
AGENTCORE_VIZ_AGENT_ID=YOUR_AGENT_ID_HERE
AGENTCORE_VIZ_ALIAS_ID=YOUR_ALIAS_ID_HERE
AWS_REGION=us-east-1

# Toggle: use AgentCore vs local Strands agent
USE_AGENTCORE_VIZ=true
```

### AWS Credentials

Your existing PowerUserAccess SSO profile works. Make sure your local `~/.aws/config` has:

```ini
[profile PowerUserAccess-654654478821]
sso_start_url = https://your-sso-url.awsapps.com/start
sso_account_id = 654654478821
sso_role_name = PowerUserAccess
sso_region = us-east-1
region = us-east-1
```

Then either:
- Set `AWS_PROFILE=PowerUserAccess-654654478821` in your `.env`
- Or run `aws sso login --profile PowerUserAccess-654654478821` before starting your app

---

## Rollback Strategy

If the AgentCore deployment has issues:

1. Set `USE_AGENTCORE_VIZ=false` in your environment
2. The system falls back to the local Strands Agent (or deterministic builder)
3. No code deploy needed — just an env var change

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Agent returns text but doesn't call emit_chart | Make instructions more forceful; add "You MUST call emit_chart". Re-Prepare the agent. |
| No `returnControl` event in stream | Verify action group invocation is set to "Return Control" (not Lambda) |
| `AccessDeniedException` on invoke_agent | Verify your SSO role has `bedrock:InvokeAgent` permission |
| Agent not prepared | Click **Prepare** in the console after any config change |
| Guardrail blocks valid output | Check guardrail config; financial data shouldn't trigger content filters |
| `chart_config` is invalid JSON | The agent sometimes produces malformed JSON — add retry logic or fallback |
| Empty response stream | Check agent alias is pointed to the correct version |

---

## Summary

| Component | Where it lives |
|-----------|---------------|
| Visualization Agent logic | Bedrock Agent (managed, no Lambda) |
| emit_chart validation | **Your application** (local Python code) |
| Chart type selection intelligence | Claude 3.5 Haiku (via Bedrock Agent) |
| Backend orchestration | Local (`visualization_renderer.py`) with `AgentCoreVizClient` |
| Frontend | Unchanged — still calls `POST /query` on backend |
| Guardrails | Bedrock Guardrails (attached to agent natively) |
| IAM requirements | Just `bedrock:*` — no Lambda roles, no PassRole |

---

## CLI Alternative (Optional)

If you prefer CLI over console for creating the action group with Return Control:

```bash
aws bedrock-agent create-agent-action-group \
  --agent-id YOUR_AGENT_ID \
  --agent-version DRAFT \
  --action-group-name emit_chart_action \
  --description "Emits a validated Chart.js configuration" \
  --action-group-executor '{"customControl": "RETURN_CONTROL"}' \
  --api-schema '{"payload": "{\"openapi\":\"3.0.3\",\"info\":{\"title\":\"emit_chart\",\"version\":\"1.0.0\"},\"paths\":{\"/emit_chart\":{\"post\":{\"operationId\":\"emitChart\",\"requestBody\":{\"required\":true,\"content\":{\"application/json\":{\"schema\":{\"type\":\"object\",\"required\":[\"chart_config\",\"title\",\"description\"],\"properties\":{\"chart_config\":{\"type\":\"string\",\"description\":\"Complete Chart.js JSON string\"},\"title\":{\"type\":\"string\",\"description\":\"Chart title\"},\"description\":{\"type\":\"string\",\"description\":\"BI insight\"}}}}}},\"responses\":{\"200\":{\"description\":\"Success\"}}}}}}"}}' \
  --region us-east-1 \
  --profile PowerUserAccess-654654478821
```

Then prepare the agent:

```bash
aws bedrock-agent prepare-agent \
  --agent-id YOUR_AGENT_ID \
  --region us-east-1 \
  --profile PowerUserAccess-654654478821
```
