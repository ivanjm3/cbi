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
