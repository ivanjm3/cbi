## Implementation Plan: Ontology Entity Resolution Bugfix

### Overview

Fix the NLP Translator's `_resolve_entities` method to correctly route queries to the appropriate data source agent. Add data-source keyword detection, agent-aware prioritization, and deterministic tie-breaking to replace the current first-match logic.

---

### Tasks

- [x] 1. Add data-source detection to NLP Translator
  - [x] 1.1 Create `_detect_data_source(query_text)` method in `src/services/nlp_translator.py` that scans for explicit keywords ("redshift", "csv", "json", "product catalog") and returns the matched data source identifier or None
  - [x] 1.2 Add data-source-to-property mapping: "redshift" → `data_source: "redshift"`, "csv"/"product catalog" → `data_source: "product_catalog"`, "json" → `data_source: "financial_data"`

- [x] 2. Refactor `_resolve_entities` with ranking and filtering
  - [x] 2.1 Modify `_resolve_entities` to collect ALL matching concepts per keyword (not just top-1), then apply filtering and re-ranking before selecting the best
  - [x] 2.2 Add data-source filtering: if `_detect_data_source` returns a source, filter candidates to only concepts with matching `data_source` property; if filtering removes all candidates, fall back to unfiltered set
  - [x] 2.3 Add agent-aware tie-breaking: when multiple candidates have the same base score, prefer concepts whose `agent_id` matches a currently registered agent (requires access to registered agent list)
  - [x] 2.4 Add default Redshift preference: when no explicit data source is detected and scores are tied, boost Redshift-backed concepts over legacy JSON/CSV concepts

- [x] 3. Expose registered agent IDs to NLP Translator
  - [x] 3.1 Add a method or inject registered agent IDs into NLPTranslator so it can check whether an `agent_id` from the ontology corresponds to an active agent
  - [x] 3.2 Ensure the registered agent list updates when agents are registered/deregistered (use reference to orchestrator's agent registry or pass at construction)

- [x] 4. Update ontology concepts for clarity
  - [x] 4.1 Add `data_source` property to all ontology concepts that are missing it (ensure every concept with an `agent_id` also has an explicit `data_source` field)
  - [x] 4.2 Update the shared dimension concepts (`ontology:product_category`, `ontology:region`) to include `values` lists that match all current data sources (Redshift uses more regions/categories than listed)

- [ ]* 5. Write tests for the fix
  - [ ]* 5.1 Unit tests for `_detect_data_source`: verify correct extraction for "redshift", "csv", "json", "product catalog", and no-match cases
  - [ ]* 5.2 Unit tests for refactored `_resolve_entities`: verify Redshift concepts win over JSON/CSV concepts for ambiguous keywords like "sales"; verify explicit data-source mention overrides default preference
  - [ ]* 5.3 Regression tests: verify existing unambiguous queries (product catalog, inventory, supplier) still resolve correctly; verify NO_ONTOLOGY_MATCH and AMBIGUOUS_INTENT errors still raised appropriately
  - [ ]* 5.4 Property-based test: for any query text, resolution is deterministic (same input always produces same entity_refs regardless of ontology concept ordering)

- [x] 6. Integration validation
  - [x] 6.1 End-to-end test: query "show me sales by region" routes to redshift-spoke-agent
  - [x] 6.2 End-to-end test: query "show me redshift employee performance" routes to redshift-spoke-agent
  - [x] 6.3 End-to-end test: query "show me product catalog" routes to spoke-agent-csv (when registered)
  - [x] 6.4 Verify orchestrator dispatch still works correctly with new entity_refs output

---

### Notes

- The fix is scoped to `src/services/nlp_translator.py` (primary), `data/ontology/enterprise_ontology.json` (data fix), and a thin integration point with the agent registry
- No changes to the orchestrator hub dispatch logic or spoke agent implementations
- Backward compatibility: CSV/JSON routing still works if those agents are re-registered
