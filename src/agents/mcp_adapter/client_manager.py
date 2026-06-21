"""MCP Client Manager for the MCP Adapter Layer.

Manages connections to MCP servers using the official `mcp` Python SDK,
handles connection lifecycle (connect, reconnect, shutdown), and exposes
a `call_tool()` method for invoking tools on connected servers.

Supports both stdio and streamable-http transports as configured per server.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import AsyncExitStack
from datetime import timedelta

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent

from .config import MCPServerConfig
from .models import MCPToolResult

logger = logging.getLogger(__name__)


class MCPUnavailableError(Exception):
    """Raised when an MCP server is not connected or marked unavailable."""
    pass


class MCPTimeoutError(Exception):
    """Raised when an MCP tool call exceeds the configured timeout."""
    pass


class MCPClientManager:
    """Manages MCP server connections with reconnection logic.

    Establishes connections using the official MCP SDK, tracks availability,
    and provides automatic reconnection on failure.
    """

    def __init__(self, server_config: MCPServerConfig) -> None:
        self.config = server_config
        self.available: bool = False
        self._session: ClientSession | None = None
        self._exit_stack: AsyncExitStack | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = 10
        self._reconnect_interval: int = 30
        self._in_flight_tasks: set[asyncio.Task] = set()
        self._shutting_down: bool = False

    async def connect(self) -> bool:
        """Establish connection to the MCP server within 10-second timeout.

        Returns:
            True if connection succeeded, False otherwise.
        """
        if not self.config.available:
            logger.warning(
                "Cannot connect to %s: configuration is invalid (%s)",
                self.config.server_id,
                self.config.unavailable_reason,
            )
            return False

        try:
            async with asyncio.timeout(self.config.connection_timeout):
                return await self._establish_connection()
        except (asyncio.TimeoutError, TimeoutError):
            logger.error(
                "Connection to MCP server %s timed out after %ds",
                self.config.server_id,
                self.config.connection_timeout,
            )
            await self._cleanup_connection()
            self.available = False
            self._start_reconnect_loop()
            return False
        except (asyncio.CancelledError, RuntimeError, GeneratorExit):
            logger.error(
                "Connection to MCP server %s was cancelled or encountered "
                "a runtime error",
                self.config.server_id,
            )
            # Don't try cleanup — exit stack may be in broken state
            self._session = None
            self._exit_stack = None
            self.available = False
            self._start_reconnect_loop()
            return False
        except Exception as e:
            logger.error(
                "Failed to connect to MCP server %s (%s transport): %s",
                self.config.server_id,
                self.config.transport,
                str(e),
            )
            await self._cleanup_connection()
            self.available = False
            self._start_reconnect_loop()
            return False

    async def _establish_connection(self) -> bool:
        """Set up the MCP client session with the configured transport."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        try:
            if self.config.transport == "stdio":
                server_params = StdioServerParameters(
                    command=self.config.command,
                    args=[],
                )
                transport = await self._exit_stack.enter_async_context(
                    stdio_client(server_params)
                )
                read_stream, write_stream = transport[0], transport[1]
            else:
                # streamable-http transport
                # Pre-check connectivity before entering the MCP context
                # to avoid anyio task group cleanup issues on failure.
                import httpx
                url = f"http://{self.config.host}:{self.config.port}/mcp"
                try:
                    async with httpx.AsyncClient(timeout=5.0) as probe:
                        resp = await probe.get(url)
                        # Any response means the server is listening
                except (httpx.ConnectError, httpx.TimeoutException) as e:
                    raise ConnectionError(
                        f"MCP server at {url} is not reachable: {e}"
                    ) from e

                transport = await self._exit_stack.enter_async_context(
                    streamablehttp_client(
                        url=url,
                        timeout=float(self.config.timeout),
                    )
                )
                read_stream, write_stream = transport[0], transport[1]

            # Create and initialize the client session
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(
                    read_stream=read_stream,
                    write_stream=write_stream,
                    read_timeout_seconds=timedelta(seconds=self.config.timeout),
                )
            )
            await self._session.initialize()

            self.available = True
            self._reconnect_attempts = 0
            logger.info(
                "Connected to MCP server %s via %s",
                self.config.server_id,
                self.config.transport,
            )
            return True

        except (asyncio.CancelledError, RuntimeError, GeneratorExit):
            # Cancellation or task-group issues — don't try to clean up
            # the exit stack here as it may be in a broken state.
            # The caller (connect()) handles cleanup.
            self._session = None
            self._exit_stack = None
            raise

        except Exception:
            await self._cleanup_connection()
            raise

    async def call_tool(self, tool_name: str, arguments: dict) -> MCPToolResult:
        """Invoke a tool on the connected MCP server.

        Args:
            tool_name: Name of the MCP tool to invoke.
            arguments: Arguments dict to pass to the tool.

        Returns:
            MCPToolResult with success/failure status and response content.

        Raises:
            MCPUnavailableError: If the server is not connected.
            MCPTimeoutError: If the tool call exceeds the configured timeout.
        """
        if not self.available or self._session is None:
            raise MCPUnavailableError(
                f"MCP server {self.config.server_id} is not available"
            )

        start_time = time.monotonic()
        task = asyncio.current_task()
        if task:
            self._in_flight_tasks.add(task)

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments),
                timeout=self.config.timeout,
            )
            duration_ms = (time.monotonic() - start_time) * 1000

            if result.isError:
                error_msg = _extract_text_content(result.content)
                return MCPToolResult(
                    success=False,
                    error_message=error_msg,
                    tool_name=tool_name,
                    server_id=self.config.server_id,
                    duration_ms=duration_ms,
                )

            # Parse successful response content
            content = _parse_content(result.content)
            return MCPToolResult(
                success=True,
                content=content,
                tool_name=tool_name,
                server_id=self.config.server_id,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "Tool call %s on %s timed out after %.1fms",
                tool_name,
                self.config.server_id,
                duration_ms,
            )
            raise MCPTimeoutError(
                f"Tool call {tool_name} on {self.config.server_id} "
                f"timed out after {self.config.timeout}s"
            )

        except (MCPUnavailableError, MCPTimeoutError):
            raise

        except Exception as e:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "Tool call %s on %s failed: %s",
                tool_name,
                self.config.server_id,
                str(e),
            )
            # Mark as unavailable on connection errors and start reconnect
            self.available = False
            self._session = None
            self._start_reconnect_loop()
            raise MCPUnavailableError(
                f"MCP server {self.config.server_id} connection lost: {e}"
            ) from e

        finally:
            if task:
                self._in_flight_tasks.discard(task)

    async def disconnect(self) -> None:
        """Graceful disconnect within 5 seconds, cancelling in-flight calls."""
        self._shutting_down = True
        self._stop_reconnect_loop()

        # Cancel in-flight tool calls
        for task in list(self._in_flight_tasks):
            task.cancel()

        # Wait briefly for in-flight tasks to finish
        if self._in_flight_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *self._in_flight_tasks, return_exceptions=True
                    ),
                    timeout=5.0,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Some in-flight calls on %s did not complete within 5s shutdown",
                    self.config.server_id,
                )

        await self._cleanup_connection()
        self.available = False
        logger.info("Disconnected from MCP server %s", self.config.server_id)

    async def _reconnect_loop(self) -> None:
        """Reconnect at 30-second intervals, up to 10 attempts.

        Restores available status on successful reconnection.
        """
        while (
            self._reconnect_attempts < self._max_reconnect_attempts
            and not self._shutting_down
        ):
            self._reconnect_attempts += 1
            logger.info(
                "Reconnect attempt %d/%d for MCP server %s",
                self._reconnect_attempts,
                self._max_reconnect_attempts,
                self.config.server_id,
            )

            try:
                await self._cleanup_connection()
                async with asyncio.timeout(self.config.connection_timeout):
                    success = await self._establish_connection()
                if success:
                    logger.info(
                        "Reconnected to MCP server %s after %d attempts",
                        self.config.server_id,
                        self._reconnect_attempts,
                    )
                    return
            except Exception as e:
                # Clean up broken state
                self._session = None
                self._exit_stack = None
                logger.warning(
                    "Reconnect attempt %d for %s failed: %s",
                    self._reconnect_attempts,
                    self.config.server_id,
                    type(e).__name__,
                )

            # Wait before next attempt
            if not self._shutting_down:
                await asyncio.sleep(self._reconnect_interval)

        if not self._shutting_down:
            logger.error(
                "Max reconnect attempts (%d) reached for MCP server %s",
                self._max_reconnect_attempts,
                self.config.server_id,
            )

    def _start_reconnect_loop(self) -> None:
        """Start the background reconnection loop if not already running."""
        if self._shutting_down:
            return
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_attempts = 0
            self._reconnect_task = asyncio.create_task(
                self._reconnect_loop(),
                name=f"reconnect-{self.config.server_id}",
            )

    def _stop_reconnect_loop(self) -> None:
        """Cancel the background reconnection loop."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None

    async def _cleanup_connection(self) -> None:
        """Clean up existing connection resources."""
        self._session = None
        if self._exit_stack:
            try:
                await self._exit_stack.aclose()
            except (Exception, GeneratorExit):
                # Exit stack cleanup can fail if transports are in a broken
                # state (e.g., after cancellation of anyio task groups).
                # This is expected and safe to ignore.
                pass
            finally:
                self._exit_stack = None


def _extract_text_content(content: list) -> str:
    """Extract text from MCP response content list."""
    texts = []
    for item in content:
        if isinstance(item, TextContent):
            texts.append(item.text)
        elif hasattr(item, "text"):
            texts.append(str(item.text))
    return "; ".join(texts) if texts else "Unknown error"


def _parse_content(content: list) -> dict:
    """Parse MCP response content into a dict.

    Attempts to parse the first TextContent item as JSON.
    Falls back to wrapping text in a dict.
    """
    for item in content:
        if isinstance(item, TextContent):
            try:
                return json.loads(item.text)
            except (json.JSONDecodeError, TypeError):
                return {"text": item.text}
        elif hasattr(item, "text"):
            try:
                return json.loads(str(item.text))
            except (json.JSONDecodeError, TypeError):
                return {"text": str(item.text)}
    return {}
