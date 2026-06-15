"""Redshift-specific data models for the Conversational BI application.

These models define the data structures used by the Redshift Connector,
Schema Registry, and SQL Generator components.
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RedshiftResult(BaseModel):
    """Structured result from a successful Redshift Data API query execution.

    Contains column metadata, row data, total row count, and the statement
    identifier used for the query.
    """

    columns: list[dict[str, str]] = Field(
        description='Column metadata, e.g. [{"name": "col", "type": "VARCHAR"}]'
    )
    rows: list[list[Any]] = Field(description="Row data as list of value lists")
    row_count: int = Field(description="Total number of rows returned")
    statement_id: str = Field(description="Redshift Data API statement identifier")


class RedshiftError(BaseModel):
    """Structured error returned when a Redshift operation fails.

    Classifies the failure into one of four error types for consistent
    error handling across the application.
    """

    error_type: Literal["TIMEOUT", "AUTH_FAILURE", "QUERY_FAILURE", "CONNECTION_ERROR"]
    description: str
    elapsed_seconds: float | None = None


class ColumnClassification(str, Enum):
    """Classification of a Redshift column for query generation purposes.

    - categorical: usable in GROUP BY and WHERE equality filters
    - numeric: usable in aggregate functions (SUM, AVG, COUNT, MIN, MAX)
    - identifier: usable only in SELECT and WHERE equality filters,
      not in aggregations or GROUP BY
    """

    CATEGORICAL = "categorical"
    NUMERIC = "numeric"
    IDENTIFIER = "identifier"


class ColumnDef(BaseModel):
    """Definition of a single column in a Redshift table mapping.

    Includes the column name, its classification for query generation,
    and the SQL data type.
    """

    name: str
    classification: ColumnClassification
    sql_type: str


class FilterMapping(BaseModel):
    """Maps a filterable keyword to a target column and comparison operator.

    Used by the SQL Generator to translate entity_ref filter values into
    WHERE clause conditions.
    """

    keyword: str
    target_column: str
    operator: Literal["equals", "in", "greater_than", "less_than", "between", "like"]


class TableMapping(BaseModel):
    """Maps an ontology concept to a Redshift table with full column and filter metadata.

    Used by the Schema Registry to resolve entity_refs to table/column
    information for SQL generation.
    """

    concept_id: str
    table_name: str
    columns: list[ColumnDef]
    filter_mappings: list[FilterMapping]


class GeneratedQuery(BaseModel):
    """Result of successful SQL generation from a StructuredIntent.

    Contains the parameterized SQL string, parameter values, the resolved
    table name, and the query type that was generated.
    """

    sql: str
    parameters: list[dict[str, Any]]
    table_name: str
    query_type: str


class SQLGeneratorError(BaseModel):
    """Error returned when SQL generation fails.

    Covers cases where entity_refs cannot be resolved or the query type
    is not supported.
    """

    error_type: Literal["UNRESOLVED_ENTITY", "INVALID_QUERY_TYPE"]
    description: str
