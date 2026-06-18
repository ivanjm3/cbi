#!/usr/bin/env python
"""Test ontology concept matching to debug NLP issues."""

from src.services.ontology_store import OntologyStore

# Initialize ontology store
ontology = OntologyStore()

# Test keywords
test_keywords = ["employees", "remote", "in-office", "workforce"]

print("Testing ontology concept matching...")
print("=" * 60)

for keyword in test_keywords:
    print(f"\nSearching for: '{keyword}'")
    concepts = ontology.search_concepts(keyword)
    if concepts:
        for concept in concepts[:3]:  # Show top 3 matches
            print(f"  ✓ {concept.concept_id}: {concept.label}")
    else:
        print(f"  ✗ No matches found")

# Test the workforce_metrics concept specifically
print("\n" + "=" * 60)
print("Checking workforce_metrics concept details...")
workforce = ontology.lookup_concept("ontology:workforce_metrics")
if workforce:
    print(f"Concept ID: {workforce.concept_id}")
    print(f"Label: {workforce.label}")
    filter_keywords = workforce.properties.get("filter_keywords", [])
    print(f"Filter keywords ({len(filter_keywords)}): {filter_keywords[:10]}")
    
    # Check if our test keywords are in filter_keywords
    print("\nKeyword checks:")
    for kw in ["employees", "remote", "in-office"]:
        is_in = any(kw.lower() == fk.lower() for fk in filter_keywords)
        status = "✓" if is_in else "✗"
        print(f"  {status} '{kw}' in filter_keywords: {is_in}")
else:
    print("✗ workforce_metrics concept not found!")

# Test the NLP translator's entity resolution
print("\n" + "=" * 60)
print("Testing NLP Translator entity resolution...")

from src.services.nlp_translator import NLPTranslator

translator = NLPTranslator(ontology_store=ontology)

# Extract keywords from the query
query = "How many employees are remote vs in-office"
keywords = translator._extract_keywords(query)
print(f"Query: '{query}'")
print(f"Extracted keywords: {keywords}")

# Resolve entities
entity_refs = translator._resolve_entities(query)
print(f"Resolved entity_refs: {entity_refs}")

# Check specificity
is_strong = translator._has_strong_match(keywords, entity_refs)
print(f"Has strong match: {is_strong}")
