"""Pydantic models for ontology definitions.
Defines the structure for concepts, relationships, and full ontology
definitions used by the Ontology Store. These models support serialization
round-trip consistency (JSON ↔ in-memory) and schema validation on ingest.
Requirements: 3.1, 12.1
"""

from typing import Any
from pydantic import BaseModel, Field

class OntologyRelationship(BaseModel):
    """A directed relationship between two ontology concepts.
    Represents edges in the ontology graph, connecting a source concept
    to a target concept with a typed relation and optional properties.
    """

    source_id: str
    target_id: str
    relation_type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class OntologyConcept(BaseModel):
    """A single concept in the ontology.
    Represents a node in the ontology graph with a unique identifier,
    human-readable label, arbitrary properties, and its outgoing relationships.
    """
    concept_id: str
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)
    relationships: list[OntologyRelationship] = Field(default_factory=list)


class OntologyDefinition(BaseModel):
    """A complete ontology definition containing concepts and relationships.
    This is the top-level structure for serialization, storage, and exchange.
    The metadata dict can hold version, name, timestamps, or any other
    administrative information about the ontology.
    """
    concepts: list[OntologyConcept] = Field(default_factory=list)
    relationships: list[OntologyRelationship] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)