"""Pydantic model for conversational session state.

Defines the SessionContext used by the Backend_Agent_API to maintain
in-memory conversational state for follow-up queries that reference
prior results.

Requirements: 7.3
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SessionContext(BaseModel):
    """In-memory conversational state for follow-up queries.

    Tracks the history of query/result pairs within a session, along with
    the most recently resolved entity references and data sources, enabling
    the Query_Planner_Agent to handle contextual follow-up questions.
    """

    session_id: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    last_entity_refs: list[str] = Field(default_factory=list)
    last_sources_used: list[str] = Field(default_factory=list)
    created_at: datetime
    last_active: datetime
