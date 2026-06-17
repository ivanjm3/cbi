# Design Document – Ontology Entity Resolution Bugfix

## Overview

This design addresses incorrect ontology entity resolution in the NLP Translator caused by ambiguity between legacy JSON/CSV-backed concepts and Redshift-backed concepts.

### Key Design Goals

- Deterministic entity resolution independent of ontology ordering
- Data-source-aware filtering based on user query hints
- Agent-aware prioritization favoring registered/active agents
- Backward compatibility to prevent regression in existing flows
- Minimal disruption to existing NLP pipeline and scoring logic

---

## Architecture

```
graph TB
    subgraph NLP Translator
        Input[User Query]
        Parser[Keyword Extraction]
        Resolver[_resolve_entities]
        Ranker[Entity Ranking Layer]
        Filter[Data Source Filter]
        AgentCheck[Agent Registry Validation]
        Output[Resolved Entity Refs]
    end

    subgraph Supporting Systems
        Ontology[Ontology Store]
        AgentRegistry[Registered Agents]
    end

    Input --> Parser
    Parser --> Resolver
    Resolver --> Ranker
    Ranker --> Filter
    Filter --> AgentCheck
    AgentCheck --> Output

    Resolver --> Ontology
    AgentCheck --> AgentRegistry
```

---

## Data Flow

1. User submits query  
2. NLP extracts keywords  
3. `_resolve_entities` retrieves all matching ontology concepts  
4. Concepts pass through multi-stage ranking pipeline  
5. Final ranked entities returned to orchestrator  

---

## Component Changes

### 1. `_resolve_entities` Enhancement

```python
def _resolve_entities(keywords):
    matches = {}
    for keyword in keywords:
        candidates = find_all_matching_concepts(keyword)
        scored = score_candidates(candidates, keyword)
        matches[keyword] = scored
    return matches
```

---

### 2. Ranking Rules

Priority order:

1. Explicit Data Source Match  
2. Registered Agent Preference  
3. Default Preference (Redshift over legacy)  

---

### 3. Data Source Detection

```python
def extract_data_source(query):
    sources = ["redshift", "csv", "json"]
    for source in sources:
        if source in query.lower():
            return source
    return None
```

---

### 4. Filtering Layer

```python
def filter_by_data_source(concepts, data_source):
    if not data_source:
        return concepts
    return [c for c in concepts if c.properties.get("data_source") == data_source]
```

---

### 5. Agent Prioritization

```python
def prioritize_registered_agents(concepts, agent_registry):
    return sorted(concepts, key=lambda c: agent_registry.is_registered(c.agent_id), reverse=True)
```

---

## Resolution Algorithm

```python
def resolve_entities(query, keywords):
    data_source = extract_data_source(query)
    resolved = []

    for keyword in keywords:
        candidates = find_all_matching_concepts(keyword)
        candidates = score_candidates(candidates, keyword)
        candidates = filter_by_data_source(candidates, data_source)
        candidates = prioritize_registered_agents(candidates, agent_registry)
        best = max(candidates, key=lambda c: c.finalScore)
        resolved.append(best)

    return resolved
```

---

## Correctness Properties

- Explicit data source must always be respected
- Redshift preferred by default
- Registered agents prioritized
- Deterministic resolution for identical inputs

---

## Error Handling

- No match → NO_ONTOLOGY_MATCH  
- Ambiguous → AMBIGUOUS_INTENT  
- No registered agents → fallback to best score  

---

## Testing Strategy

### Unit Tests
- Entity resolution logic
- Data source filtering
- Ranking correctness

### Integration Tests
- Full query → resolution → routing flow

---

## Benefits

- Removes ontology ordering dependency
- Improves routing accuracy
- Maintains backward compatibility
- Extensible for future sources
