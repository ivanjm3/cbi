"""Orchestrator Hub — Strands Agent with tool-based routing and dispatch.

Central routing agent that checks the Result Cache, resolves agents from
the Ontology Store via entity_refs, dispatches work to Spoke Agents using
Strands SDK tool-calling, and merges results into a single response.

The Orchestrator supports two dispatch modes:
1. MCP dispatch (default): Calls MCP server tools over Streamable HTTP
2. Legacy HTTP dispatch: POSTs to spoke agent FastAPI endpoints (fallback)

The dispatch mode is chosen based on whether MCP servers are reachable.

Supports runtime agent registration and deregistration without restart.

Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.8, 4.9, 6.5, 6.6
"""

import json
import logging
from typing import Any, Callable, Optional

import httpx
from strands import Agent, tool

from src.config import (
    AGENT_TIMEOUT_DEFAULT,
    AGENT_TIMEOUT_MAX,
    AGENT_TIMEOUT_MIN,
    DEFAULT_MODEL_ID,
)
from src.models.shared import (
    AgentRegistration,
    AgentResult,
    OrchestratorError,
    OrchestratorResponse,
    StructuredIntent,
)
from src.services.cancellation_registry import CancellationRegistry
from src.services.ontology_store import OntologyStore
from src.services.result_cache import ResultCache

logger = logging.getLogger(__name__)

# Module-level state shared with @tool functions.
# The Strands @tool decorator requires standalone functions, so we use module
# state to give them access to the hub's registry, cache, and config.
_hub_instance: "OrchestratorHub | None" = None

# Accumulator for dispatch results collected during a single process_intent call.
# Reset before each agent invocation to collect fresh results.
_dispatch_results: list[dict[str, Any]] = []

# Global callback for agent registry updates (used to sync with NLPTranslator)
_agent_registry_callback: Optional[Callable] = None


def set_agent_registry_callback(callback: Callable) -> None:
    """Set a callback to be invoked when the agent registry changes.

    This allows external components (like NLPTranslator) to keep their
    agent registry in sync with the orchestrator's registry.

    Args:
        callback: A callable that receives a list of registered agent IDs.
    """
    global _agent_registry_callback
    _agent_registry_callback = callback


def _normalize_columns(columns: list) -> list[str]:
    """Normalize column data to a flat list of string names.

    MCP servers may return columns as dicts (e.g. {"name": "col", "type": "VARCHAR"})
    or as plain strings. The visualization pipeline expects plain strings.

    Args:
        columns: List of column names (strings) or column metadata (dicts).

    Returns:
        List of column name strings.
    """
    if not columns:
        return []
    result = []
    for col in columns:
        if isinstance(col, str):
            result.append(col)
        elif isinstance(col, dict):
            result.append(col.get("name", col.get("column_name", str(col))))
        else:
            result.append(str(col))
    return result


@tool
def check_result_cache(cache_key: str) -> str:
    """Check the result cache for a previously computed response.

    Args:
        cache_key: The deterministic hash key for the structured intent.

    Returns:
        JSON string of the cached OrchestratorResponse if found, or "CACHE_MISS".
    """
    if _hub_instance is None:
        return "ERROR: Hub not initialized"
    cached = _hub_instance.result_cache.get(cache_key)
    if cached is not None:
        return json.dumps({"status": "CACHE_HIT", "response": cached.model_dump(mode="json")})
    return json.dumps({"status": "CACHE_MISS"})


@tool
def resolve_available_agents(entity_refs: list[str]) -> str:
    """Resolve which registered spoke agents handle the given ontology entity references.

    Looks up the agent registry to find agents whose entity_refs overlap
    with the provided list.

    Args:
        entity_refs: List of canonical ontology concept identifiers from the structured intent.

    Returns:
        JSON string with list of matching agent registrations.
    """
    if _hub_instance is None:
        return "ERROR: Hub not initialized"
    entity_set = set(entity_refs)
    resolved = []
    for agent in _hub_instance._agents.values():
        agent_entities = set(agent.entity_refs)
        if agent_entities & entity_set:
            resolved.append({
                "agent_id": agent.agent_id,
                "agent_name": agent.agent_name,
                "endpoint_url": agent.endpoint_url,
                "data_source": agent.data_source,
                "entity_refs": agent.entity_refs,
            })
    return json.dumps({"resolved_agents": resolved, "count": len(resolved)})


@tool
def dispatch_to_spoke_agent(agent_id: str, endpoint_url: str, intent_json: str) -> str:
    """Dispatch a structured intent to a specific spoke agent and return its result.

    Makes an HTTP POST call to the spoke agent's invoke endpoint with the
    structured intent. Handles timeouts and connection errors.

    This is the LEGACY dispatch path. Prefer MCP dispatch via
    dispatch_via_mcp when MCP servers are available.

    Args:
        agent_id: The identifier of the spoke agent to call.
        endpoint_url: The base URL of the spoke agent (e.g. http://localhost:8010).
        intent_json: JSON-serialized structured intent to send to the agent.

    Returns:
        JSON string with the agent's response or error details.
    """
    if _hub_instance is None:
        result = {"status": "error", "agent_id": agent_id, "error_type": "HUB_NOT_INITIALIZED"}
        _dispatch_results.append(result)
        return json.dumps(result)

    timeout = _hub_instance.agent_timeout
    correlation_id = _hub_instance._current_correlation_id

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if correlation_id:
        headers["X-Correlation-ID"] = correlation_id

    try:
        intent_data = json.loads(intent_json)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                f"{endpoint_url}/agents/{agent_id}/invoke",
                json={"structured_intent": intent_data},
                headers=headers,
            )

            if response.status_code == 200:
                result = {
                    "status": "success",
                    "agent_id": agent_id,
                    "result": response.json(),
                }
            else:
                result = {
                    "status": "error",
                    "agent_id": agent_id,
                    "error_type": "HTTP_ERROR",
                    "error_description": f"Agent returned status {response.status_code}",
                    "response_body": response.text[:500],
                }

    except httpx.TimeoutException:
        result = {
            "status": "error",
            "agent_id": agent_id,
            "error_type": "TIMEOUT",
            "error_description": f"Agent timed out after {timeout}s",
        }
    except httpx.ConnectError as e:
        result = {
            "status": "error",
            "agent_id": agent_id,
            "error_type": "CONNECTION_ERROR",
            "error_description": str(e),
        }
    except Exception as e:
        result = {
            "status": "error",
            "agent_id": agent_id,
            "error_type": type(e).__name__,
            "error_description": str(e),
        }

    _dispatch_results.append(result)
    return json.dumps(result)


@tool
def dispatch_via_mcp(entity_refs: list[str], query_type: str, query_text: str, routing_metadata: dict | None = None) -> str:
    """Dispatch data retrieval via MCP servers based on entity refs.

    Calls the appropriate MCP server tools (S3 or Redshift) based on
    which ontology concepts are referenced. This is the PRIMARY dispatch
    path when MCP servers are available.

    Args:
        entity_refs: List of ontology concept IDs from the structured intent.
        query_type: Query type — one of 'lookup', 'aggregation', 'comparison'.
        query_text: Original query text for context in SQL generation.
        routing_metadata: Optional routing metadata with hints like group_by_hint.

    Returns:
        JSON string with results from MCP tool calls.
    """
    import asyncio

    from src.mcp_servers.mcp_client import get_mcp_client

    mcp_client = get_mcp_client()
    
    if routing_metadata is None:
        routing_metadata = {}

    try:
        # Try to get existing event loop
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                asyncio.run,
                mcp_client.dispatch_for_entity_refs(entity_refs, query_type, query_text, routing_metadata),
            )
            mcp_results = future.result(timeout=60)
    except RuntimeError:
        # No running loop
        mcp_results = asyncio.run(
            mcp_client.dispatch_for_entity_refs(entity_refs, query_type, query_text, routing_metadata)
        )

    # Convert MCP results into dispatch_results format for _build_response_from_results
    for mcp_result in mcp_results:
        if "error" in mcp_result:
            dispatch_entry = {
                "status": "error",
                "agent_id": f"mcp-{mcp_result.get('server', 'unknown')}",
                "error_type": "MCP_ERROR",
                "error_description": mcp_result.get("error", "Unknown MCP error"),
            }
        else:
            # Build an AgentResult-compatible payload
            source = mcp_result.pop("_source", "mcp")
            entity_refs_used = mcp_result.pop("_entity_refs", [])
            sql_used = mcp_result.pop("_sql", None)

            # Determine agent_id and data_source from the source
            if source.startswith("s3:"):
                agent_id = "mcp-s3-server"
                data_source = source.replace("s3:", "")
            elif source.startswith("redshift:"):
                agent_id = "mcp-redshift-server"
                data_source = source.replace("redshift:", "")
            else:
                agent_id = "mcp-unknown"
                data_source = source

            # Format as AgentResult payload
            columns_normalized = _normalize_columns(mcp_result.get("columns", []))
            rows_raw = mcp_result.get("rows", [])

            # Normalize rows: MCP may return list of dicts or list of lists
            if rows_raw and isinstance(rows_raw[0], dict):
                rows_normalized = [
                    [row.get(col, None) for col in columns_normalized]
                    for row in rows_raw
                ]
            else:
                rows_normalized = rows_raw

            payload = {
                "data_type": "tabular",
                "columns": columns_normalized,
                "rows": rows_normalized,
                "row_count": mcp_result.get("row_count", len(rows_normalized)),
            }

            # Preserve additional metadata
            if sql_used:
                payload["sql_query"] = sql_used
            if mcp_result.get("format"):
                payload["format"] = mcp_result["format"]
            if mcp_result.get("total_rows"):
                payload["total_rows"] = mcp_result["total_rows"]

            dispatch_entry = {
                "status": "success",
                "agent_id": agent_id,
                "result": {
                    "status": "success",
                    "payload": payload,
                    "agent_id": agent_id,
                    "data_source": data_source,
                },
            }

        _dispatch_results.append(dispatch_entry)

    return json.dumps({"mcp_dispatch_count": len(mcp_results), "results": mcp_results})


ORCHESTRATOR_SYSTEM_PROMPT = """\
You are an Orchestrator Agent responsible for intelligently routing data queries \
to the most relevant spoke agents.

Your workflow for each query:
1. First, check the result cache using the provided cache key. If there's a \
cache hit, return the cached response immediately.
2. If cache miss, resolve which spoke agents are available by looking up the \
entity_refs.
3. Analyze the query intent, the ontology context, and each agent's data source \
to decide which agent(s) are actually needed to answer the query. Consider:
   - What specific data does the query need?
   - Which agent's data source contains that data?
   - Does the query require combining data from multiple sources, or can a \
single agent answer it?
4. Dispatch the structured intent ONLY to the agent(s) whose data source is \
relevant to answering the query.
5. Collect all results and report them back.

Important rules:
- Always check the cache first.
- Be selective: only dispatch to agents whose data source is relevant to the \
query. Do NOT dispatch to all agents by default.
- If the query clearly needs data from multiple sources (e.g., a comparison \
between products and financials), dispatch to multiple agents.
- If the query targets a single domain (e.g., "show me revenue"), dispatch only \
to the agent that owns that data.
- Report both successful results and any agent failures/timeouts.
- Do not modify the structured intent — pass it through as-is to agents.
"""


class OrchestratorHub:
    """Central routing agent for the hub-and-spoke architecture.

    Implemented as a Strands Agent that uses @tool-decorated functions to:
    - Check the Result Cache for existing results
    - Resolve responsible agents from the registry based on entity_refs
    - Dispatch structured intents to spoke agents via HTTP

    The LLM reasons about which agents to invoke and handles the dispatch
    strategy based on the query's ontology context.

    Supports runtime agent registration and deregistration.
    """

    def __init__(
        self,
        ontology_store: OntologyStore | None = None,
        result_cache: ResultCache | None = None,
        agent_timeout: float = AGENT_TIMEOUT_DEFAULT,
        model_id: str | None = None,
        cancellation_registry: CancellationRegistry | None = None,
    ):
        """Initialize the Orchestrator Hub.

        Args:
            ontology_store: The ontology store for agent resolution context.
                Defaults to a flat-file store using the configured directory.
            result_cache: The result cache for avoiding redundant dispatches.
                Defaults to a new in-memory cache.
            agent_timeout: Per-agent timeout in seconds (1-300, default 30).
            model_id: Optional Bedrock model ID override for the Strands Agent.
            cancellation_registry: Optional registry for cooperative cancellation.
                Defaults to a new CancellationRegistry instance.
        """
        global _hub_instance
        _hub_instance = self

        self.ontology_store = ontology_store or OntologyStore()
        self.result_cache = result_cache or ResultCache()
        self.agent_timeout = max(
            AGENT_TIMEOUT_MIN, min(agent_timeout, AGENT_TIMEOUT_MAX)
        )
        self._model_id = model_id or DEFAULT_MODEL_ID
        # In-memory agent registry: agent_id -> AgentRegistration
        self._agents: dict[str, AgentRegistration] = {}
        # Correlation ID for the current request (set per-request)
        self._current_correlation_id: str = ""
        # Cancellation registry for cooperative query cancellation
        self._cancellation_registry = cancellation_registry or CancellationRegistry()

        # Initialize the Strands Agent with orchestrator tools
        from botocore.config import Config as BotoConfig

        from src.config import get_strands_bedrock_model

        agent_kwargs: dict[str, Any] = {
            "system_prompt": ORCHESTRATOR_SYSTEM_PROMPT,
            "tools": [check_result_cache, resolve_available_agents, dispatch_to_spoke_agent, dispatch_via_mcp],
            "model": get_strands_bedrock_model(model_id),
            "callback_handler": None,
        }

        self._agent = Agent(**agent_kwargs)

    async def process_intent(
        self, intent: StructuredIntent, correlation_id: str = ""
    ) -> OrchestratorResponse | OrchestratorError:
        """Process a structured intent: check cache, resolve agents, dispatch.

        Uses AGENTIC dispatch for multi-domain queries (entity_refs span
        multiple agent domains) and direct dispatch for single-domain queries.
        The Strands Agent reasons about which agents to call and how to
        merge results for complex cross-domain queries.

        Checks the cancellation registry before dispatching and returns
        QUERY_CANCELLED if the correlation ID has been cancelled.

        Args:
            intent: The structured intent from the NLP Translator.
            correlation_id: The correlation ID for downstream propagation.

        Returns:
            OrchestratorResponse on success, OrchestratorError on failure.
        """
        self._current_correlation_id = correlation_id

        # Check if already cancelled before starting any work
        if correlation_id and self._cancellation_registry.is_cancelled(correlation_id):
            logger.info(
                json.dumps({
                    "service_name": "orchestrator_hub",
                    "operation": "process_intent",
                    "event": "query_cancelled_before_dispatch",
                    "query_id": str(intent.query_id),
                    "correlation_id": correlation_id,
                })
            )
            return OrchestratorError(
                error_type="QUERY_CANCELLED",
                message="Query was cancelled before dispatch.",
                query_id=intent.query_id,
            )

        # Step 1: Check cache (Requirement 4.1, 4.2)
        cache_key = ResultCache.generate_key(intent)
        cached = self.result_cache.get(cache_key)
        if cached is not None:
            logger.info(
                json.dumps({
                    "service_name": "orchestrator_hub",
                    "operation": "process_intent",
                    "event": "cache_hit",
                    "query_id": str(intent.query_id),
                })
            )
            return cached

        # Step 2: Resolve agents (Requirement 4.3)
        resolved_agents = self._resolve_agents(intent.entity_refs)
        if not resolved_agents:
            return OrchestratorError(
                error_type="NO_AGENTS_RESOLVED",
                message=(
                    f"No agents could be resolved for entity_refs: {intent.entity_refs}. "
                    "No registered agents handle these ontology concepts."
                ),
                query_id=intent.query_id,
            )

        # Step 3: Choose dispatch strategy based on query complexity
        # AGENTIC: For multi-agent queries, let the LLM reason about routing.
        # DIRECT: For single-agent queries, skip the LLM for speed.
        if len(resolved_agents) > 1 and intent.query_type == "comparison":
            # Multi-domain comparison — use agentic dispatch
            logger.info(json.dumps({
                "service_name": "orchestrator_hub",
                "operation": "process_intent",
                "event": "agentic_dispatch",
                "query_id": str(intent.query_id),
                "resolved_agent_count": len(resolved_agents),
            }))
            return self._agent_dispatch(intent, resolved_agents, cache_key)
        else:
            # Single-domain or simple query — fast direct dispatch
            return self._direct_dispatch(intent, resolved_agents, cache_key)

    def register_cancellation(self, correlation_id: str) -> None:
        """Register a correlation ID as cancelled in the hub's registry.

        Called by the orchestrator API when it receives a cancellation
        request from the NLP API.

        Args:
            correlation_id: The query identifier to cancel.
        """
        self._cancellation_registry.register(correlation_id, source="propagated")

    def _agent_dispatch(
        self,
        intent: StructuredIntent,
        resolved_agents: list[AgentRegistration],
        cache_key: str,
    ) -> OrchestratorResponse | OrchestratorError:
        """Dispatch via the Strands Agent with LLM-based reasoning.

        The agent reasons about which spoke agents to invoke based on
        the intent's entity_refs and ontology context, then uses the
        dispatch_to_spoke_agent tool to call them.

        Checks cancellation before invoking the Strands Agent.

        Tool call results are captured in the module-level _dispatch_results
        accumulator during execution.

        Args:
            intent: The structured intent to dispatch.
            resolved_agents: Pre-resolved list of candidate agents.
            cache_key: The cache key for storing results on success.

        Returns:
            OrchestratorResponse or OrchestratorError.
        """
        global _dispatch_results
        _dispatch_results = []  # Reset accumulator for this request

        correlation_id = self._current_correlation_id

        # Check cancellation before invoking the (expensive) Strands Agent
        if correlation_id and self._cancellation_registry.is_cancelled(correlation_id):
            logger.info(
                json.dumps({
                    "service_name": "orchestrator_hub",
                    "operation": "_agent_dispatch",
                    "event": "cancelled_before_agent_invocation",
                    "query_id": str(intent.query_id),
                    "correlation_id": correlation_id,
                })
            )
            return OrchestratorError(
                error_type="QUERY_CANCELLED",
                message="Query was cancelled before agent dispatch.",
                query_id=intent.query_id,
            )

        intent_json = intent.model_dump_json()

        # Build ontology context for the agent's reasoning
        ontology_context = []
        for entity_ref in intent.entity_refs:
            concept = self.ontology_store.lookup_concept(entity_ref)
            if concept:
                ontology_context.append({
                    "concept_id": concept.concept_id,
                    "label": concept.label,
                    "properties": concept.properties,
                })
        ontology_json = json.dumps(ontology_context, indent=2) if ontology_context else "[]"

        agent_list = json.dumps(
            [
                {
                    "agent_id": a.agent_id,
                    "data_source": a.data_source,
                    "endpoint_url": a.endpoint_url,
                    "handles_entities": a.entity_refs,
                }
                for a in resolved_agents
            ],
            indent=2,
        )

        prompt = (
            f"Process this query by selecting and dispatching to the most relevant agent(s).\n\n"
            f"Cache key: {cache_key}\n"
            f"Query type: {intent.query_type}\n"
            f"Entity refs: {intent.entity_refs}\n"
            f"Routing metadata: {json.dumps(intent.routing_metadata)}\n\n"
            f"Ontology context for the entities in this query:\n{ontology_json}\n\n"
            f"Available agents and their data sources:\n{agent_list}\n\n"
            f"Structured Intent (JSON — pass this exactly to agents):\n{intent_json}\n\n"
            f"Decide which agent(s) are needed based on the query type, entities, and "
            f"each agent's data source. Then dispatch using dispatch_to_spoke_agent for "
            f"each selected agent."
        )

        # Invoke the Strands Agent — tool calls populate _dispatch_results
        result = self._agent(prompt)

        # Build response from accumulated dispatch results
        return self._build_response_from_results(intent, resolved_agents, cache_key)

    def _direct_dispatch(
        self,
        intent: StructuredIntent,
        resolved_agents: list[AgentRegistration],
        cache_key: str,
    ) -> OrchestratorResponse | OrchestratorError:
        """Dispatch via MCP servers first, falling back to legacy HTTP agents.

        Tries MCP dispatch (Streamable HTTP to MCP servers) as the primary
        path. If MCP fails (servers unreachable), falls back to the legacy
        HTTP POST dispatch to spoke agent FastAPI endpoints.

        Checks cancellation registry before dispatch.

        Args:
            intent: The structured intent to dispatch.
            resolved_agents: List of resolved agent registrations.
            cache_key: The cache key for storing results on success.

        Returns:
            OrchestratorResponse or OrchestratorError.
        """
        global _dispatch_results
        _dispatch_results = []  # Reset accumulator

        correlation_id = self._current_correlation_id

        # Check cancellation before starting
        if correlation_id and self._cancellation_registry.is_cancelled(correlation_id):
            return OrchestratorError(
                error_type="QUERY_CANCELLED",
                message="Query was cancelled before dispatch.",
                query_id=intent.query_id,
            )

        # PRIMARY PATH: Try MCP dispatch
        try:
            query_text = intent.routing_metadata.get("query_text", "") if intent.routing_metadata else ""
            dispatch_via_mcp(
                entity_refs=intent.entity_refs,
                query_type=intent.query_type,
                query_text=query_text,
                routing_metadata=intent.routing_metadata or {},
            )

            # Check if MCP dispatch produced results
            if _dispatch_results:
                has_success = any(r.get("status") == "success" for r in _dispatch_results)
                if has_success:
                    logger.info(
                        json.dumps({
                            "service_name": "orchestrator_hub",
                            "operation": "_direct_dispatch",
                            "event": "mcp_dispatch_success",
                            "query_id": str(intent.query_id),
                            "dispatch_count": len(_dispatch_results),
                        })
                    )
                    return self._build_response_from_results(intent, resolved_agents, cache_key)
        except Exception as e:
            logger.warning(
                json.dumps({
                    "service_name": "orchestrator_hub",
                    "operation": "_direct_dispatch",
                    "event": "mcp_dispatch_failed_fallback_to_http",
                    "query_id": str(intent.query_id),
                    "error": str(e),
                })
            )
            _dispatch_results = []  # Reset for fallback

        # FALLBACK PATH: Legacy HTTP dispatch to spoke agents
        import asyncio
        import concurrent.futures

        intent_json = intent.model_dump_json()

        try:
            loop = asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor() as pool:
                for agent in resolved_agents:
                    if correlation_id and self._cancellation_registry.is_cancelled(correlation_id):
                        logger.info(
                            json.dumps({
                                "service_name": "orchestrator_hub",
                                "operation": "_direct_dispatch",
                                "event": "cancelled_mid_dispatch",
                                "query_id": str(intent.query_id),
                                "correlation_id": correlation_id,
                                "skipped_agent": agent.agent_id,
                            })
                        )
                        break
                    future = pool.submit(
                        dispatch_to_spoke_agent,
                        agent_id=agent.agent_id,
                        endpoint_url=agent.endpoint_url,
                        intent_json=intent_json,
                    )
                    future.result()
        except RuntimeError:
            for agent in resolved_agents:
                if correlation_id and self._cancellation_registry.is_cancelled(correlation_id):
                    logger.info(
                        json.dumps({
                            "service_name": "orchestrator_hub",
                            "operation": "_direct_dispatch",
                            "event": "cancelled_mid_dispatch",
                            "query_id": str(intent.query_id),
                            "correlation_id": correlation_id,
                            "skipped_agent": agent.agent_id,
                        })
                    )
                    break
                dispatch_to_spoke_agent(
                    agent_id=agent.agent_id,
                    endpoint_url=agent.endpoint_url,
                    intent_json=intent_json,
                )

        # If cancelled, return QUERY_CANCELLED error
        if correlation_id and self._cancellation_registry.is_cancelled(correlation_id):
            return OrchestratorError(
                error_type="QUERY_CANCELLED",
                message="Query was cancelled during dispatch.",
                query_id=intent.query_id,
            )

        return self._build_response_from_results(intent, resolved_agents, cache_key)

    def _build_response_from_results(
        self,
        intent: StructuredIntent,
        resolved_agents: list[AgentRegistration],
        cache_key: str,
    ) -> OrchestratorResponse | OrchestratorError:
        """Build an OrchestratorResponse from the accumulated dispatch results.

        Parses _dispatch_results to separate successful results from
        unavailable agents. Caches successful responses.

        Args:
            intent: The original structured intent.
            resolved_agents: The agents that were candidates for dispatch.
            cache_key: The cache key for storing the result.

        Returns:
            OrchestratorResponse or OrchestratorError.
        """
        results: list[AgentResult] = []
        unavailable: list[str] = []
        dispatched_agent_ids: set[str] = set()

        for dispatch_result in _dispatch_results:
            agent_id = dispatch_result.get("agent_id", "unknown")
            dispatched_agent_ids.add(agent_id)

            if dispatch_result.get("status") == "success" and "result" in dispatch_result:
                try:
                    agent_result = AgentResult.model_validate(dispatch_result["result"])
                    results.append(agent_result)
                except Exception:
                    # Result didn't conform to AgentResult schema
                    unavailable.append(agent_id)
            else:
                unavailable.append(agent_id)

        # If no agents were dispatched at all (LLM didn't call the tool),
        # treat all resolved agents as dispatched via fallback
        if not dispatched_agent_ids and resolved_agents:
            logger.warning(
                json.dumps({
                    "service_name": "orchestrator_hub",
                    "operation": "_build_response_from_results",
                    "event": "no_dispatches_detected",
                    "query_id": str(intent.query_id),
                })
            )
            # Re-attempt dispatch to all resolved agents
            intent_json = intent.model_dump_json()
            for agent in resolved_agents:
                dispatch_to_spoke_agent(
                    agent_id=agent.agent_id,
                    endpoint_url=agent.endpoint_url,
                    intent_json=intent_json,
                )
            # Rebuild from updated accumulator
            for dispatch_result in _dispatch_results:
                agent_id = dispatch_result.get("agent_id", "unknown")
                if agent_id in dispatched_agent_ids:
                    continue  # Already processed
                dispatched_agent_ids.add(agent_id)

                if dispatch_result.get("status") == "success" and "result" in dispatch_result:
                    try:
                        agent_result = AgentResult.model_validate(dispatch_result["result"])
                        results.append(agent_result)
                    except Exception:
                        unavailable.append(agent_id)
                else:
                    unavailable.append(agent_id)

        # Requirement 4.8: All agents timed out
        if not results and unavailable:
            return OrchestratorError(
                error_type="ALL_AGENTS_TIMED_OUT",
                message=(
                    f"All dispatched agents failed: {unavailable}. "
                    f"Timeout was {self.agent_timeout}s per agent."
                ),
                query_id=intent.query_id,
            )

        response = OrchestratorResponse(
            query_id=intent.query_id,
            results=results,
            unavailable_agents=unavailable,
        )

        # Cache the successful response (Requirement 4.2)
        self.result_cache.put(cache_key, response)

        # Clean up cancellation entry on normal completion (Requirement 8.2)
        if self._current_correlation_id:
            self._cancellation_registry.remove(self._current_correlation_id)

        return response

    # --- Agent Registration (Requirements 6.5, 6.6) ---

    def register_agent(self, agent_config: AgentRegistration) -> None:
        """Register a spoke agent for routing.

        Updates the active agent routing table immediately.

        Args:
            agent_config: The agent registration configuration.
        """
        self._agents[agent_config.agent_id] = agent_config
        logger.info(
            json.dumps({
                "service_name": "orchestrator_hub",
                "operation": "register_agent",
                "agent_id": agent_config.agent_id,
                "endpoint_url": agent_config.endpoint_url,
                "entity_refs": agent_config.entity_refs,
            })
        )
        
        # Notify any registered callback (e.g., NLPTranslator) about registry update
        if _agent_registry_callback:
            try:
                _agent_registry_callback(list(self._agents.keys()))
            except Exception as e:
                logger.warning(
                    json.dumps({
                        "service_name": "orchestrator_hub",
                        "operation": "register_agent",
                        "event": "callback_failed",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    })
                )

    def deregister_agent(self, agent_id: str) -> bool:
        """Remove a spoke agent from the routing table.

        Args:
            agent_id: The identifier of the agent to remove.

        Returns:
            True if the agent was found and removed, False otherwise.
        """
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(
                json.dumps({
                    "service_name": "orchestrator_hub",
                    "operation": "deregister_agent",
                    "agent_id": agent_id,
                })
            )
            # Notify callback about registry update
            if _agent_registry_callback:
                try:
                    _agent_registry_callback(list(self._agents.keys()))
                except Exception as e:
                    logger.warning(
                        json.dumps({
                            "service_name": "orchestrator_hub",
                            "operation": "deregister_agent",
                            "event": "callback_failed",
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                        })
                    )
            return True
        return False

    def get_registered_agents(self) -> list[AgentRegistration]:
        """Return all currently registered agents.

        Returns:
            List of all agent registrations.
        """
        return list(self._agents.values())

    # --- Internal Helpers ---

    def _resolve_agents(self, entity_refs: list[str]) -> list[AgentRegistration]:
        """Resolve which registered agents handle the given entity_refs.

        An agent is resolved if any of its registered entity_refs overlap
        with the intent's entity_refs.

        Args:
            entity_refs: List of canonical ontology concept identifiers.

        Returns:
            List of agent registrations that handle at least one entity_ref.
        """
        entity_set = set(entity_refs)
        resolved: list[AgentRegistration] = []

        for agent in self._agents.values():
            agent_entities = set(agent.entity_refs)
            if agent_entities & entity_set:
                resolved.append(agent)

        return resolved
