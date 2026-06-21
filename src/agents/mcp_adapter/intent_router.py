"""Intent Router for the MCP Adapter Layer.

Resolves entity_refs from a StructuredIntent via the OntologyStore to
determine which MCP server(s) should handle the request. Maps data_source
properties to server IDs and dataset names.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.models.shared import AgentResult, StructuredIntent

from .models import RoutingTarget

if TYPE_CHECKING:
    from src.services.ontology_store import OntologyStore

logger = logging.getLogger(__name__)

# Mapping from ontology data_source values to (server_id, dataset_name)
_DATA_SOURCE_MAP: dict[str, tuple[str, str | None]] = {
    "financial_data": ("s3", "financial_data"),
    "product_catalog": ("s3", "product_catalog"),
    "redshift": ("redshift", None),
}


class IntentRouter:
    """Routes StructuredIntent to appropriate MCP server based on entity_refs.

    Resolves each entity_ref by looking up the concept in the OntologyStore
    and reading its `data_source` property to determine which MCP server
    and dataset should handle it.
    """

    def __init__(self, ontology_store: OntologyStore) -> None:
        self.ontology_store = ontology_store

    def resolve_targets(
        self, intent: StructuredIntent
    ) -> list[RoutingTarget] | AgentResult:
        """Resolve entity_refs to RoutingTarget(s) with server_id and dataset info.

        Args:
            intent: The StructuredIntent containing entity_refs to resolve.

        Returns:
            A list of RoutingTarget objects grouped by server_id/dataset, or
            an AgentResult with error_type "UNROUTABLE_ENTITY" if no entity
            can be resolved.
        """
        # Accumulate routing info per (server_id, dataset_name)
        targets: dict[tuple[str, str | None], list[str]] = {}
        unresolved: list[str] = []

        for entity_ref in intent.entity_refs:
            concept = self.ontology_store.lookup_concept(entity_ref)

            if concept is None:
                unresolved.append(entity_ref)
                continue

            data_source = concept.properties.get("data_source")

            if data_source is None:
                # Dimension/reference concepts without data_source are unroutable
                unresolved.append(entity_ref)
                continue

            mapping = _DATA_SOURCE_MAP.get(data_source)

            if mapping is None:
                # Unknown data_source value
                logger.warning(
                    "Unknown data_source '%s' for entity_ref '%s'",
                    data_source,
                    entity_ref,
                )
                unresolved.append(entity_ref)
                continue

            server_id, dataset_name = mapping
            key = (server_id, dataset_name)

            if key not in targets:
                targets[key] = []
            targets[key].append(entity_ref)

        # If no entity resolved successfully, return error
        if not targets:
            return AgentResult(
                status="error",
                error_type="UNROUTABLE_ENTITY",
                error_description=(
                    f"Could not resolve entity_refs to any configured MCP server: "
                    f"{', '.join(unresolved or intent.entity_refs)}"
                ),
                agent_id="mcp-adapter",
                data_source="unknown",
            )

        # Build RoutingTarget list
        result: list[RoutingTarget] = []
        for (server_id, dataset_name), entity_refs in targets.items():
            result.append(
                RoutingTarget(
                    server_id=server_id,
                    dataset_name=dataset_name,
                    entity_refs=entity_refs,
                )
            )

        return result
