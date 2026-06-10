"""Pydantic models for Source Registry configuration.

Defines the structure for column descriptors, schema descriptors, and
source configurations used by the Source_Registry to store metadata
about registered data sources.

Requirements: 3.1, 3.2
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnDescriptor(BaseModel):
    """A single column in a schema descriptor.

    Describes the name, type, nullability, and purpose of a column
    within a registered data source's schema.
    """

    name: str
    data_type: Literal["string", "integer", "float", "boolean", "datetime"]
    nullable: bool = True
    description: str = ""


class SchemaDescriptor(BaseModel):
    """Describes the structure of a data source.

    Contains the list of columns, an optional primary key, and references
    to related sources. Used by the Query_Planner_Agent for informed
    routing and field validation.
    """

    columns: list[ColumnDescriptor] = Field(default_factory=list)
    primary_key: str | None = None
    relationships: list[str] = Field(default_factory=list)


class SourceConfig(BaseModel):
    """Configuration for a registered data source.

    Stores all metadata needed to connect to, query, and reason about
    a data source including its connector type, connection parameters,
    schema, and the ontology concepts it provides data for.
    """

    model_config = {"populate_by_name": True}

    source_id: str
    source_name: str
    connector_type: Literal["sql", "dynamodb", "csv", "logs", "s3_json"]
    connection_params: dict[str, Any] = Field(default_factory=dict)
    source_schema: SchemaDescriptor = Field(
        default_factory=SchemaDescriptor, alias="schema"
    )
    ontology_concepts: list[str] = Field(default_factory=list)
    enabled: bool = True
