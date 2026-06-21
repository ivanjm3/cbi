"""Startup script to register spoke agents with the Orchestrator Hub.

Registers the legacy spoke agents and, when MCP feature flags are enabled,
the MCP adapter agents with the Orchestrator Hub so it can route intents.

Requirements: 6.5, 6.6, 8.1, 8.4
"""

import asyncio
import logging
import os

import httpx

from src.config import AGENT_A_URL, ORCHESTRATOR_URL, REDSHIFT_AGENT_URL

logger = logging.getLogger(__name__)

# MCP Adapter port
MCP_ADAPTER_URL = "http://localhost:8012"

# Single unified agent registration
AGENT_REGISTRATIONS = [
    {
        "agent_id": "spoke-agent",
        "agent_name": "Data Retrieval Agent",
        "data_source": "multi-source",
        "endpoint_url": AGENT_A_URL,
        "entity_refs": [
            "ontology:sales_revenue",
            "ontology:order_volume",
            "ontology:return_rate",
            "ontology:quarterly_report",
            "ontology:product_catalog",
            "ontology:inventory_stock",
            "ontology:product_pricing",
            "ontology:supplier_info",
        ],
    },
    {
        "agent_id": "redshift-spoke-agent",
        "agent_name": "Redshift Spoke Agent",
        "data_source": "redshift",
        "endpoint_url": REDSHIFT_AGENT_URL,
        "entity_refs": [
            "ontology:workforce_metrics",
            "ontology:support_tickets",
            "ontology:marketing_campaigns",
        ],
    },
]

# MCP Adapter agent registrations (conditionally registered when flags are enabled)
MCP_ADAPTER_REGISTRATIONS = [
    {
        "agent_id": "mcp-redshift-adapter",
        "agent_name": "MCP Redshift Adapter",
        "data_source": "redshift",
        "endpoint_url": MCP_ADAPTER_URL,
        "entity_refs": [
            "ontology:workforce_metrics",
            "ontology:support_tickets",
            "ontology:marketing_campaigns",
        ],
        "flag": "USE_MCP_REDSHIFT",
    },
    {
        "agent_id": "mcp-s3-adapter",
        "agent_name": "MCP S3 Adapter",
        "data_source": "s3",
        "endpoint_url": MCP_ADAPTER_URL,
        "entity_refs": [
            "ontology:sales_revenue",
            "ontology:order_volume",
            "ontology:return_rate",
            "ontology:quarterly_report",
            "ontology:product_catalog",
            "ontology:inventory_stock",
            "ontology:product_pricing",
            "ontology:supplier_info",
        ],
        "flag": "USE_MCP_S3",
    },
]


def _should_register_mcp_agent(flag_name: str) -> bool:
    """Check if an MCP adapter agent should be registered.

    Returns True if the per-datasource flag or the global USE_MCP_ADAPTER
    flag is enabled.
    """
    truthy = {"true", "1", "yes", "on"}

    # Check per-datasource flag
    per_ds = os.environ.get(flag_name, "").strip().lower()
    if per_ds in truthy:
        return True

    # Check global flag
    global_flag = os.environ.get("USE_MCP_ADAPTER", "").strip().lower()
    if global_flag in truthy:
        return True

    return False


async def register_agents() -> None:
    """Register spoke agents and (conditionally) MCP adapter agents with the Orchestrator Hub."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Register legacy spoke agents (always)
        for agent_config in AGENT_REGISTRATIONS:
            await _register_single_agent(client, agent_config)

        # Conditionally register MCP adapter agents
        for mcp_config in MCP_ADAPTER_REGISTRATIONS:
            flag_name = mcp_config.get("flag", "")
            if _should_register_mcp_agent(flag_name):
                # Remove the 'flag' key before sending to the API
                registration = {
                    k: v for k, v in mcp_config.items() if k != "flag"
                }
                await _register_single_agent(client, registration)
            else:
                logger.debug(
                    "Skipping MCP adapter registration for %s (flag %s not enabled)",
                    mcp_config["agent_id"],
                    flag_name,
                )


async def _register_single_agent(
    client: httpx.AsyncClient, agent_config: dict
) -> None:
    """Register a single agent with the Orchestrator Hub."""
    try:
        response = await client.post(
            f"{ORCHESTRATOR_URL}/admin/agents",
            json=agent_config,
        )
        if response.status_code == 201:
            logger.info(
                f"Registered agent: {agent_config['agent_id']} "
                f"at {agent_config['endpoint_url']}"
            )
            print(f"  \u2713 Registered: {agent_config.get('agent_name', agent_config['agent_id'])} ({agent_config['agent_id']})")
        else:
            logger.error(
                f"Failed to register {agent_config['agent_id']}: "
                f"{response.status_code} - {response.text}"
            )
    except httpx.ConnectError:
        logger.error(
            f"Cannot connect to Orchestrator Hub at {ORCHESTRATOR_URL}. "
            f"Is it running?"
        )
    except Exception as e:
        logger.error(f"Error registering {agent_config['agent_id']}: {e}")


def main() -> None:
    """Run agent registration as a standalone script."""
    logging.basicConfig(level=logging.INFO)
    print("Registering spoke agent with Orchestrator Hub...")
    asyncio.run(register_agents())
    print("Done.")


if __name__ == "__main__":
    main()
