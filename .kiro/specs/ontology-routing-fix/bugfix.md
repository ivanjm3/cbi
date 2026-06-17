# Bugfix Requirements Document

## Introduction

The enterprise ontology contains overlapping concepts between legacy JSON/CSV data sources and the Redshift data source. When users ask queries that should route to the Redshift spoke agent (e.g., "show me sales by region"), the NLP translator's `_resolve_entities` method matches old JSON/CSV-backed concepts (like `ontology:sales_revenue` with `agent_id: "spoke-agent-json"`) instead of the Redshift-backed concepts (like `ontology:sales_transactions` with `agent_id: "redshift-spoke-agent"`). This is because:

1. The `_resolve_entities` method takes only the top match per keyword based on iteration order, so whichever concept appears first in the ontology wins when scores are tied.
2. There is no mechanism to filter concepts based on explicit data-source mentions in the user query (e.g., "redshift", "csv").

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user queries about "sales" or "revenue" without specifying a data source THEN the system resolves `ontology:sales_revenue` (agent_id: "spoke-agent-json") instead of `ontology:sales_transactions` (agent_id: "redshift-spoke-agent") because it appears first in the ontology and both get the same match score

1.2 WHEN a user explicitly mentions "{data_source}" in their query (e.g., "show me redshift sales data") THEN the system ignores the data-source hint and still resolves entities without regard to the user's stated preference

1.3 WHEN multiple ontology concepts match the same keyword with equal scores THEN the system picks whichever concept appears first in iteration order rather than preferring concepts backed by registered agents

### Expected Behavior (Correct)

2.1 WHEN a user queries about "sales", "revenue", "customers", or "employee performance" without specifying a data source THEN the system SHALL resolve to Redshift-backed concepts (`ontology:sales_transactions`, `ontology:customer_segments`, `ontology:employee_performance`)

2.2 WHEN a user explicitly mentions {"data_source"} in their query THEN the system SHALL filter resolved concepts to only those with `data_source: "{"data_source"}"` in their properties

2.3 WHEN multiple ontology concepts match the same keyword with equal scores THEN the system SHALL prefer concepts backed by currently registered agents over those with unregistered agent IDs

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user queries about "product catalog", "inventory", or "supplier" and the CSV spoke agent IS registered THEN the system SHALL CONTINUE TO route to the CSV-backed concepts and the CSV spoke agent

3.2 WHEN a user queries about concepts that have only one matching ontology entry (no ambiguity) THEN the system SHALL CONTINUE TO resolve entities and route correctly as before

3.3 WHEN a user query matches no ontology concepts at all THEN the system SHALL CONTINUE TO return a NO_ONTOLOGY_MATCH error

3.4 WHEN a user query is too vague to resolve to a specific domain THEN the system SHALL CONTINUE TO return an AMBIGUOUS_INTENT error

3.5 WHEN the orchestrator receives entity refs that map to registered agents THEN the system SHALL CONTINUE TO dispatch intents to those agents and return results normally

3.6 WHEN the result cache contains a cached response for a query THEN the system SHALL CONTINUE TO return the cached response without re-dispatching
