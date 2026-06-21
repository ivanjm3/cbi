"""Fallback Handler for the MCP Adapter Layer.

Dispatches requests to legacy spoke agents when MCP servers are unavailable
or when tool calls fail. Handles connection reset with a single reconnect
attempt within 3 seconds before returning a DUAL_PATH_FAILURE error.
"""

from __future__ import annotations

import logging

import httpx

from src.models.shared import AgentResult, StructuredIntent

logger = logging.getLogger(__name__)

# Default legacy spoke agent endpoints
_DEFAULT_LEGACY_ENDPOINTS = {
    "redshift": "http://localhost:8011",
    "s3": "http://localhost:8010",
}

# Legacy agent IDs for endpoint construction
_LEGACY_AGENT_IDS = {
    "redshift": "redshift-spoke-agent",
    "s3": "spoke-agent",
}

# Timeout for legacy agent requests (seconds)
_LEGACY_TIMEOUT = 30.0

# Reconnect timeout on connection reset (seconds)
_RECONNECT_TIMEOUT = 3.0


class FallbackHandler:
    """Handles fallback dispatch to legacy spoke agents.

    When an MCP server is unavailable or a tool call fails, the adapter
    falls back to the legacy spoke agent for that data source.
    """

    def __init__(
        self,
        legacy_endpoints: dict[str, str] | None = None,
    ) -> None:
        """Initialize the fallback handler.

        Args:
            legacy_endpoints: Map of server_id to legacy agent base URL.
                Defaults to localhost ports 8010 (S3) and 8011 (Redshift).
        """
        self.endpoints = legacy_endpoints or _DEFAULT_LEGACY_ENDPOINTS

    async def dispatch(
        self,
        intent: StructuredIntent,
        server_id: str,
        correlation_id: str,
    ) -> AgentResult:
        """Dispatch a StructuredIntent to the legacy spoke agent.

        POSTs the intent to the legacy agent's /agents/{agent_id}/invoke
        endpoint. On connection reset, attempts one reconnection within
        3 seconds. Returns DUAL_PATH_FAILURE if both MCP and legacy fail.

        Args:
            intent: The StructuredIntent to dispatch.
            server_id: MCP server ID ("redshift" or "s3") to determine
                which legacy agent to call.
            correlation_id: X-Correlation-ID for observability.

        Returns:
            AgentResult from the legacy agent, or error AgentResult on failure.
        """
        base_url = self.endpoints.get(server_id)
        if not base_url:
            logger.error(
                "No legacy endpoint configured for server_id=%s", server_id
            )
            return self._dual_path_failure(
                server_id, correlation_id, "No legacy endpoint configured"
            )

        agent_id = _LEGACY_AGENT_IDS.get(server_id, f"{server_id}-spoke-agent")
        url = f"{base_url}/agents/{agent_id}/invoke"

        headers = {"X-Correlation-ID": correlation_id}
        payload = {"structured_intent": intent.model_dump(mode="json")}

        logger.warning(
            "Falling back to legacy agent for server_id=%s, "
            "correlation_id=%s, url=%s",
            server_id,
            correlation_id,
            url,
        )

        # First attempt
        try:
            return await self._post_to_legacy(url, payload, headers)

        except httpx.ConnectError as e:
            # Connection reset — attempt one reconnection within 3 seconds
            logger.warning(
                "Connection reset to legacy agent %s, attempting reconnect "
                "(correlation_id=%s): %s",
                server_id,
                correlation_id,
                str(e),
            )
            try:
                return await self._post_to_legacy(
                    url, payload, headers, timeout=_RECONNECT_TIMEOUT
                )
            except Exception as retry_err:
                logger.error(
                    "Reconnect to legacy agent %s failed "
                    "(correlation_id=%s): %s",
                    server_id,
                    correlation_id,
                    str(retry_err),
                )
                return self._dual_path_failure(
                    server_id, correlation_id, str(retry_err)
                )

        except httpx.TimeoutException as e:
            logger.error(
                "Legacy agent %s timed out (correlation_id=%s): %s",
                server_id,
                correlation_id,
                str(e),
            )
            return self._dual_path_failure(
                server_id, correlation_id, f"Timeout: {e}"
            )

        except Exception as e:
            logger.error(
                "Legacy agent %s request failed (correlation_id=%s): %s",
                server_id,
                correlation_id,
                str(e),
            )
            return self._dual_path_failure(
                server_id, correlation_id, str(e)
            )

    async def _post_to_legacy(
        self,
        url: str,
        payload: dict,
        headers: dict,
        timeout: float = _LEGACY_TIMEOUT,
    ) -> AgentResult:
        """POST to legacy spoke agent and parse the AgentResult response.

        Args:
            url: Full URL to the legacy agent invoke endpoint.
            payload: Request body with structured_intent.
            headers: HTTP headers including X-Correlation-ID.
            timeout: Request timeout in seconds.

        Returns:
            Parsed AgentResult from the legacy agent response.

        Raises:
            httpx.ConnectError: On connection failure.
            httpx.TimeoutException: On timeout.
            Exception: On non-200 response or parse failure.
        """
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code != 200:
            raise Exception(
                f"Legacy agent returned status {response.status_code}: "
                f"{response.text[:200]}"
            )

        data = response.json()
        return AgentResult.model_validate(data)

    @staticmethod
    def _dual_path_failure(
        server_id: str, correlation_id: str, failure_reason: str
    ) -> AgentResult:
        """Produce DUAL_PATH_FAILURE error when both MCP and legacy fail.

        Args:
            server_id: The MCP server that originally failed.
            correlation_id: Request correlation ID.
            failure_reason: Description of the legacy agent failure.

        Returns:
            AgentResult with error_type "DUAL_PATH_FAILURE".
        """
        agent_id = f"mcp-{server_id}-adapter"
        legacy_agent = _LEGACY_AGENT_IDS.get(server_id, f"{server_id}-spoke-agent")

        return AgentResult(
            status="error",
            error_type="DUAL_PATH_FAILURE",
            error_description=(
                f"Both MCP server ({server_id}) and legacy agent "
                f"({legacy_agent}) failed for correlation_id={correlation_id}. "
                f"Legacy failure: {failure_reason}"
            ),
            agent_id=agent_id,
            data_source=f"mcp-{server_id}",
        )
