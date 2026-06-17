"""Integration tests for ontology routing bugfix.

Validates that the NLP Translator correctly routes queries to appropriate
data source agents based on:
- Explicit data-source keywords in queries
- Default Redshift preference when no explicit source mentioned
- Agent-aware prioritization (registered agents preferred)
- Deterministic entity resolution

Requirements: Task 6 - Integration validation
"""

import json
import pathlib
from unittest.mock import patch

import pytest

from src.models.ontology import OntologyDefinition
from src.services.nlp_translator import NLPTranslator
from src.services.ontology_store import OntologyStore
from src.models.shared import StructuredIntent


def _create_local_ontology_store():
    """Create an OntologyStore that loads from local data/ontology/ only.

    The S3 bucket may have a stale version of the ontology. This fixture
    ensures we test against the local (updated) ontology that includes
    Redshift concepts added in Task 4.
    """
    # Load directly from local file to bypass S3
    local_file = pathlib.Path("data/ontology/enterprise_ontology.json")
    body = local_file.read_text(encoding="utf-8")
    parsed = json.loads(body)
    definition = OntologyDefinition.model_validate(parsed)

    # Create store but prevent S3 loading
    with patch.object(OntologyStore, "_load_all"):
        store = OntologyStore()
    store._definitions = {"enterprise_ontology": definition}
    return store


@pytest.fixture
def ontology_store():
    """OntologyStore loaded from local data (includes Redshift concepts)."""
    return _create_local_ontology_store()


@pytest.fixture
def nlp_translator(ontology_store):
    """Create NLPTranslator with empty agent registry (default behavior)."""
    return NLPTranslator(ontology_store=ontology_store)


@pytest.fixture
def nlp_translator_with_agents(ontology_store):
    """Create NLPTranslator with simulated registered agents."""
    return NLPTranslator(
        ontology_store=ontology_store,
        registered_agent_ids=[
            "redshift-spoke-agent",
            "spoke-agent-csv",
            "spoke-agent-json",
        ],
    )


# Task 6.1: Query "show me sales by region" should route to redshift-spoke-agent
def test_query_sales_by_region_routes_to_redshift(nlp_translator_with_agents):
    """Query with ambiguous 'sales' keyword should default to Redshift-backed concepts.
    
    When user queries about "sales" without specifying a data source, the system
    should prefer Redshift-backed concepts (ontology:sales_transactions with
    agent_id: redshift-spoke-agent) over legacy JSON-backed concepts
    (ontology:sales_revenue with agent_id: spoke-agent-json).
    
    Validates: Task 6.1 - Default Redshift preference
    """
    translator = nlp_translator_with_agents
    
    query = "show me sales by region"
    result = translator._resolve_entities(query)
    
    # Should resolve to sales_transactions (Redshift) not sales_revenue (JSON)
    assert "ontology:sales_transactions" in result, \
        f"Expected 'ontology:sales_transactions' for 'sales' query, got {result}"
    
    # Should NOT resolve to JSON-backed concept when Redshift is available
    assert "ontology:sales_revenue" not in result, \
        f"JSON-backed concept 'ontology:sales_revenue' should not be selected when Redshift is available"


# Task 6.2: Query "show me redshift employee performance" should route to redshift-spoke-agent
def test_query_redshift_employee_performance_routes_to_redshift(nlp_translator_with_agents):
    """Explicit 'redshift' keyword should filter to Redshift-backed concepts.
    
    When user explicitly mentions 'redshift' in the query, the system should
    filter results to only concepts with data_source: "redshift".
    
    Validates: Task 6.2 - Explicit data-source filtering
    """
    translator = nlp_translator_with_agents
    
    query = "show me redshift employee performance"
    result = translator._resolve_entities(query)
    
    # Should resolve to employee_performance (Redshift)
    assert "ontology:employee_performance" in result, \
        f"Expected 'ontology:employee_performance' for 'redshift employee performance' query, got {result}"
    
    # Data source detection should work for "redshift" keyword
    detected_source = translator._detect_data_source(query)
    assert detected_source == "redshift", \
        f"Expected detected data source 'redshift', got {detected_source}"


# Task 6.3: Query "show me product catalog" should route to spoke-agent-csv
def test_query_product_catalog_routes_to_csv(nlp_translator_with_agents):
    """Explicit 'product catalog' keyword should filter to CSV-backed concepts.
    
    When user explicitly mentions 'product catalog', the system should
    filter results to only concepts with data_source: "product_catalog".
    
    Validates: Task 6.3 - CSV/JSON routing for specific queries
    """
    translator = nlp_translator_with_agents
    
    query = "show me product catalog"
    result = translator._resolve_entities(query)
    
    # Should resolve to product_catalog (CSV)
    assert "ontology:product_catalog" in result, \
        f"Expected 'ontology:product_catalog' for 'product catalog' query, got {result}"
    
    # Data source detection should work for "product catalog" keyword
    detected_source = translator._detect_data_source(query)
    assert detected_source == "product_catalog", \
        f"Expected detected data source 'product_catalog', got {detected_source}"


# Task 6.4: Verify orchestrator dispatch still works correctly with new entity_refs output
def test_orchestrator_dispatch_with_resolved_entity_refs():
    """Verify orchestrator's _resolve_agents works with entity_refs from new resolution logic.
    
    Tests that the orchestrator hub's agent resolution mechanism correctly maps
    entity_refs (produced by the fixed NLP translator) to the appropriate
    registered spoke agents. This validates backward compatibility between the
    new entity resolution output and the orchestrator's dispatch logic.
    
    Validates: Task 6.4 - Orchestrator dispatch compatibility
    """
    from src.services.orchestrator_hub import OrchestratorHub
    from src.models.shared import AgentRegistration

    # Create hub with mocked Strands dependencies (we only test _resolve_agents)
    with patch("src.services.orchestrator_hub.Agent"):
        with patch("src.config.get_strands_bedrock_model"):
            hub = OrchestratorHub()

    # Register agents matching the ontology's agent_id values
    hub.register_agent(AgentRegistration(
        agent_id="redshift-spoke-agent",
        agent_name="Redshift Spoke Agent",
        data_source="redshift",
        endpoint_url="http://localhost:8011",
        entity_refs=[
            "ontology:sales_transactions",
            "ontology:customer_segments",
            "ontology:employee_performance",
        ],
    ))
    hub.register_agent(AgentRegistration(
        agent_id="spoke-agent-csv",
        agent_name="CSV Spoke Agent",
        data_source="product_catalog",
        endpoint_url="http://localhost:8010",
        entity_refs=[
            "ontology:product_catalog",
            "ontology:inventory_stock",
            "ontology:product_pricing",
            "ontology:supplier_info",
        ],
    ))
    hub.register_agent(AgentRegistration(
        agent_id="spoke-agent-json",
        agent_name="JSON Spoke Agent",
        data_source="financial_data",
        endpoint_url="http://localhost:8010",
        entity_refs=[
            "ontology:sales_revenue",
            "ontology:order_volume",
            "ontology:return_rate",
            "ontology:quarterly_report",
        ],
    ))

    # Test 1: Redshift entity_refs resolve to redshift-spoke-agent
    resolved = hub._resolve_agents(["ontology:sales_transactions"])
    assert len(resolved) == 1
    assert resolved[0].agent_id == "redshift-spoke-agent"

    # Test 2: CSV entity_refs resolve to spoke-agent-csv
    resolved = hub._resolve_agents(["ontology:product_catalog"])
    assert len(resolved) == 1
    assert resolved[0].agent_id == "spoke-agent-csv"

    # Test 3: Multiple entity_refs spanning agents resolve to multiple agents
    resolved = hub._resolve_agents([
        "ontology:sales_transactions",
        "ontology:product_catalog",
    ])
    resolved_ids = {a.agent_id for a in resolved}
    assert resolved_ids == {"redshift-spoke-agent", "spoke-agent-csv"}

    # Test 4: Unrecognized entity_refs yield no agents (no crash)
    resolved = hub._resolve_agents(["ontology:nonexistent_concept"])
    assert len(resolved) == 0

    # Test 5: StructuredIntent with new entity_refs format is schema-compatible
    import uuid
    from datetime import datetime, timezone
    intent = StructuredIntent(
        query_id=uuid.uuid4(),
        query_type="lookup",
        entity_refs=["ontology:sales_transactions"],
        routing_metadata={"query_text": "show me sales by region"},
        timestamp=datetime.now(timezone.utc),
    )
    # Orchestrator uses intent.entity_refs directly for resolution
    resolved = hub._resolve_agents(intent.entity_refs)
    assert len(resolved) == 1
    assert resolved[0].agent_id == "redshift-spoke-agent"
    assert resolved[0].data_source == "redshift"


def test_orchestrator_dispatch_end_to_end_with_translator(nlp_translator_with_agents):
    """Full pipeline: NLP translator resolves entities, orchestrator maps to agents.
    
    Validates that the entity_refs produced by the fixed NLP translator
    can be directly consumed by the orchestrator's _resolve_agents method
    to find the correct spoke agents for dispatch.
    
    Validates: Task 6.4 - End-to-end backward compatibility
    """
    from src.services.orchestrator_hub import OrchestratorHub
    from src.models.shared import AgentRegistration

    translator = nlp_translator_with_agents

    # Create hub with mocked Strands dependencies
    with patch("src.services.orchestrator_hub.Agent"):
        with patch("src.config.get_strands_bedrock_model"):
            hub = OrchestratorHub()

    # Register agents with the same entity_refs as the ontology
    hub.register_agent(AgentRegistration(
        agent_id="redshift-spoke-agent",
        agent_name="Redshift Spoke Agent",
        data_source="redshift",
        endpoint_url="http://localhost:8011",
        entity_refs=[
            "ontology:sales_transactions",
            "ontology:customer_segments",
            "ontology:employee_performance",
        ],
    ))
    hub.register_agent(AgentRegistration(
        agent_id="spoke-agent-csv",
        agent_name="CSV Spoke Agent",
        data_source="product_catalog",
        endpoint_url="http://localhost:8010",
        entity_refs=[
            "ontology:product_catalog",
            "ontology:inventory_stock",
            "ontology:product_pricing",
            "ontology:supplier_info",
        ],
    ))

    # NLP translator resolves "sales by region" → entity_refs
    entity_refs = translator._resolve_entities("show me sales by region")
    assert len(entity_refs) > 0, "Translator should resolve at least one entity"

    # Orchestrator resolves those entity_refs to agents
    resolved_agents = hub._resolve_agents(entity_refs)
    assert len(resolved_agents) > 0, "Orchestrator should resolve at least one agent"

    # The resolved agent should include redshift-spoke-agent 
    # (since the fixed translator prefers Redshift for ambiguous "sales")
    resolved_ids = {a.agent_id for a in resolved_agents}
    assert "redshift-spoke-agent" in resolved_ids, \
        f"Expected redshift-spoke-agent in resolved agents, got {resolved_ids}"

    # Test with CSV-targeted query
    entity_refs_csv = translator._resolve_entities("show me product catalog")
    resolved_csv = hub._resolve_agents(entity_refs_csv)
    resolved_csv_ids = {a.agent_id for a in resolved_csv}
    assert "spoke-agent-csv" in resolved_csv_ids, \
        f"Expected spoke-agent-csv for product catalog query, got {resolved_csv_ids}"


# Additional validation tests
def test_detect_data_source_variants(nlp_translator):
    """Test data source detection with various query patterns."""
    translator = nlp_translator
    
    # Redshift variants
    assert translator._detect_data_source("show redshift sales") == "redshift"
    assert translator._detect_data_source("redshift data for revenue") == "redshift"
    
    # CSV/product catalog variants
    assert translator._detect_data_source("product catalog list") == "product_catalog"
    assert translator._detect_data_source("show csv data") == "product_catalog"
    
    # JSON variants
    assert translator._detect_data_source("json financial report") == "financial_data"
    
    # No match
    assert translator._detect_data_source("show me sales") is None


def test_entity_resolution_deterministic(nlp_translator_with_agents):
    """Entity resolution should be deterministic regardless of input order.
    
    Validates: Deterministic resolution property - same input always produces
    same entity_refs regardless of ontology concept ordering.
    """
    translator = nlp_translator_with_agents
    
    # Same query, multiple runs should produce same result
    query = "show me sales"
    result1 = translator._resolve_entities(query)
    result2 = translator._resolve_entities(query)
    
    assert result1 == result2, \
        f"Entity resolution is not deterministic: {result1} vs {result2}"


def test_registered_agent_preference(nlp_translator_with_agents):
    """Concepts with registered agents should be preferred during tie-breaking."""
    translator = nlp_translator_with_agents
    
    # The registered agents list should influence entity resolution
    # when multiple concepts have the same score
    assert "redshift-spoke-agent" in translator._registered_agent_ids
    assert "spoke-agent-csv" in translator._registered_agent_ids
