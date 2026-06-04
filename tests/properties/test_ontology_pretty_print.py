"""Property tests for ontology pretty-print round-trip.

Property 16: Ontology Pretty-Print Round-Trip
- For any valid OntologyDefinition, pretty-print then parse produces
  same concepts, relationships, and properties regardless of ordering.

Validates: Requirements 12.4, 12.5
"""

import tempfile

from hypothesis import given, HealthCheck, settings
from hypothesis import strategies as st

from src.models.ontology import OntologyConcept, OntologyDefinition, OntologyRelationship
from src.services.ontology_store import OntologyStore


# --- Strategies ---

# Ontology identifiers: simple alphanumeric + underscores prefixed with "ontology:"
concept_id_strategy = st.from_regex(r"ontology:[a-z][a-z0-9_]{0,29}", fullmatch=True)

# Human-readable labels
label_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        whitelist_characters="_-",
    ),
    min_size=1,
    max_size=50,
)

# Property values: simple JSON-compatible types
property_value_strategy = st.one_of(
    st.booleans(),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.text(min_size=0, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_ "),
)

# Property dictionaries: small dicts with string keys and simple values
properties_strategy = st.dictionaries(
    keys=st.from_regex(r"[a-z][a-z0-9_]{0,14}", fullmatch=True),
    values=property_value_strategy,
    min_size=0,
    max_size=5,
)

# Relationship types
relation_type_strategy = st.sampled_from([
    "contributes_to",
    "is_part_of",
    "depends_on",
    "related_to",
    "has_child",
    "aggregates",
])


def ontology_relationship_strategy(concept_ids: list[str]) -> st.SearchStrategy:
    """Generate relationships that reference existing concept IDs."""
    if len(concept_ids) < 2:
        return st.just([])

    return st.lists(
        st.builds(
            OntologyRelationship,
            source_id=st.sampled_from(concept_ids),
            target_id=st.sampled_from(concept_ids),
            relation_type=relation_type_strategy,
            properties=properties_strategy,
        ),
        min_size=0,
        max_size=min(len(concept_ids) * 2, 10),
    )


# Generate unique concept IDs first, then build concepts from them
@st.composite
def ontology_definition_strategy(draw: st.DrawFn) -> OntologyDefinition:
    """Generate a valid OntologyDefinition with unique concept IDs."""
    # Generate 1-8 unique concept IDs
    num_concepts = draw(st.integers(min_value=1, max_value=8))
    concept_ids = draw(
        st.lists(
            concept_id_strategy,
            min_size=num_concepts,
            max_size=num_concepts,
            unique=True,
        )
    )

    # Build concepts with those IDs (no embedded relationships for simplicity)
    concepts = []
    for cid in concept_ids:
        concept = draw(
            st.builds(
                OntologyConcept,
                concept_id=st.just(cid),
                label=label_strategy,
                properties=properties_strategy,
                relationships=st.just([]),
            )
        )
        concepts.append(concept)

    # Generate top-level relationships referencing existing concept IDs
    relationships = draw(ontology_relationship_strategy(concept_ids))

    # Generate metadata
    metadata = draw(
        st.fixed_dictionaries(
            {"name": st.from_regex(r"[a-z][a-z0-9_]{2,19}", fullmatch=True)},
            optional={
                "version": st.from_regex(r"[0-9]\.[0-9]", fullmatch=True),
                "description": st.text(min_size=0, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz "),
            },
        )
    )

    return OntologyDefinition(
        concepts=concepts,
        relationships=relationships,
        metadata=metadata,
    )


@st.composite
def ontology_definition_with_embedded_rels_strategy(draw: st.DrawFn) -> OntologyDefinition:
    """Generate an OntologyDefinition where concepts have embedded relationships."""
    num_concepts = draw(st.integers(min_value=2, max_value=6))
    concept_ids = draw(
        st.lists(
            concept_id_strategy,
            min_size=num_concepts,
            max_size=num_concepts,
            unique=True,
        )
    )

    concepts = []
    for cid in concept_ids:
        # Each concept can have 0-2 embedded relationships to other concepts
        embedded_rels = draw(
            st.lists(
                st.builds(
                    OntologyRelationship,
                    source_id=st.just(cid),
                    target_id=st.sampled_from(concept_ids),
                    relation_type=relation_type_strategy,
                    properties=properties_strategy,
                ),
                min_size=0,
                max_size=2,
            )
        )
        concept = draw(
            st.builds(
                OntologyConcept,
                concept_id=st.just(cid),
                label=label_strategy,
                properties=properties_strategy,
                relationships=st.just(embedded_rels),
            )
        )
        concepts.append(concept)

    # Also generate some top-level relationships
    relationships = draw(ontology_relationship_strategy(concept_ids))

    metadata = draw(
        st.fixed_dictionaries(
            {"name": st.from_regex(r"[a-z][a-z0-9_]{2,19}", fullmatch=True)},
        )
    )

    return OntologyDefinition(
        concepts=concepts,
        relationships=relationships,
        metadata=metadata,
    )


# --- Helper Functions ---


def concepts_equivalent(original: list[OntologyConcept], restored: list[OntologyConcept]) -> bool:
    """Check that two lists of concepts are equivalent regardless of order."""
    if len(original) != len(restored):
        return False

    original_by_id = {c.concept_id: c for c in original}
    restored_by_id = {c.concept_id: c for c in restored}

    if set(original_by_id.keys()) != set(restored_by_id.keys()):
        return False

    for cid in original_by_id:
        orig = original_by_id[cid]
        rest = restored_by_id[cid]

        if orig.label != rest.label:
            return False
        if orig.properties != rest.properties:
            return False

        # Compare embedded relationships as sets of tuples
        orig_rels = {
            (r.source_id, r.target_id, r.relation_type, tuple(sorted(r.properties.items())))
            for r in orig.relationships
        }
        rest_rels = {
            (r.source_id, r.target_id, r.relation_type, tuple(sorted(r.properties.items())))
            for r in rest.relationships
        }
        if orig_rels != rest_rels:
            return False

    return True


def relationships_equivalent(
    original: list[OntologyRelationship], restored: list[OntologyRelationship]
) -> bool:
    """Check that two lists of relationships are equivalent regardless of order."""
    if len(original) != len(restored):
        return False

    orig_set = {
        (r.source_id, r.target_id, r.relation_type, tuple(sorted(r.properties.items())))
        for r in original
    }
    rest_set = {
        (r.source_id, r.target_id, r.relation_type, tuple(sorted(r.properties.items())))
        for r in restored
    }
    return orig_set == rest_set


# --- Property Tests ---


class TestOntologyPrettyPrintRoundTrip:
    """Property 16: Ontology Pretty-Print Round-Trip.

    For any valid OntologyDefinition, pretty-print then parse produces
    the same concepts, relationships, and properties.
    """

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_preserves_concept_count(self, definition: OntologyDefinition) -> None:
        """Pretty-print → deserialize preserves the number of concepts."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)
        assert len(restored.concepts) == len(definition.concepts)

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_preserves_relationship_count(self, definition: OntologyDefinition) -> None:
        """Pretty-print → deserialize preserves the number of relationships."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)
        assert len(restored.relationships) == len(definition.relationships)

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_preserves_concept_ids(self, definition: OntologyDefinition) -> None:
        """Pretty-print → deserialize preserves all concept identifiers."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)

        original_ids = {c.concept_id for c in definition.concepts}
        restored_ids = {c.concept_id for c in restored.concepts}
        assert original_ids == restored_ids

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_preserves_concept_labels(self, definition: OntologyDefinition) -> None:
        """Pretty-print → deserialize preserves all concept labels."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)

        original_labels = {c.concept_id: c.label for c in definition.concepts}
        restored_labels = {c.concept_id: c.label for c in restored.concepts}
        assert original_labels == restored_labels

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_preserves_concept_properties(self, definition: OntologyDefinition) -> None:
        """Pretty-print → deserialize preserves all concept properties."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)

        original_props = {c.concept_id: c.properties for c in definition.concepts}
        restored_props = {c.concept_id: c.properties for c in restored.concepts}
        assert original_props == restored_props

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_preserves_relationships(self, definition: OntologyDefinition) -> None:
        """Pretty-print → deserialize preserves all top-level relationships."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)

        assert relationships_equivalent(definition.relationships, restored.relationships)

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_preserves_metadata(self, definition: OntologyDefinition) -> None:
        """Pretty-print → deserialize preserves metadata."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)

        assert restored.metadata == definition.metadata

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_full_equivalence(self, definition: OntologyDefinition) -> None:
        """Pretty-print → deserialize produces a fully equivalent definition."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)

        assert concepts_equivalent(definition.concepts, restored.concepts)
        assert relationships_equivalent(definition.relationships, restored.relationships)
        assert restored.metadata == definition.metadata

    @given(definition=ontology_definition_with_embedded_rels_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_preserves_embedded_relationships(
        self, definition: OntologyDefinition
    ) -> None:
        """Pretty-print → deserialize preserves relationships embedded in concepts."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)
        restored = store.deserialize(pretty)

        assert concepts_equivalent(definition.concepts, restored.concepts)

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_output_is_human_readable(self, definition: OntologyDefinition) -> None:
        """Pretty-print output is indented and multi-line (human-readable)."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty = store.pretty_print(definition)

        # Must be multi-line (indented format)
        assert "\n" in pretty
        # Must contain indentation (4 spaces as configured)
        assert "    " in pretty
        # Must be valid JSON (parseable without error)
        restored = store.deserialize(pretty)
        assert restored is not None

    @given(definition=ontology_definition_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_pretty_print_idempotent(self, definition: OntologyDefinition) -> None:
        """Pretty-printing twice produces the same output."""
        store = OntologyStore(tempfile.mkdtemp())
        pretty1 = store.pretty_print(definition)
        restored = store.deserialize(pretty1)
        pretty2 = store.pretty_print(restored)

        assert pretty1 == pretty2
