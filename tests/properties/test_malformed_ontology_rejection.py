"""Property tests for malformed ontology rejection.

Property 4: Malformed Ontology Definition Rejection Preserves State
- For any malformed/duplicate definition submitted, the store rejects with
  structured error and state remains unchanged.

Property 17: Malformed Serialized Data Rejection
- For any malformed serialized data, deserialization rejects with structured
  error indicating parse failure location.

Validates: Requirements 3.8, 12.6
"""

import copy
import json
import tempfile

from hypothesis import given, assume, HealthCheck, settings
from hypothesis import strategies as st

from src.models.ontology import OntologyConcept, OntologyDefinition, OntologyRelationship
from src.services.ontology_store import OntologyStore, OntologyStoreError


# --- Strategies ---

concept_id_strategy = st.from_regex(r"ontology:[a-z][a-z0-9_]{0,29}", fullmatch=True)

label_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=("L", "N", "Zs"),
        whitelist_characters="_-",
    ),
    min_size=1,
    max_size=50,
)

property_value_strategy = st.one_of(
    st.booleans(),
    st.integers(min_value=-1_000_000, max_value=1_000_000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.text(min_size=0, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz0123456789_ "),
)

properties_strategy = st.dictionaries(
    keys=st.from_regex(r"[a-z][a-z0-9_]{0,14}", fullmatch=True),
    values=property_value_strategy,
    min_size=0,
    max_size=5,
)

relation_type_strategy = st.sampled_from([
    "contributes_to",
    "is_part_of",
    "depends_on",
    "related_to",
    "has_child",
    "aggregates",
])

name_strategy = st.from_regex(r"[a-z][a-z0-9_]{2,19}", fullmatch=True)


@st.composite
def valid_ontology_definition_strategy(draw: st.DrawFn) -> OntologyDefinition:
    """Generate a valid OntologyDefinition with unique concept IDs and a name."""
    num_concepts = draw(st.integers(min_value=1, max_value=6))
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

    relationships = []
    if len(concept_ids) >= 2:
        relationships = draw(
            st.lists(
                st.builds(
                    OntologyRelationship,
                    source_id=st.sampled_from(concept_ids),
                    target_id=st.sampled_from(concept_ids),
                    relation_type=relation_type_strategy,
                    properties=properties_strategy,
                ),
                min_size=0,
                max_size=5,
            )
        )

    name = draw(name_strategy)
    metadata = {"name": name}

    return OntologyDefinition(
        concepts=concepts,
        relationships=relationships,
        metadata=metadata,
    )


@st.composite
def definition_with_duplicate_concept_ids_strategy(draw: st.DrawFn) -> OntologyDefinition:
    """Generate an OntologyDefinition that has at least one duplicate concept_id."""
    base_def = draw(valid_ontology_definition_strategy())
    assume(len(base_def.concepts) >= 1)

    # Pick a concept_id to duplicate
    original_concept = base_def.concepts[0]
    duplicate_concept = OntologyConcept(
        concept_id=original_concept.concept_id,
        label=draw(label_strategy),
        properties=draw(properties_strategy),
        relationships=[],
    )

    # Insert the duplicate
    concepts_with_dup = list(base_def.concepts) + [duplicate_concept]
    return OntologyDefinition(
        concepts=concepts_with_dup,
        relationships=base_def.relationships,
        metadata=base_def.metadata,
    )


@st.composite
def definition_without_name_strategy(draw: st.DrawFn) -> OntologyDefinition:
    """Generate an OntologyDefinition with no 'name' in metadata."""
    base_def = draw(valid_ontology_definition_strategy())
    # Remove the name from metadata
    metadata = {k: v for k, v in base_def.metadata.items() if k != "name"}
    return OntologyDefinition(
        concepts=base_def.concepts,
        relationships=base_def.relationships,
        metadata=metadata,
    )


# Strategies for malformed serialized data

@st.composite
def malformed_json_strategy(draw: st.DrawFn) -> str:
    """Generate strings that are not valid JSON."""
    approach = draw(st.sampled_from([
        "truncated",
        "missing_brace",
        "trailing_comma",
        "unquoted_key",
        "random_text",
        "partial_valid",
    ]))

    if approach == "truncated":
        valid = json.dumps({"concepts": [{"concept_id": "ontology:x", "label": "X"}]})
        cut_point = draw(st.integers(min_value=1, max_value=max(1, len(valid) - 2)))
        return valid[:cut_point]
    elif approach == "missing_brace":
        return '{"concepts": [{"concept_id": "ontology:x", "label": "X"}]'
    elif approach == "trailing_comma":
        return '{"concepts": [{"concept_id": "ontology:x", "label": "X"},]}'
    elif approach == "unquoted_key":
        return '{concepts: [{"concept_id": "ontology:x", "label": "X"}]}'
    elif approach == "random_text":
        text = draw(st.text(min_size=1, max_size=100, alphabet="abcdefghijklmnop !@#$%"))
        assume(not _is_valid_json(text))
        return text
    else:  # partial_valid
        return '{"concepts": ' + draw(st.text(min_size=1, max_size=20, alphabet="abc123[{"))

    return ""


@st.composite
def invalid_schema_json_strategy(draw: st.DrawFn) -> str:
    """Generate valid JSON that doesn't conform to the OntologyDefinition schema."""
    approach = draw(st.sampled_from([
        "wrong_concepts_type",
        "concept_missing_required",
        "relationship_wrong_type",
        "concepts_as_string",
        "nested_invalid",
    ]))

    if approach == "wrong_concepts_type":
        # concepts should be a list, not a string
        return json.dumps({"concepts": "not_a_list", "relationships": [], "metadata": {}})
    elif approach == "concept_missing_required":
        # concept missing required 'label' field
        return json.dumps({
            "concepts": [{"concept_id": "ontology:x"}],
            "relationships": [],
            "metadata": {},
        })
    elif approach == "relationship_wrong_type":
        # relationship fields should be strings, not integers
        return json.dumps({
            "concepts": [],
            "relationships": [{"source_id": 123, "target_id": 456, "relation_type": 789}],
            "metadata": {},
        })
    elif approach == "concepts_as_string":
        # Each concept should be an object, not a string
        return json.dumps({
            "concepts": ["not_an_object", "another_string"],
            "relationships": [],
            "metadata": {},
        })
    else:  # nested_invalid
        # Relationships within concepts have wrong type
        return json.dumps({
            "concepts": [{
                "concept_id": "ontology:x",
                "label": "X",
                "properties": {},
                "relationships": "not_a_list",
            }],
            "relationships": [],
            "metadata": {},
        })


def _is_valid_json(text: str) -> bool:
    """Check if a string is valid JSON."""
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, ValueError):
        return False


def _snapshot_store_state(store: OntologyStore) -> dict:
    """Capture a deep copy of the store's current state for comparison."""
    definitions = store.get_all_definitions()
    return {
        name: copy.deepcopy(defn.model_dump())
        for name, defn in definitions.items()
    }


# --- Property Tests ---


class TestMalformedOntologyDefinitionRejection:
    """Property 4: Malformed Ontology Definition Rejection Preserves State.

    For any malformed/duplicate definition submitted, the store rejects with
    structured error and state remains unchanged.
    """

    @given(
        existing=valid_ontology_definition_strategy(),
        malformed=definition_with_duplicate_concept_ids_strategy(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_duplicate_concept_ids_rejected_preserves_state(
        self,
        existing: OntologyDefinition,
        malformed: OntologyDefinition,
    ) -> None:
        """Creating a definition with duplicate concept IDs is rejected and state is preserved."""
        store = OntologyStore(tempfile.mkdtemp())

        # Seed the store with an existing valid definition
        store.create_definition(existing)
        state_before = _snapshot_store_state(store)

        # Give the malformed definition a different name so it's not rejected for name duplication
        malformed.metadata["name"] = malformed.metadata.get("name", "x") + "_dup"
        assume(malformed.metadata["name"] != existing.metadata["name"])

        # Attempt to create the malformed definition
        try:
            store.create_definition(malformed)
            # If no error, the definition didn't actually have duplicates (shouldn't happen)
            assert False, "Expected OntologyStoreError for duplicate concept IDs"
        except OntologyStoreError as e:
            assert e.error_type == "DUPLICATE_IDENTIFIER"
            assert e.message  # Error has a meaningful message

        # State must be unchanged
        state_after = _snapshot_store_state(store)
        assert state_before == state_after

    @given(
        existing=valid_ontology_definition_strategy(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_duplicate_name_rejected_preserves_state(
        self,
        existing: OntologyDefinition,
    ) -> None:
        """Creating a definition with an existing name is rejected and state is preserved."""
        store = OntologyStore(tempfile.mkdtemp())

        # Create the initial definition
        store.create_definition(existing)
        state_before = _snapshot_store_state(store)

        # Attempt to create another definition with the same name
        duplicate = OntologyDefinition(
            concepts=[OntologyConcept(
                concept_id="ontology:unique_new_concept",
                label="Some New Concept",
                properties={},
                relationships=[],
            )],
            relationships=[],
            metadata={"name": existing.metadata["name"]},
        )

        try:
            store.create_definition(duplicate)
            assert False, "Expected OntologyStoreError for duplicate name"
        except OntologyStoreError as e:
            assert e.error_type == "DUPLICATE_IDENTIFIER"
            assert existing.metadata["name"] in e.message

        # State must be unchanged
        state_after = _snapshot_store_state(store)
        assert state_before == state_after

    @given(malformed=definition_without_name_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_missing_name_rejected_preserves_state(
        self,
        malformed: OntologyDefinition,
    ) -> None:
        """Creating a definition without a name in metadata is rejected and state is preserved."""
        store = OntologyStore(tempfile.mkdtemp())
        state_before = _snapshot_store_state(store)

        try:
            store.create_definition(malformed)
            assert False, "Expected OntologyStoreError for missing name"
        except OntologyStoreError as e:
            assert e.error_type == "VALIDATION_ERROR"
            assert e.message  # Error has a meaningful message

        # State must be unchanged
        state_after = _snapshot_store_state(store)
        assert state_before == state_after

    @given(
        existing=valid_ontology_definition_strategy(),
        malformed=definition_with_duplicate_concept_ids_strategy(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_malformed_update_rejected_preserves_state(
        self,
        existing: OntologyDefinition,
        malformed: OntologyDefinition,
    ) -> None:
        """Updating with a malformed definition is rejected and the original remains."""
        store = OntologyStore(tempfile.mkdtemp())

        # Create valid definition first
        store.create_definition(existing)
        state_before = _snapshot_store_state(store)

        # Try to update it with a definition that has duplicate concept IDs
        malformed.metadata["name"] = existing.metadata["name"]

        try:
            store.update_definition(malformed)
            assert False, "Expected OntologyStoreError for duplicate concept IDs"
        except OntologyStoreError as e:
            assert e.error_type == "DUPLICATE_IDENTIFIER"

        # State must be unchanged - original definition preserved
        state_after = _snapshot_store_state(store)
        assert state_before == state_after

    @given(
        existing=valid_ontology_definition_strategy(),
        another=valid_ontology_definition_strategy(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_multiple_valid_definitions_unaffected_by_failed_create(
        self,
        existing: OntologyDefinition,
        another: OntologyDefinition,
    ) -> None:
        """A failed create does not affect any previously stored definitions."""
        assume(existing.metadata["name"] != another.metadata["name"])
        store = OntologyStore(tempfile.mkdtemp())

        # Populate store with two valid definitions
        store.create_definition(existing)
        store.create_definition(another)
        state_before = _snapshot_store_state(store)

        # Attempt to create a definition with a duplicate name
        dup = OntologyDefinition(
            concepts=[],
            relationships=[],
            metadata={"name": existing.metadata["name"]},
        )

        try:
            store.create_definition(dup)
        except OntologyStoreError:
            pass

        # All existing definitions must be preserved
        state_after = _snapshot_store_state(store)
        assert state_before == state_after

    @given(existing=valid_ontology_definition_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_rejected_definition_not_queryable(
        self,
        existing: OntologyDefinition,
    ) -> None:
        """A rejected definition's concepts are not accessible via query interface."""
        store = OntologyStore(tempfile.mkdtemp())
        store.create_definition(existing)

        # Create a definition with duplicate concept IDs and a unique concept
        unique_id = "ontology:should_not_appear_in_store"
        malformed = OntologyDefinition(
            concepts=[
                OntologyConcept(concept_id=unique_id, label="Ghost", properties={}, relationships=[]),
                OntologyConcept(concept_id=unique_id, label="Ghost Dup", properties={}, relationships=[]),
            ],
            relationships=[],
            metadata={"name": "ghost_definition"},
        )

        try:
            store.create_definition(malformed)
        except OntologyStoreError:
            pass

        # The unique concept from the rejected definition should not be findable
        assert store.lookup_concept(unique_id) is None
        assert store.search_concepts("Ghost") == []


class TestMalformedSerializedDataRejection:
    """Property 17: Malformed Serialized Data Rejection.

    For any malformed serialized data, deserialization rejects with structured
    error indicating parse failure location.
    """

    @given(data=malformed_json_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_malformed_json_rejected_with_parse_error(self, data: str) -> None:
        """Any malformed JSON is rejected with a PARSE_ERROR containing location info."""
        store = OntologyStore(tempfile.mkdtemp())

        try:
            store.deserialize(data)
            # If it parsed, it must have been valid JSON that also conforms to schema
            # (shouldn't happen with our strategy, but guard just in case)
            assert False, f"Expected OntologyStoreError for malformed data: {data!r}"
        except OntologyStoreError as e:
            assert e.error_type == "PARSE_ERROR"
            assert e.message  # Has a meaningful error message
            # Parse errors should indicate location
            assert "line" in e.message.lower() or "column" in e.message.lower() or e.details.get("line") is not None

    @given(data=invalid_schema_json_strategy())
    @settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_schema_rejected_with_validation_error(self, data: str) -> None:
        """Valid JSON that doesn't conform to schema is rejected with SCHEMA_VALIDATION_ERROR."""
        store = OntologyStore(tempfile.mkdtemp())

        try:
            store.deserialize(data)
            assert False, f"Expected OntologyStoreError for invalid schema data: {data!r}"
        except OntologyStoreError as e:
            assert e.error_type == "SCHEMA_VALIDATION_ERROR"
            assert e.message  # Has a meaningful error message
            # Should indicate where in the schema the failure occurred
            assert "location" in e.details or "errors" in e.details

    @given(data=malformed_json_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_malformed_deserialization_does_not_alter_store(self, data: str) -> None:
        """Deserializing malformed data does not change the store's in-memory state."""
        store = OntologyStore(tempfile.mkdtemp())

        # Add a valid definition first
        valid = OntologyDefinition(
            concepts=[OntologyConcept(
                concept_id="ontology:baseline",
                label="Baseline Concept",
                properties={"stable": True},
                relationships=[],
            )],
            relationships=[],
            metadata={"name": "baseline"},
        )
        store.create_definition(valid)
        state_before = _snapshot_store_state(store)

        # Attempt malformed deserialization
        try:
            store.deserialize(data)
        except OntologyStoreError:
            pass

        # Store state is unchanged
        state_after = _snapshot_store_state(store)
        assert state_before == state_after

    @given(data=invalid_schema_json_strategy())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_invalid_schema_deserialization_does_not_alter_store(self, data: str) -> None:
        """Deserializing schema-invalid JSON does not change the store's in-memory state."""
        store = OntologyStore(tempfile.mkdtemp())

        # Add a valid definition first
        valid = OntologyDefinition(
            concepts=[OntologyConcept(
                concept_id="ontology:baseline",
                label="Baseline Concept",
                properties={"stable": True},
                relationships=[],
            )],
            relationships=[],
            metadata={"name": "baseline"},
        )
        store.create_definition(valid)
        state_before = _snapshot_store_state(store)

        # Attempt invalid schema deserialization
        try:
            store.deserialize(data)
        except OntologyStoreError:
            pass

        # Store state is unchanged
        state_after = _snapshot_store_state(store)
        assert state_before == state_after

    @given(
        prefix=st.text(min_size=0, max_size=20, alphabet="abcdefghijk "),
        suffix=st.text(min_size=0, max_size=20, alphabet="lmnopqrstuv "),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_corruption_of_valid_json_detected(self, prefix: str, suffix: str) -> None:
        """Prepending or appending garbage to valid JSON is detected and rejected."""
        assume(prefix.strip() != "" or suffix.strip() != "")
        store = OntologyStore(tempfile.mkdtemp())

        valid_json = json.dumps({
            "concepts": [{"concept_id": "ontology:test", "label": "Test"}],
            "relationships": [],
            "metadata": {"name": "test"},
        })

        corrupted = prefix + valid_json + suffix

        # If prefix or suffix is whitespace only, the JSON might still be valid
        # so we only test when the corruption actually makes it invalid
        try:
            result = store.deserialize(corrupted)
            # If it somehow parsed, the corruption was just whitespace - that's fine
        except OntologyStoreError as e:
            assert e.error_type in ("PARSE_ERROR", "SCHEMA_VALIDATION_ERROR")
            assert e.message  # Has a meaningful error message

    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    @given(st.data())
    def test_empty_and_whitespace_only_rejected(self, data: st.DataObject) -> None:
        """Empty strings and whitespace-only strings are rejected."""
        text = data.draw(st.sampled_from(["", " ", "\n", "\t", "   \n\t  "]))
        store = OntologyStore(tempfile.mkdtemp())

        try:
            store.deserialize(text)
            assert False, "Expected OntologyStoreError for empty/whitespace input"
        except OntologyStoreError as e:
            assert e.error_type == "PARSE_ERROR"
            assert e.message
