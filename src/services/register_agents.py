"""Startup script to register the unified spoke agent with the Orchestrator Hub.

Registers the single spoke agent with all ontology entity mappings so the
Orchestrator Hub can route intents to it. The spoke agent handles both
financial data (JSON) and product catalog (CSV) internally.

Requirements: 6.5, 6.6
"""

import asyncio
import logging

import httpx

from src.config import AGENT_A_URL, ORCHESTRATOR_URL

logger = logging.getLogger(__name__)

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
            "ontology:product_category",
            "ontology:region",
        ],
    },
]


async def register_agents() -> None:
    """Register the spoke agent with the Orchestrator Hub."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        for agent_config in AGENT_REGISTRATIONS:
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
                    print(f"  ✓ Registered: {agent_config['agent_name']} ({agent_config['agent_id']})")
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
                break
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
