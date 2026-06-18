"""Ontology MCP Server — Exposes domain ontology as MCP tools and resources.

Tools:
  - get_ontology_concepts: Retrieve all domain concepts with metadata
  - search_ontology: Map natural-language terms to ontology concepts
  - map_term_to_column: Bridge natural language to actual column names across data sources

Resources:
  - ontology://concepts — full ontology concept graph as read-only context

Runs via stdio transport for local MCP client integration.
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from src.config import S3_BUCKET, S3_ONTOLOGY_PREFIX, get_s3_client

logger = logging.getLogger(__name__)

mcp = FastMCP(name="Ontology Server")

# Local fallback path for the enterprise ontology
_LOCAL_ONTOLOGY_PATH = Path("data/ontology/enterprise_ontology.json")


# ---------------------------------------------------------------------------
# Internal ontology loading
# ---------------------------------------------------------------------------


def _load_ontology() -> dict[str, Any]:
    """Load the enterprise ontology from S3 or local fallback.

    Tries S3 first; falls back to the local data/ontology/ directory
    for development environments without AWS credentials.
    """
    try:
        s3 = get_s3_client()
        # Try to load the main enterprise ontology from S3
        response = s3.get_object(
            Bucket=S3_BUCKET,
            Key=f"{S3_ONTOLOGY_PREFIX}enterprise_ontology.json",
        )
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)
    except Exception:
        # Fallback to local file
        if _LOCAL_ONTOLOGY_PATH.exists():
            return json.loads(_LOCAL_ONTOLOGY_PATH.read_text(encoding="utf-8"))
        return {"concepts": [], "relationships": [], "metadata": {}}


def _get_concepts() -> list[dict[str, Any]]:
    """Get all concepts from the ontology."""
    data = _load_ontology()
    return data.get("concepts", [])


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
def get_ontology_concepts(domain: str = "") -> list[dict[str, Any]]:
    """Retrieve all domain concepts from the enterprise ontology.

    Returns concept metadata including labels, domains, data sources,
    agent mappings, and column definitions. Optionally filter by domain.

    Args:
        domain: Optional domain filter (e.g. 'finance', 'inventory', 'hr').
                If empty, returns all concepts.

    Returns:
        List of concept objects with full metadata.
    """
    concepts = _get_concepts()

    if domain:
        domain_lower = domain.lower()
        concepts = [
            c for c in concepts
            if c.get("properties", {}).get("domain", "").lower() == domain_lower
        ]

    # Return a summarized view with key metadata
    results = []
    for concept in concepts:
        props = concept.get("properties", {})
        results.append({
            "concept_id": concept.get("concept_id"),
            "label": concept.get("label"),
            "domain": props.get("domain"),
            "description": props.get("description"),
            "data_source": props.get("data_source"),
            "agent_id": props.get("agent_id"),
            "table_name": props.get("table_name"),
            "columns": list(props.get("columns", {}).keys()),
            "filter_keywords": props.get("filter_keywords", []),
            "relationships": [
                {
                    "target": r.get("target_id"),
                    "type": r.get("relation_type"),
                }
                for r in concept.get("relationships", [])
            ],
        })

    return results


@mcp.tool
def search_ontology(query: str) -> list[dict[str, Any]]:
    """Search the ontology to map natural-language terms to data concepts.

    Performs keyword matching against concept labels, descriptions,
    filter_keywords, and column names to find relevant ontology entries.

    Args:
        query: Natural language search term (e.g. 'revenue', 'employee count',
               'product pricing').

    Returns:
        List of matching concepts ranked by relevance score.
    """
    concepts = _get_concepts()
    query_lower = query.lower()
    query_words = set(query_lower.split())

    scored_results: list[tuple[float, dict[str, Any]]] = []

    for concept in concepts:
        score = 0.0
        props = concept.get("properties", {})

        # Match against label
        label = concept.get("label", "").lower()
        if query_lower in label:
            score += 10.0
        elif any(w in label for w in query_words):
            score += 5.0

        # Match against description
        description = props.get("description", "").lower()
        if query_lower in description:
            score += 6.0
        else:
            matching_words = sum(1 for w in query_words if w in description)
            score += matching_words * 2.0

        # Match against filter_keywords
        keywords = [k.lower() for k in props.get("filter_keywords", [])]
        for kw in keywords:
            if query_lower in kw or kw in query_lower:
                score += 8.0
                break
            if any(w in kw or kw in w for w in query_words):
                score += 3.0

        # Match against column names
        columns = props.get("columns", {})
        for col_name in columns:
            col_lower = col_name.lower().replace("_", " ")
            if query_lower in col_lower or col_lower in query_lower:
                score += 7.0
                break
            if any(w in col_lower for w in query_words):
                score += 2.0

        # Match against domain
        domain = props.get("domain", "").lower()
        if query_lower in domain or domain in query_lower:
            score += 3.0

        if score > 0:
            scored_results.append((score, {
                "concept_id": concept.get("concept_id"),
                "label": concept.get("label"),
                "domain": props.get("domain"),
                "description": props.get("description"),
                "data_source": props.get("data_source"),
                "agent_id": props.get("agent_id"),
                "table_name": props.get("table_name"),
                "relevance_score": round(score, 2),
                "matching_keywords": [
                    k for k in props.get("filter_keywords", [])
                    if any(w in k.lower() for w in query_words)
                ],
            }))

    # Sort by relevance score descending
    scored_results.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in scored_results[:10]]


@mcp.tool
def map_term_to_column(term: str) -> list[dict[str, Any]]:
    """Map a natural-language term to actual column names across data sources.

    Bridges business language (e.g. 'revenue', 'headcount') to the specific
    column names in S3 datasets and Redshift tables where that data lives.

    Args:
        term: A business term or natural language phrase (e.g. 'revenue',
              'employee count', 'order value').

    Returns:
        List of column mappings with concept, table, column_name, data_type,
        and the data source (S3 or Redshift).
    """
    concepts = _get_concepts()
    term_lower = term.lower().replace("_", " ")
    term_words = set(term_lower.split())

    mappings: list[dict[str, Any]] = []

    for concept in concepts:
        props = concept.get("properties", {})
        columns = props.get("columns", {})
        table_name = props.get("table_name", "")
        data_source = props.get("data_source", "")
        agent_id = props.get("agent_id", "")

        # Determine storage backend
        if "redshift" in agent_id.lower():
            backend = "redshift"
        elif "json" in agent_id.lower():
            backend = "s3_json"
        elif "csv" in agent_id.lower():
            backend = "s3_csv"
        else:
            backend = "unknown"

        for col_name, col_meta in columns.items():
            col_lower = col_name.lower().replace("_", " ")
            col_desc = col_meta.get("description", "").lower() if isinstance(col_meta, dict) else ""

            # Score this column against the term
            match_score = 0.0
            if term_lower == col_lower:
                match_score = 10.0
            elif term_lower in col_lower or col_lower in term_lower:
                match_score = 8.0
            elif any(w in col_lower for w in term_words):
                match_score = 5.0
            elif term_lower in col_desc:
                match_score = 6.0
            elif any(w in col_desc for w in term_words):
                match_score = 3.0

            if match_score > 0:
                col_type = col_meta.get("type", "unknown") if isinstance(col_meta, dict) else "unknown"
                sql_type = col_meta.get("sql_type", "") if isinstance(col_meta, dict) else ""
                mappings.append({
                    "term": term,
                    "concept_id": concept.get("concept_id"),
                    "concept_label": concept.get("label"),
                    "table_name": table_name,
                    "column_name": col_name,
                    "column_type": col_type,
                    "sql_type": sql_type,
                    "backend": backend,
                    "data_source": data_source,
                    "match_score": round(match_score, 2),
                    "column_description": col_meta.get("description", "") if isinstance(col_meta, dict) else "",
                })

    # Sort by match score descending, deduplicate by column_name + table_name
    mappings.sort(key=lambda x: x["match_score"], reverse=True)

    # Deduplicate: keep highest scoring entry per (table_name, column_name)
    seen: set[tuple[str, str]] = set()
    unique_mappings: list[dict[str, Any]] = []
    for m in mappings:
        key = (m["table_name"], m["column_name"])
        if key not in seen:
            seen.add(key)
            unique_mappings.append(m)

    return unique_mappings[:15]


# ---------------------------------------------------------------------------
# Resources — Injected as read-only context before tool calls
# ---------------------------------------------------------------------------


@mcp.resource("ontology://concepts")
def ontology_concepts_resource() -> dict[str, Any]:
    """Full enterprise ontology as a read-only resource.

    Provides the complete concept graph including relationships, column
    definitions, and domain metadata. Injected as context before the LLM
    decides which tools to call.
    URI: ontology://concepts
    """
    data = _load_ontology()
    concepts = data.get("concepts", [])
    relationships = data.get("relationships", [])
    metadata = data.get("metadata", {})

    return {
        "metadata": metadata,
        "concept_count": len(concepts),
        "relationship_count": len(relationships),
        "domains": list(set(
            c.get("properties", {}).get("domain", "unknown")
            for c in concepts
        )),
        "concepts": [
            {
                "concept_id": c.get("concept_id"),
                "label": c.get("label"),
                "domain": c.get("properties", {}).get("domain"),
                "table_name": c.get("properties", {}).get("table_name"),
                "agent_id": c.get("properties", {}).get("agent_id"),
                "columns": list(c.get("properties", {}).get("columns", {}).keys()),
            }
            for c in concepts
        ],
        "relationships": relationships,
    }


if __name__ == "__main__":
    from src.config import MCP_ONTOLOGY_PORT
    mcp.run(transport="streamable-http", host="0.0.0.0", port=MCP_ONTOLOGY_PORT, path="/mcp")
