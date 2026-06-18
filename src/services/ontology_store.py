"""S3-backed Ontology Store with uniform query interface.

Provides concept lookup, hierarchical traversal, keyword search, and CRUD
operations backed by JSON objects in S3. The same interface can be swapped
to a graph DB or RDBMS backend in a future phase.

S3 structure:
  s3://visualization-poc-bucket/ontology/{name}.json

Requirements: 3.1, 3.3, 3.5, 3.6, 3.7, 3.8, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
"""

import json
import logging
from typing import Any

from pydantic import ValidationError

from src.config import S3_BUCKET, S3_ONTOLOGY_PREFIX, get_s3_client
from src.models.ontology import OntologyConcept, OntologyDefinition, OntologyRelationship

logger = logging.getLogger(__name__)


class OntologyStoreError(Exception):
    """Structured error raised by the Ontology Store."""

    def __init__(self, error_type: str, message: str, details: dict[str, Any] | None = None):
        self.error_type = error_type
        self.message = message
        self.details = details or {}
        super().__init__(message)


class OntologyStore:
    """S3-backed ontology store with uniform query interface.

    Stores ontology definitions as JSON objects in S3.
    Provides concept lookup, hierarchy traversal, keyword search, and
    full CRUD with schema validation.
    """

    def __init__(
        self,
        bucket: str = S3_BUCKET,
        prefix: str = S3_ONTOLOGY_PREFIX,
    ):
        """Initialize the store with S3 bucket and prefix.

        Args:
            bucket: S3 bucket name.
            prefix: S3 key prefix for ontology files.
        """
        self.bucket = bucket
        self.prefix = prefix
        self._s3 = get_s3_client()
        self._definitions: dict[str, OntologyDefinition] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all ontology definitions from S3 into memory.
        
        Falls back to loading from local data/ontology/ directory if S3
        is unavailable (e.g., local development without AWS credentials).
        """
        try:
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".json"):
                        try:
                            response = self._s3.get_object(Bucket=self.bucket, Key=key)
                            body = response["Body"].read().decode("utf-8")
                            definition = self.deserialize(body)
                            name = definition.metadata.get("name", key.split("/")[-1].replace(".json", ""))
                            self._definitions[name] = definition
                        except OntologyStoreError as e:
                            logger.error(f"Failed to load ontology from {key}: {e.message}")
                        except Exception as e:
                            logger.error(f"Failed to read {key}: {e}")
        except Exception as e:
            logger.error(f"Failed to list ontology objects: {e}")

        # Fallback: load from local filesystem if S3 yielded nothing
        if not self._definitions:
            self._load_from_local()

    def _load_from_local(self) -> None:
        """Load ontology definitions from local data/ontology/ directory.

        Used as fallback when S3 is unavailable (local dev, no AWS creds).
        """
        import pathlib
        local_dir = pathlib.Path("data/ontology")
        if not local_dir.exists():
            logger.warning(f"Local ontology directory not found: {local_dir}")
            return

        for json_file in local_dir.glob("*.json"):
            try:
                body = json_file.read_text(encoding="utf-8")
                definition = self.deserialize(body)
                name = definition.metadata.get("name", json_file.stem)
                self._definitions[name] = definition
                logger.info(f"Loaded ontology from local file: {json_file.name}")
            except OntologyStoreError as e:
                logger.error(f"Failed to load local ontology {json_file}: {e.message}")
            except Exception as e:
                logger.error(f"Failed to read local ontology {json_file}: {e}")

    # --- Query Interface ---

    def lookup_concept(self, concept_id: str) -> OntologyConcept | None:
        """Look up a concept by its identifier across all loaded definitions.

        Args:
            concept_id: The unique concept identifier to search for.

        Returns:
            The matching OntologyConcept, or None if not found.
        """
        for definition in self._definitions.values():
            for concept in definition.concepts:
                if concept.concept_id == concept_id:
                    return concept
        return None

    def traverse_hierarchy(self, concept_id: str, direction: str = "children") -> list[OntologyConcept]:
        """Traverse concept relationships in the given direction.

        Args:
            concept_id: The starting concept identifier.
            direction: "children" for outgoing (source → target),
                       "parents" for incoming (target ← source).

        Returns:
            List of related concepts found by traversal.
        """
        related_ids: list[str] = []
        for definition in self._definitions.values():
            for rel in definition.relationships:
                if direction == "children" and rel.source_id == concept_id:
                    related_ids.append(rel.target_id)
                elif direction == "parents" and rel.target_id == concept_id:
                    related_ids.append(rel.source_id)
            for concept in definition.concepts:
                for rel in concept.relationships:
                    if direction == "children" and rel.source_id == concept_id:
                        related_ids.append(rel.target_id)
                    elif direction == "parents" and rel.target_id == concept_id:
                        related_ids.append(rel.source_id)

        results: list[OntologyConcept] = []
        seen: set[str] = set()
        for rid in related_ids:
            if rid not in seen:
                concept = self.lookup_concept(rid)
                if concept:
                    results.append(concept)
                    seen.add(rid)
        return results

    def search_concepts(self, keyword: str) -> list[OntologyConcept]:
        """Keyword search over concept labels, descriptions, and concept_ids.

        Uses multiple matching strategies with priority ranking:
        1. Exact match on concept_id (highest priority)
        2. Exact substring match on label
        3. Substring match on concept_id words
        4. Stemmed/partial word match on label or concept_id
        5. Substring match on description (lowest priority)

        Results are sorted by match quality — exact matches first.

        Args:
            keyword: The search term to match against concepts.

        Returns:
            List of concepts matching the keyword, ordered by match quality.
        """
        keyword_lower = keyword.lower().strip()
        if not keyword_lower:
            return []

        # Generate stemmed variants for partial matching
        stems = self._get_stems(keyword_lower)

        # Collect results with priority scores (lower = better)
        scored: list[tuple[int, OntologyConcept]] = []
        seen: set[str] = set()

        for definition in self._definitions.values():
            for concept in definition.concepts:
                if concept.concept_id in seen:
                    continue

                score = self._score_concept_match(concept, keyword_lower, stems)
                if score is not None:
                    scored.append((score, concept))
                    seen.add(concept.concept_id)

        # Sort by score (lower = better match)
        scored.sort(key=lambda x: x[0])
        return [concept for _, concept in scored]

    def _score_concept_match(self, concept: OntologyConcept, keyword: str, stems: set[str]) -> int | None:
        """Score how well a concept matches the keyword. Returns None if no match.
        
        Lower scores = better matches:
        0 = exact concept_id match
        1 = exact label match
        2 = exact filter_keyword match
        3 = concept_id word containment
        4 = label word stem match
        5 = filter_keyword match
        6 = description containment
        7 = description stem match
        """
        label_lower = concept.label.lower()
        concept_id_lower = concept.concept_id.lower().replace("ontology:", "").replace("_", " ")
        description = concept.properties.get("description", "").lower()
        filter_keywords = concept.properties.get("filter_keywords", [])

        # Priority 0: exact concept_id match (e.g. "workforce_metrics" matches ontology:workforce_metrics)
        if keyword.replace(" ", "_") == concept_id_lower.replace(" ", "_"):
            return 0

        # Priority 1: exact substring in label
        if keyword in label_lower:
            return 1

        # Priority 2: exact match in filter_keywords (highest priority for user queries)
        for kw in filter_keywords:
            if keyword.lower() == kw.lower():
                return 2

        # Priority 3: exact substring in concept_id words
        if keyword in concept_id_lower:
            return 3

        # Priority 4: stemmed matching on label or concept_id words
        label_words = set(label_lower.split())
        concept_id_words = set(concept_id_lower.split())
        all_words = label_words | concept_id_words

        for stem in stems:
            for word in all_words:
                if word.startswith(stem) or stem.startswith(word):
                    return 4

        # Priority 5: partial match in filter_keywords (common for multi-word keywords)
        for kw in filter_keywords:
            if keyword in kw.lower():
                return 5

        # Priority 6: exact substring in description
        if keyword in description:
            return 6

        # Priority 7: stem match in description (only for longer stems)
        desc_words = set(description.split())
        for stem in stems:
            if len(stem) >= 4:
                for word in desc_words:
                    if word.startswith(stem):
                        return 7

        return None

    @staticmethod
    def _get_stems(keyword: str) -> set[str]:
        """Generate simple stemmed variants of a keyword.

        Strips common English suffixes to improve matching.
        E.g., "products" -> {"products", "product"}
              "transactions" -> {"transactions", "transaction"}
              "pricing" -> {"pricing", "pric"}
        """
        stems = {keyword}

        # Strip plural 's'
        if keyword.endswith("s") and len(keyword) > 3:
            stems.add(keyword[:-1])

        # Strip 'es' plural
        if keyword.endswith("es") and len(keyword) > 4:
            stems.add(keyword[:-2])

        # Strip 'ing'
        if keyword.endswith("ing") and len(keyword) > 5:
            stems.add(keyword[:-3])

        # Strip 'tion'/'sion'
        if keyword.endswith("tion") and len(keyword) > 5:
            stems.add(keyword[:-4])
        if keyword.endswith("sion") and len(keyword) > 5:
            stems.add(keyword[:-4])

        # Strip 'ment'
        if keyword.endswith("ment") and len(keyword) > 5:
            stems.add(keyword[:-4])

        # Strip 'ance'/'ence'
        if keyword.endswith("ance") and len(keyword) > 5:
            stems.add(keyword[:-4])
        if keyword.endswith("ence") and len(keyword) > 5:
            stems.add(keyword[:-4])

        return stems

    # --- CRUD Interface ---

    def create_definition(self, definition: OntologyDefinition) -> None:
        """Persist a new ontology definition to S3.

        Args:
            definition: The ontology definition to create.

        Raises:
            OntologyStoreError: If the definition is malformed or has a duplicate name.
        """
        name = definition.metadata.get("name")
        if not name:
            raise OntologyStoreError(
                error_type="VALIDATION_ERROR",
                message="Ontology definition must have a 'name' in metadata.",
            )

        if name in self._definitions:
            raise OntologyStoreError(
                error_type="DUPLICATE_IDENTIFIER",
                message=f"Ontology definition with name '{name}' already exists.",
                details={"existing_name": name},
            )

        self._validate_no_duplicate_concepts(definition)
        self._persist_to_s3(name, definition)
        self._definitions[name] = definition

    def update_definition(self, definition: OntologyDefinition) -> None:
        """Update an existing ontology definition in S3.

        Args:
            definition: The updated ontology definition.

        Raises:
            OntologyStoreError: If the definition doesn't exist or is malformed.
        """
        name = definition.metadata.get("name")
        if not name:
            raise OntologyStoreError(
                error_type="VALIDATION_ERROR",
                message="Ontology definition must have a 'name' in metadata.",
            )

        if name not in self._definitions:
            raise OntologyStoreError(
                error_type="NOT_FOUND",
                message=f"Ontology definition with name '{name}' does not exist.",
            )

        self._validate_no_duplicate_concepts(definition)
        self._persist_to_s3(name, definition)
        self._definitions[name] = definition

    def delete_definition(self, name: str) -> None:
        """Delete an ontology definition from S3.

        Args:
            name: The name of the ontology definition to remove.

        Raises:
            OntologyStoreError: If the definition doesn't exist.
        """
        if name not in self._definitions:
            raise OntologyStoreError(
                error_type="NOT_FOUND",
                message=f"Ontology definition with name '{name}' does not exist.",
            )

        key = f"{self.prefix}{name}.json"
        try:
            self._s3.delete_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            logger.error(f"Failed to delete {key} from S3: {e}")

        del self._definitions[name]

    # --- Serialization Interface ---

    def serialize(self, definition: OntologyDefinition) -> str:
        """Serialize an ontology definition to JSON string.

        Args:
            definition: The ontology definition to serialize.

        Returns:
            A JSON string representation.

        Raises:
            OntologyStoreError: If serialization fails.
        """
        try:
            return definition.model_dump_json(indent=2)
        except Exception as e:
            raise OntologyStoreError(
                error_type="SERIALIZATION_ERROR",
                message=f"Failed to serialize ontology definition: {e}",
            )

    def deserialize(self, data: str) -> OntologyDefinition:
        """Deserialize a JSON string into an OntologyDefinition.

        Args:
            data: JSON string to parse.

        Returns:
            The parsed OntologyDefinition.

        Raises:
            OntologyStoreError: If the data is malformed or doesn't conform to schema.
        """
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError as e:
            raise OntologyStoreError(
                error_type="PARSE_ERROR",
                message=f"Malformed JSON at line {e.lineno}, column {e.colno}: {e.msg}",
                details={"line": e.lineno, "column": e.colno},
            )

        try:
            return OntologyDefinition.model_validate(parsed)
        except ValidationError as e:
            first_error = e.errors()[0] if e.errors() else {}
            raise OntologyStoreError(
                error_type="SCHEMA_VALIDATION_ERROR",
                message=f"Data does not conform to ontology schema: {first_error.get('msg', str(e))}",
                details={"location": list(first_error.get("loc", [])), "errors": e.error_count()},
            )

    def pretty_print(self, definition: OntologyDefinition) -> str:
        """Format an ontology definition as human-readable indented JSON.

        Args:
            definition: The ontology definition to format.

        Returns:
            A pretty-printed JSON string.
        """
        data = definition.model_dump()
        return json.dumps(data, indent=4, sort_keys=False, ensure_ascii=False)

    # --- Internal Helpers ---

    def _validate_no_duplicate_concepts(self, definition: OntologyDefinition) -> None:
        """Check for duplicate concept IDs within a definition."""
        seen_ids: set[str] = set()
        for concept in definition.concepts:
            if concept.concept_id in seen_ids:
                raise OntologyStoreError(
                    error_type="DUPLICATE_IDENTIFIER",
                    message=f"Duplicate concept_id '{concept.concept_id}' in definition.",
                    details={"concept_id": concept.concept_id},
                )
            seen_ids.add(concept.concept_id)

    def _persist_to_s3(self, name: str, definition: OntologyDefinition) -> None:
        """Write definition to S3 as JSON object."""
        key = f"{self.prefix}{name}.json"
        serialized = self.serialize(definition)
        self._s3.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=serialized,
            ContentType="application/json",
        )

    # --- Convenience ---

    def get_all_definitions(self) -> dict[str, OntologyDefinition]:
        """Return all loaded definitions."""
        return dict(self._definitions)

    def reload(self) -> None:
        """Reload all definitions from S3."""
        self._definitions.clear()
        self._load_all()
