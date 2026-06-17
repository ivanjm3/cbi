"""Shared Pydantic data models for the Ontology NLP Query System.

These models define the core data structures used for inter-service
communication throughout the hub-and-spoke architecture.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

class StructuredIntent(BaseModel):
    """Machine-readable representation of a user query produced by the NLP Translator.
    Contains the parsed query type, resolved ontology entity references,
    routing hints, and metadata for tracing.
    """
    query_id: UUID
    query_type: Literal["lookup", "aggregation", "comparison"]
    entity_refs: list[str] = Field(min_length=1)
    routing_metadata: dict
    timestamp: datetime

class AgentResult(BaseModel):
    """Structured response from a Spoke Agent after querying its data source.
    Contains either a successful payload or error information describing
    why the query failed.
    """
    status: Literal["success", "error"]
    payload: dict | None = None
    error_type: str | None = None
    error_description: str | None = None
    agent_id: str
    data_source: str

class OrchestratorResponse(BaseModel):
    """Merged response from the Orchestrator Hub after dispatching to Spoke Agents.
    Combines results from all responding agents and identifies any agents
    that did not respond within the timeout window.
    """
    query_id: UUID
    results: list[AgentResult]
    unavailable_agents: list[str] = Field(default_factory=list)

class OrchestratorError(BaseModel):
    """Structured error returned by the Orchestrator Hub when dispatch fails.
    Covers cases where no agents could be resolved for the query, all
    dispatched agents timed out, or the query was cancelled.
    """
    error_type: Literal["NO_AGENTS_RESOLVED", "ALL_AGENTS_TIMED_OUT", "QUERY_CANCELLED"]
    message: str
    query_id: UUID

class NLPError(BaseModel):
    """Structured error returned by the NLP Translator when parsing fails.
    Covers unparseable queries, missing ontology matches, and ambiguous intents.
    """
    error_code: Literal["UNPARSEABLE_QUERY", "NO_ONTOLOGY_MATCH", "AMBIGUOUS_INTENT"]
    error_message: str
    query_id: UUID

class GuardrailResult(BaseModel):
    """Result from the Guardrail Layer after validating an orchestrator response.
    Indicates whether the response passed, was partially redacted, was fully
    rejected, or encountered an internal error during validation.
    """
    status: Literal["passed", "redacted", "rejected", "error"]
    validated_response: OrchestratorResponse | None = None
    applied_rules: list[str] = Field(default_factory=list)
    error_details: str | None = None


class RenderedOutput(BaseModel):
    """Final visualization output returned to the UI.
    Contains either chart data (with type and spec) or plain text content,
    along with a human-readable description and metadata for tracing.
    """
    output_type: Literal["chart", "text"]
    chart_type: str | None = None
    chart_data: dict | None = None
    text_content: str | None = None
    description: str
    metadata: dict

class AgentRegistration(BaseModel):
    """Configuration for registering a Spoke Agent with the Orchestrator Hub.
    Maps an agent to its data source endpoint and the ontology concepts it handles.
    """
    agent_id: str
    agent_name: str
    data_source: str
    endpoint_url: str
    entity_refs: list[str]