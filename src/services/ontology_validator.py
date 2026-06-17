"""
Ontology Entity Validator

Validates that entities referenced in a query exist in the ontology
before expensive orchestration/rendering. Requirement #4.

Provides early-exit validation to fail fast on invalid queries.
"""

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class OntologyValidator:
    """
    Validates query entities against ontology.
    
    Used as a pre-flight check in the query pipeline (Step 0.5)
    to catch invalid entities before routing to orchestrator.
    """

    def __init__(self, ontology_store):
        """
        Initialize validator.
        
        Args:
            ontology_store: OntologyStore instance with entity lookup methods
        """
        self.ontology = ontology_store

    def validate_query_entities(
        self,
        query: str,
        entity_refs: List[str],
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if all entities referenced in query exist in ontology.
        
        Args:
            query: Original query text (for context in error messages)
            entity_refs: List of entity reference strings to validate
        
        Returns:
            Tuple of (is_valid: bool, error_message: Optional[str])
            - (True, None) if all entities valid
            - (False, error_msg) if any entity missing
        """
        if not entity_refs:
            # No entities to validate
            return True, None

        invalid_entities = []

        for entity_ref in entity_refs:
            if not self.ontology.entity_exists(entity_ref):
                invalid_entities.append(entity_ref)
                logger.warning(f"Invalid entity reference: {entity_ref}")

        if invalid_entities:
            error_msg = self._format_error_message(invalid_entities, query)
            return False, error_msg

        logger.debug(f"All {len(entity_refs)} entities validated successfully")
        return True, None

    def _format_error_message(self, invalid_entities: List[str], query: str) -> str:
        """
        Format helpful error message for invalid entities.
        
        Args:
            invalid_entities: List of entity refs that don't exist
            query: Original query for context
        
        Returns:
            Formatted error message
        """
        if len(invalid_entities) == 1:
            return (
                f"Entity '{invalid_entities[0]}' not found in ontology. "
                f"Check the entity name and try again."
            )

        entities_str = ", ".join(f"'{e}'" for e in invalid_entities)
        return (
            f"The following entities were not found in ontology: {entities_str}. "
            f"Please verify entity names and try again."
        )

    def validate_data_source_access(
        self,
        entity_ref: str,
        user_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if user has access to data source behind entity.
        
        Args:
            entity_ref: Entity reference to check
            user_id: Optional user ID for access control
        
        Returns:
            Tuple of (has_access: bool, error_message: Optional[str])
        """
        try:
            entity = self.ontology.get_entity(entity_ref)
            if not entity:
                return False, f"Entity '{entity_ref}' not found"

            # Check if entity's data source is accessible
            data_source = entity.properties.get("data_source")
            if not data_source:
                return False, f"Entity '{entity_ref}' has no associated data source"

            # If access control enabled, check user permissions
            if user_id and hasattr(entity, "access_control"):
                if not entity.access_control.can_access(user_id):
                    return False, f"User does not have access to data source '{data_source}'"

            logger.debug(f"Access validated for entity: {entity_ref}")
            return True, None

        except Exception as e:
            logger.error(f"Access validation error for {entity_ref}: {e}")
            return False, f"Unable to validate access: {str(e)}"

    def suggest_similar_entities(
        self,
        invalid_entity: str,
        max_suggestions: int = 3,
    ) -> List[str]:
        """
        Suggest similar entity names for typo correction.
        
        Args:
            invalid_entity: The invalid entity reference
            max_suggestions: Max suggestions to return
        
        Returns:
            List of similar entity references
        """
        try:
            # Use ontology's fuzzy matching if available
            if hasattr(self.ontology, "find_similar_entities"):
                suggestions = self.ontology.find_similar_entities(
                    invalid_entity,
                    limit=max_suggestions,
                )
                return suggestions
            return []
        except Exception as e:
            logger.warning(f"Error getting suggestions: {e}")
            return []


class ValidationError(Exception):
    """Raised when entity validation fails."""

    def __init__(self, message: str, invalid_entities: Optional[List[str]] = None):
        self.message = message
        self.invalid_entities = invalid_entities or []
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message
