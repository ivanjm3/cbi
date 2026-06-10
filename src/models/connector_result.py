"""Dataclass for uniform data source connector results.

Defines the ConnectorResult structure returned by all Data_Source_Connectors,
providing a consistent interface for the Result_Assembler regardless of
the underlying data source type.

Requirements: 5.1, 5.4, 5.5
"""

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ConnectorResult:
    """Uniform result from any data source connector.

    Encapsulates either a successful query response (with columns and rows)
    or a structured error indicating what went wrong. The metadata dict
    carries connector-specific information such as timing and query stats.
    """

    status: Literal["success", "error"]
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    data_source: str
    error_type: str | None = None
    error_description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
