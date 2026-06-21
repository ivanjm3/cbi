"""Feature Flag Router for MCP adapter routing decisions.

Reads environment variables per-request to determine whether data access
should route through the MCP Adapter Layer or the legacy spoke agents.
Supports per-datasource overrides and a global flag, with precedence:
  1. Per-datasource flag (USE_MCP_REDSHIFT, USE_MCP_S3) if set
  2. Global flag (USE_MCP_ADAPTER) if set
  3. Default: false (legacy path)

Flags are read from environment variables at request time, allowing
hot-toggling without service restart.
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)

# Environment variable names
_GLOBAL_FLAG = "USE_MCP_ADAPTER"
_PER_DATASOURCE_FLAGS = {
    "redshift": "USE_MCP_REDSHIFT",
    "s3": "USE_MCP_S3",
}

# Values considered truthy
_TRUTHY_VALUES = {"true", "1", "yes", "on"}
_FALSY_VALUES = {"false", "0", "no", "off"}


class FeatureFlagRouter:
    """Reads feature flags and decides routing target per request.

    Checks per-datasource flag first, then global flag. Per-datasource
    flags override the global flag. When no flags are set, defaults to
    legacy (False).
    """

    def should_use_mcp(self, data_source: str) -> bool:
        """Determine whether to route through MCP for a given data source.

        Reads environment variables at call time for hot-toggle support.

        Args:
            data_source: The data source identifier to check routing for.
                Typically "redshift" or "s3".

        Returns:
            True if the request should route to MCP Adapter Layer,
            False if it should route to the legacy spoke agent.
        """
        # Check per-datasource flag first
        per_ds_var = _PER_DATASOURCE_FLAGS.get(data_source)
        if per_ds_var:
            per_ds_value = os.environ.get(per_ds_var, "").strip().lower()
            if per_ds_value in _TRUTHY_VALUES:
                return True
            if per_ds_value in _FALSY_VALUES:
                return False
            # If set but not recognized, fall through to global

        # Check global flag
        global_value = os.environ.get(_GLOBAL_FLAG, "").strip().lower()
        if global_value in _TRUTHY_VALUES:
            return True

        # Default: legacy path
        return False
