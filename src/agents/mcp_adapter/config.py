"""Configuration models for the MCP Adapter Layer.

Parses environment variables with MCP_ADAPTER_REDSHIFT_ and MCP_ADAPTER_S3_
prefixes to build server connection configurations. Validates transport mode,
timeout bounds, and required variables per transport type.
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Valid transport modes
VALID_TRANSPORTS = ("stdio", "streamable-http")

# Timeout bounds
TIMEOUT_MIN = 1
TIMEOUT_MAX = 300
TIMEOUT_DEFAULT = 30

# Port bounds for streamable-http
PORT_MIN = 1024
PORT_MAX = 65535


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server connection.

    Attributes:
        server_id: Identifier for this server ("redshift" or "s3").
        transport: Transport protocol. Must be "stdio" or "streamable-http".
        host: Server host for streamable-http transport.
        port: Server port for streamable-http transport (1024-65535).
        command: Executable path for stdio transport.
        timeout: Per-tool-call timeout in seconds (1-300).
        connection_timeout: Initial connection timeout in seconds.
        available: Whether this server configuration is valid and usable.
        unavailable_reason: Description of why the server is unavailable.
    """

    server_id: str
    transport: Literal["stdio", "streamable-http"] = "stdio"
    host: str | None = None
    port: int | None = None
    command: str | None = None
    timeout: int = Field(default=TIMEOUT_DEFAULT, ge=TIMEOUT_MIN, le=TIMEOUT_MAX)
    connection_timeout: int = 10
    available: bool = True
    unavailable_reason: str | None = None


class MCPAdapterConfig(BaseModel):
    """Full adapter configuration loaded from environment variables.

    Attributes:
        redshift: Configuration for the MCP Redshift server.
        s3: Configuration for the MCP S3 server.
        max_reconnect_attempts: Maximum reconnection attempts before giving up.
        reconnect_interval: Seconds between reconnection attempts.
        max_row_limit: Maximum rows to paginate from S3.
        shutdown_timeout: Seconds for graceful shutdown.
    """

    redshift: MCPServerConfig
    s3: MCPServerConfig
    max_reconnect_attempts: int = 10
    reconnect_interval: int = 30
    max_row_limit: int = 10000
    shutdown_timeout: int = 5


def _parse_transport(raw_value: str | None) -> str:
    """Parse and validate the TRANSPORT env var.

    Returns "stdio" if the value is missing or empty.
    Returns the value if valid, otherwise returns the raw value
    (caller handles marking unavailable for invalid values).
    """
    if not raw_value or raw_value.strip() == "":
        return "stdio"
    return raw_value.strip().lower()


def _parse_timeout(raw_value: str | None) -> int:
    """Parse and clamp the TIMEOUT env var to 1-300.

    Returns TIMEOUT_DEFAULT (30) if missing, empty, or non-numeric.
    Clamps to bounds if outside range.
    """
    if not raw_value or raw_value.strip() == "":
        return TIMEOUT_DEFAULT
    try:
        value = int(raw_value.strip())
    except ValueError:
        return TIMEOUT_DEFAULT
    return max(TIMEOUT_MIN, min(TIMEOUT_MAX, value))


def _parse_port(raw_value: str | None) -> int | None:
    """Parse the PORT env var.

    Returns None if missing, empty, or non-numeric.
    Returns the integer value otherwise (validation of range is done separately).
    """
    if not raw_value or raw_value.strip() == "":
        return None
    try:
        return int(raw_value.strip())
    except ValueError:
        return None


def _parse_server_config(server_id: str, prefix: str) -> MCPServerConfig:
    """Parse a single MCP server configuration from environment variables.

    Reads env vars with the given prefix (e.g., MCP_ADAPTER_REDSHIFT_)
    and validates required variables based on transport mode.

    Args:
        server_id: Server identifier ("redshift" or "s3").
        prefix: Environment variable prefix (e.g., "MCP_ADAPTER_REDSHIFT_").

    Returns:
        MCPServerConfig with available=False if configuration is invalid.
    """
    raw_transport = os.environ.get(f"{prefix}TRANSPORT")
    transport = _parse_transport(raw_transport)
    timeout = _parse_timeout(os.environ.get(f"{prefix}TIMEOUT"))
    host = os.environ.get(f"{prefix}HOST", "").strip() or None
    port = _parse_port(os.environ.get(f"{prefix}PORT"))
    command = os.environ.get(f"{prefix}COMMAND", "").strip() or None

    # Validate transport value
    if transport not in VALID_TRANSPORTS:
        reason = (
            f"Invalid TRANSPORT value '{transport}' for {server_id}. "
            f"Must be one of: {', '.join(VALID_TRANSPORTS)}"
        )
        logger.error(reason)
        return MCPServerConfig(
            server_id=server_id,
            transport="stdio",  # Default for model validity
            timeout=timeout,
            host=host,
            port=port,
            command=command,
            available=False,
            unavailable_reason=reason,
        )

    # Validate required vars for streamable-http
    if transport == "streamable-http":
        missing = []
        if not host:
            missing.append(f"{prefix}HOST")
        if port is None:
            missing.append(f"{prefix}PORT")

        if missing:
            reason = (
                f"Missing required environment variable(s) for {server_id} "
                f"streamable-http transport: {', '.join(missing)}"
            )
            logger.error(reason)
            return MCPServerConfig(
                server_id=server_id,
                transport=transport,
                timeout=timeout,
                host=host,
                port=port,
                command=command,
                available=False,
                unavailable_reason=reason,
            )

        # Validate port range
        if port is not None and (port < PORT_MIN or port > PORT_MAX):
            reason = (
                f"Invalid PORT value {port} for {server_id}. "
                f"Must be between {PORT_MIN} and {PORT_MAX}."
            )
            logger.error(reason)
            return MCPServerConfig(
                server_id=server_id,
                transport=transport,
                timeout=timeout,
                host=host,
                port=port,
                command=command,
                available=False,
                unavailable_reason=reason,
            )

    # Validate required vars for stdio
    if transport == "stdio":
        if not command:
            reason = (
                f"Missing required environment variable {prefix}COMMAND "
                f"for {server_id} stdio transport"
            )
            logger.error(reason)
            return MCPServerConfig(
                server_id=server_id,
                transport=transport,
                timeout=timeout,
                host=host,
                port=port,
                command=command,
                available=False,
                unavailable_reason=reason,
            )

    # All validations passed
    return MCPServerConfig(
        server_id=server_id,
        transport=transport,
        timeout=timeout,
        host=host,
        port=port,
        command=command,
        available=True,
        unavailable_reason=None,
    )


def load_config() -> MCPAdapterConfig:
    """Load the full MCP Adapter configuration from environment variables.

    Reads MCP_ADAPTER_REDSHIFT_* and MCP_ADAPTER_S3_* prefixed variables
    and returns a validated MCPAdapterConfig. Servers with invalid or
    incomplete configuration are marked as unavailable.

    Returns:
        MCPAdapterConfig with both server configurations.
    """
    redshift_config = _parse_server_config("redshift", "MCP_ADAPTER_REDSHIFT_")
    s3_config = _parse_server_config("s3", "MCP_ADAPTER_S3_")

    return MCPAdapterConfig(
        redshift=redshift_config,
        s3=s3_config,
    )
