"""Unit tests for the flat-file OntologyStore."""

import json
import tempfile
from pathlib import Path

import pytest

from src.models.ontology import OntologyConcept, OntologyDefinition, OntologyRelationship
from src.services.ontology_store import OntologyStore, OntologyStoreError


@pytest.fixture
def tmp_ontology_dir(tmp_path):
    """Create a temporary directory for ontology files."""
    return tmp_path / "ontology"


@pytest.fixture
def sample_definition() -> OntologyDefinition:
    """Create a minimal sample ontology definition."""
    return OntologyDefinition(
        concepts=[
            OntologyConcept(
                concept_id="test:revenue",
                label="Revenue",
                properties={"domain": "finance", "aggregatable": True},
            ),
            OntologyConcept(
                concept_id="test:products",
                label="Product Catalog",
                properties={"domain": "inventory"},
            ),
        ],
        relationships=[
            OntologyRelationship(
                source_id="test:revenue",
                target_id="test:products",
                relation_type="related_to",
                properties={"join_key": "category"},
            ),
        ],
        metadata={"name": "test_ontology", "version": "1.0"},
    )


@pytest.fixture
def store_with_data(tmp_ontology_dir, sample_definition):
    """Create a store with a pre-loaded definition."""
    store = OntologyStore(tmp_ontology_dir)
    store.create_definition(sample_definition)
    return store


# --- Lookup tests ---


class TestLookupConcept:
    def test_finds_existing_concept(self, store_with_data):
        result = store_with_data.lookup_concept("test:revenue")
        assert result is not None
        assert result.concept_id == "test:revenue"
        assert result.label == "Revenue"

    def test_returns_none_for_missing_concept(self, store_with_data):
        result = store_with_data.lookup_concept("test:nonexistent")
        assert result is None


# --- Traversal tests ---


class TestTraverseHierarchy:
    def test_traverses_children(self, store_with_data):
        children = store_with_data.traverse_hierarchy("test:revenue", direction="children")
        assert len(children) == 1
        assert children[0].concept_id == "test:products"

    def test_traverses_parents(self, store_with_data):
        parents = store_with_data.traverse_hierarchy("test:products", direction="parents")
        assert len(parents) == 1
        assert parents[0].concept_id == "test:revenue"

    def test_returns_empty_for_no_relations(self, store_with_data):
        children = store_with_data.traverse_hierarchy("test:products", direction="children")
        assert children == []


# --- Search tests ---


class TestSearchConcepts:
    def test_finds_by_keyword(self, store_with_data):
        results = store_with_data.search_concepts("revenue")
        assert len(results) == 1
        assert results[0].concept_id == "test:revenue"

    def test_case_insensitive_search(self, store_with_data):
        results = store_with_data.search_concepts("PRODUCT")
        assert len(results) == 1
        assert results[0].concept_id == "test:products"

    def test_returns_empty_for_no_match(self, store_with_data):
        results = store_with_data.search_concepts("zzz_nonexistent")
        assert results == []


# --- CRUD tests ---


class TestCreateDefinition:
    def test_creates_and_persists(self, tmp_ontology_dir, sample_definition):
        store = OntologyStore(tmp_ontology_dir)
        store.create_definition(sample_definition)

        # Verify file exists
        file_path = tmp_ontology_dir / "test_ontology.json"
        assert file_path.exists()

        # Verify can be found via lookup
        assert store.lookup_concept("test:revenue") is not None

    def test_rejects_duplicate_name(self, store_with_data, sample_definition):
        with pytest.raises(OntologyStoreError) as exc_info:
            store_with_data.create_definition(sample_definition)
        assert exc_info.value.error_type == "DUPLICATE_IDENTIFIER"

    def test_rejects_missing_name(self, tmp_ontology_dir):
        store = OntologyStore(tmp_ontology_dir)
        definition = OntologyDefinition(metadata={})
        with pytest.raises(OntologyStoreError) as exc_info:
            store.create_definition(definition)
        assert exc_info.value.error_type == "VALIDATION_ERROR"

    def test_rejects_duplicate_concept_ids(self, tmp_ontology_dir):
        store = OntologyStore(tmp_ontology_dir)
        definition = OntologyDefinition(
            concepts=[
                OntologyConcept(concept_id="dup:a", label="A"),
                OntologyConcept(concept_id="dup:a", label="A duplicate"),
            ],
            metadata={"name": "dup_test"},
        )
        with pytest.raises(OntologyStoreError) as exc_info:
            store.create_definition(definition)
        assert exc_info.value.error_type == "DUPLICATE_IDENTIFIER"


class TestUpdateDefinition:
    def test_updates_existing(self, store_with_data):
        updated = OntologyDefinition(
            concepts=[
                OntologyConcept(concept_id="test:revenue", label="Updated Revenue"),
            ],
            relationships=[],
            metadata={"name": "test_ontology", "version": "2.0"},
        )
        store_with_data.update_definition(updated)
        result = store_with_data.lookup_concept("test:revenue")
        assert result.label == "Updated Revenue"

    def test_rejects_nonexistent(self, tmp_ontology_dir):
        store = OntologyStore(tmp_ontology_dir)
        definition = OntologyDefinition(metadata={"name": "nope"})
        with pytest.raises(OntologyStoreError) as exc_info:
            store.update_definition(definition)
        assert exc_info.value.error_type == "NOT_FOUND"


class TestDeleteDefinition:
    def test_deletes_existing(self, store_with_data, tmp_ontology_dir):
        store_with_data.delete_definition("test_ontology")
        assert store_with_data.lookup_concept("test:revenue") is None
        assert not (tmp_ontology_dir / "test_ontology.json").exists()

    def test_rejects_nonexistent(self, tmp_ontology_dir):
        store = OntologyStore(tmp_ontology_dir)
        with pytest.raises(OntologyStoreError) as exc_info:
            store.delete_definition("nope")
        assert exc_info.value.error_type == "NOT_FOUND"


# --- Serialization tests ---


class TestSerialization:
    def test_round_trip(self, sample_definition):
        store = OntologyStore(tempfile.mkdtemp())
        serialized = store.serialize(sample_definition)
        deserialized = store.deserialize(serialized)

        assert len(deserialized.concepts) == len(sample_definition.concepts)
        assert len(deserialized.relationships) == len(sample_definition.relationships)
        assert deserialized.metadata == sample_definition.metadata

        # Verify concept content preserved
        original_ids = {c.concept_id for c in sample_definition.concepts}
        restored_ids = {c.concept_id for c in deserialized.concepts}
        assert original_ids == restored_ids

    def test_deserialize_rejects_malformed_json(self, tmp_ontology_dir):
        store = OntologyStore(tmp_ontology_dir)
        with pytest.raises(OntologyStoreError) as exc_info:
            store.deserialize("{invalid json")
        assert exc_info.value.error_type == "PARSE_ERROR"

    def test_deserialize_rejects_invalid_schema(self, tmp_ontology_dir):
        store = OntologyStore(tmp_ontology_dir)
        # Valid JSON but wrong structure for a concept
        bad_data = json.dumps({"concepts": [{"wrong_field": "bad"}]})
        with pytest.raises(OntologyStoreError) as exc_info:
            store.deserialize(bad_data)
        assert exc_info.value.error_type == "SCHEMA_VALIDATION_ERROR"


class TestPrettyPrint:
    def test_pretty_print_round_trip(self, sample_definition):
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(sample_definition)
        restored = store.deserialize(pretty)

        assert len(restored.concepts) == len(sample_definition.concepts)
        assert len(restored.relationships) == len(sample_definition.relationships)

    def test_pretty_print_is_readable(self, sample_definition):
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(sample_definition)
        # Should be indented (multi-line)
        assert pretty.count("\n") > 5
        # Should contain concept labels
        assert "Revenue" in pretty


# --- Load from real data test ---


class TestLoadRealOntology:
    def test_loads_enterprise_ontology(self):
        """Verify the actual enterprise_ontology.json loads correctly."""
        store = OntologyStore("data/ontology")
        definitions = store.get_all_definitions()
        assert "enterprise_ontology" in definitions

        # Check key concepts exist
        revenue = store.lookup_concept("ontology:sales_revenue")
        assert revenue is not None
        assert revenue.label == "Sales Revenue"

        catalog = store.lookup_concept("ontology:product_catalog")
        assert catalog is not None
        assert catalog.label == "Product Catalog"

        # Check shared dimension
        category = store.lookup_concept("ontology:product_category")
        assert category is not None
        assert "Electronics" in category.properties["values"]

    def test_search_finds_concepts_across_domains(self):
        """Search finds concepts from both financial and inventory domains."""
        store = OntologyStore("data/ontology")
        results = store.search_concepts("product")
        labels = [c.label for c in results]
        assert "Product Catalog" in labels
        assert "Product Category" in labels
        assert "Product Pricing" in labels

    def test_traverse_shared_dimension(self):
        """Concepts from both agents connect through shared category dimension."""
        store = OntologyStore("data/ontology")
        # Both revenue and catalog are grouped_by product_category
        parents = store.traverse_hierarchy("ontology:product_category", direction="parents")
        parent_ids = [c.concept_id for c in parents]
        assert "ontology:sales_revenue" in parent_ids
        assert "ontology:product_catalog" in parent_ids
