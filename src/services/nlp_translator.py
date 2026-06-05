"""NLP Translator with Bedrock Claude integration.

Parses natural language queries into Structured Intents using ontology context
and query history bias. Integrates with Amazon Bedrock (Claude Sonnet) for
intent classification and uses the Ontology Store for entity resolution.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 10.6
"""

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.config import SIMILARITY_THRESHOLD
from src.models.shared import NLPError, StructuredIntent
from src.services.lru_cache import LRUCache
from src.services.ontology_store import OntologyStore
from src.services.query_history_store import QueryHistoryStore

logger = logging.getLogger(__name__)


class BedrockClassifier:
    """Classifies query type using Amazon Bedrock Claude.
    Separated into its own class to allow easy mocking in tests and to
    isolate the external dependency on AWS Bedrock.
    """

    def __init__(self, model_id: str | None = None):
        """Initialize with the Bedrock model identifier.
        Args:
            model_id: The Bedrock Claude model ID for intent classification.
        """
        from src.config import DEFAULT_MODEL_ID
        self.model_id = model_id or DEFAULT_MODEL_ID
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazily initialize the Bedrock runtime client."""
        if self._client is None:
            from src.config import get_bedrock_client
            self._client = get_bedrock_client()
        return self._client

    def classify_query_type(
        self, query_text: str, ontology_context: list[dict[str, Any]]) -> str | None:
        """Classify a query into one of the supported query types.
        Uses a structured prompt with ontology context to determine whether
        the query is a lookup, aggregation, or comparison.
        Args:
            query_text: The natural language query to classify.
            ontology_context: List of resolved ontology concepts with their
                properties, providing domain context for classification.
        Returns:
            One of "lookup", "aggregation", "comparison", or None if
            classification fails or is ambiguous.
        """
        from src.services.cost_tracker import get_cost_tracker
        
        prompt = self._build_classification_prompt(query_text, ontology_context)
        try:
            client = self._get_client()
            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 100,
                    "temperature": 0.0,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                }
            )
            response = client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response["body"].read())
            
            # Track cost
            usage = response_body.get("usage", {})
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            get_cost_tracker().log_invocation(
                model_id=self.model_id,
                component="nlp_translator",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
            
            content = response_body.get("content", [])
            if content and len(content) > 0:
                text = content[0].get("text", "").strip().lower()
                return self._parse_classification(text)
            return None
        except Exception as e:
            logger.error(
                json.dumps(
                    {
                        "service_name": "nlp_translator",
                        "operation": "classify_query_type",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                )
            )
            return None

    def _build_classification_prompt(
        self, query_text: str, ontology_context: list[dict[str, Any]]
    ) -> str:
        """Build the structured prompt for query type classification.
        Args:
            query_text: The user's natural language query.
            ontology_context: Resolved ontology concepts for context.
        Returns:
            The formatted prompt string.
        """
        context_str = json.dumps(ontology_context, indent=2) if ontology_context else "[]"

        return f"""You are a query classifier for a data retrieval system. Classify the following natural language query into exactly one of these types:

- "lookup": The user wants to retrieve specific data points, records, or details about a particular entity.
- "aggregation": The user wants summarized, computed, or grouped data (totals, averages, counts, trends over time).
- "comparison": The user wants to compare two or more entities, time periods, or data sets.

Ontology context (available data concepts):
{context_str}

User query: "{query_text}"

Respond with ONLY one word: lookup, aggregation, or comparison. Do not include any other text."""

    @staticmethod
    def _parse_classification(text: str) -> str | None:
        """Parse the LLM response into a valid query type.
        Args:
            text: The raw text response from the LLM.
        Returns:
            A valid query type or None if unparseable.
        """
        valid_types = {"lookup", "aggregation", "comparison"}
        # Try exact match first
        if text in valid_types:
            return text
        # Try to find a valid type within the response
        for qt in valid_types:
            if qt in text:
                return qt
        return None


class NLPTranslator:
    """Translates natural language queries into Structured Intents.
    Orchestrates entity resolution against the Ontology Store, history-based
    routing bias from the Query History Store, and query type classification
    via Amazon Bedrock Claude.

    The translator gracefully degrades if the Query History Store is
    unavailable, skipping the routing bias step and continuing without
    history-based metadata.
    """

    def __init__(
        self,
        ontology_store: OntologyStore | None = None,
        history_store: QueryHistoryStore | None = None,
        classifier: BedrockClassifier | None = None,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ):
        """Initialize the NLP Translator with its dependencies.

        Args:
            ontology_store: The ontology store for entity resolution.
                Defaults to a flat-file store using the configured directory.
            history_store: The query history store for routing bias.
                If None, history-based routing is disabled.
            classifier: The Bedrock classifier for query type classification.
                Defaults to a Claude Sonnet classifier.
            similarity_threshold: Minimum cosine similarity for history matches.
                Defaults to 0.85.
        """
        self.ontology_store = ontology_store or OntologyStore()
        self.history_store = history_store
        self.classifier = classifier or BedrockClassifier()
        self.similarity_threshold = similarity_threshold
        self._classification_cache: LRUCache[str, str] = LRUCache(max_size=1000)

    async def translate(
        self, query_text: str, user_id: str = "anonymous"
    ) -> StructuredIntent | NLPError:
        """Parse a natural language query into a Structured Intent.
        Follows the NLP translation pipeline:
        1. Check Query History Store for similar past intents (cosine >= 0.85)
        2. Resolve entities against Ontology Store using keyword search
        3. Classify query type via Bedrock Claude with ontology context
        4. Produce StructuredIntent with all required fields
        Args:
            query_text: The natural language query text from the user.
            user_id: The authenticated user's identifier. Defaults to "anonymous".
        Returns:
            A StructuredIntent on success, or an NLPError on failure.
        """
        query_id = uuid.uuid4()
        # Validate input
        if not query_text or not query_text.strip():
            return NLPError(
                error_code="UNPARSEABLE_QUERY",
                error_message="Query text is empty or contains only whitespace.",
                query_id=query_id,
            )
        query_text = query_text.strip()
        # Steps 1 & 2: Run entity resolution and history bias concurrently
        entity_refs, routing_metadata = await asyncio.gather(
            asyncio.to_thread(self._resolve_entities, query_text),
            asyncio.to_thread(self._get_history_bias, query_text),
        )

        if not entity_refs:
            return NLPError(
                error_code="NO_ONTOLOGY_MATCH",
                error_message=(
                    f"No ontology concepts matched the query: '{query_text}'. "
                    "Unable to resolve any entity references."
                ),
                query_id=query_id,
            )

        # Specificity check: require at least one strong keyword match.
        # A "strong" match is a keyword that appears in a concept label as a
        # substantial portion (not just a short substring of a longer label).
        keywords = self._extract_keywords(query_text)
        if not self._has_strong_match(keywords, entity_refs):
            return NLPError(
                error_code="AMBIGUOUS_INTENT",
                error_message=(
                    f"The query '{query_text}' is too vague to resolve to a specific "
                    "data domain. Please include specific terms like 'revenue', "
                    "'products', 'sales', 'inventory', etc."
                ),
                query_id=query_id,
            )

        # Step 3: Classify query type — check cache first
        cache_key = self._classification_cache_key(query_text, entity_refs)
        cached_type = self._classification_cache.get(cache_key)
        if cached_type is not None:
            query_type = cached_type
        else:
            ontology_context = self._build_ontology_context(entity_refs)
            query_type = self.classifier.classify_query_type(query_text, ontology_context)

            if query_type is None:
                return NLPError(
                    error_code="AMBIGUOUS_INTENT",
                    error_message=(
                        f"Unable to classify the query type for: '{query_text}'. "
                        "The query may be ambiguous or not match supported patterns."
                    ),
                    query_id=query_id,
                )

            self._classification_cache.put(cache_key, query_type)

        # Step 4: Produce StructuredIntent
        return StructuredIntent(
            query_id=query_id,
            query_type=query_type,
            entity_refs=entity_refs,
            routing_metadata={**routing_metadata, **self._extract_viz_hints(query_text)},
            timestamp=datetime.now(timezone.utc),
        )

    def _get_history_bias(self, query_text: str) -> dict:
        """Check the Query History Store for similar past intents.

        If a match with similarity >= threshold is found, extract the routing
        metadata from the most recent match to bias future routing.

        Gracefully degrades if the history store is unavailable or encounters
        errors — returns empty metadata and continues.

        Args:
            query_text: The query text to find similar past queries for.

        Returns:
            Routing metadata dict. Contains preferred_agent and source if
            a history match is found, otherwise empty dict.
        """
        if self.history_store is None:
            return {}

        try:
            matches = self.history_store.find_similar(
                query_text, threshold=self.similarity_threshold
            )
            if matches:
                # Use the most recent match (highest similarity, sorted desc)
                best_match = matches[0]
                history_routing = best_match.intent.routing_metadata
                if history_routing:
                    return {
                        "preferred_agent": history_routing.get("preferred_agent", ""),
                        "source": "history_bias",
                    }
        except Exception as e:
            # Graceful degradation: log and continue without history bias
            logger.error(
                json.dumps(
                    {
                        "service_name": "nlp_translator",
                        "operation": "get_history_bias",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                )
            )

        return {}

    def _resolve_entities(self, query_text: str) -> list[str]:
        """Resolve entity references in the query against the Ontology Store.
        Extracts keywords from the query text and searches the ontology for
        matching concepts. Returns canonical concept identifiers for all
        matched concepts.

        Args:
            query_text: The natural language query text.

        Returns:
            List of canonical ontology concept identifiers (concept_ids).
            Empty list if no concepts match.
        """
        keywords = self._extract_keywords(query_text)
        resolved_ids: list[str] = []
        seen: set[str] = set()

        for keyword in keywords:
            concepts = self.ontology_store.search_concepts(keyword)
            for concept in concepts:
                if concept.concept_id not in seen:
                    resolved_ids.append(concept.concept_id)
                    seen.add(concept.concept_id)

        return resolved_ids

    def _extract_keywords(self, query_text: str) -> list[str]:
        """Extract meaningful keywords from query text for ontology search.

        Performs simple tokenization and stop word removal to identify
        candidate terms for ontology concept matching.

        Args:
            query_text: The natural language query text.

        Returns:
            List of candidate keywords for ontology search.
        """
        stop_words = {
            "a", "an", "the", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "above",
            "below", "between", "and", "but", "or", "not", "no", "nor",
            "so", "yet", "both", "either", "neither", "each", "every",
            "all", "any", "few", "more", "most", "other", "some", "such",
            "than", "too", "very", "just", "about", "also", "how", "what",
            "which", "who", "whom", "this", "that", "these", "those", "am",
            "it", "its", "i", "me", "my", "we", "our", "you", "your",
            "he", "him", "his", "she", "her", "they", "them", "their",
            "show", "tell", "give", "get", "find", "list", "display",
            "many", "much",
        }

        # Tokenize: split on whitespace and punctuation, lowercase
        words = query_text.lower().split()
        # Remove punctuation from word boundaries
        cleaned = []
        for word in words:
            cleaned_word = word.strip(".,;:!?\"'()[]{}")
            if cleaned_word and cleaned_word not in stop_words and len(cleaned_word) > 1:
                cleaned.append(cleaned_word)

        # Also try multi-word combinations (bigrams) for compound concept matching
        bigrams = []
        for i in range(len(cleaned) - 1):
            bigrams.append(f"{cleaned[i]} {cleaned[i + 1]}")

        # Return individual keywords followed by bigrams
        return cleaned + bigrams

    def _build_ontology_context(self, entity_refs: list[str]) -> list[dict[str, Any]]:
        """Build ontology context for the classifier from resolved entity refs.

        Looks up each resolved concept and formats it as a dict for inclusion
        in the classification prompt.

        Args:
            entity_refs: List of canonical ontology concept identifiers.

        Returns:
            List of concept dicts with id, label, and properties.
        """
        context: list[dict[str, Any]] = []
        for concept_id in entity_refs:
            concept = self.ontology_store.lookup_concept(concept_id)
            if concept:
                context.append(
                    {
                        "concept_id": concept.concept_id,
                        "label": concept.label,
                        "properties": concept.properties,
                    }
                )
        return context

    def _classification_cache_key(self, query_text: str, entity_refs: list[str]) -> str:
        """Generate a deterministic cache key for classification results.

        Uses SHA-256 of normalized query text combined with sorted entity_refs.

        Args:
            query_text: The raw query text.
            entity_refs: Resolved entity reference IDs.

        Returns:
            Hex digest string to use as cache key.
        """
        normalized_query = query_text.strip().lower()
        key_input = f"{normalized_query}|{','.join(sorted(entity_refs))}"
        return hashlib.sha256(key_input.encode()).hexdigest()

    def _has_strong_match(self, keywords: list[str], entity_refs: list[str]) -> bool:
        """Check if at least one keyword is a strong match against resolved concepts.

        A "strong" match requires the keyword to cover a significant portion
        of a concept label (not just a 3-letter fragment matching inside a
        longer word). This prevents vague queries like "for each quarter"
        from matching "Quarterly Report" on the substring "quarter".

        Rules for a strong match:
        - Keyword length >= 5 AND keyword matches a concept label word exactly,
          OR keyword covers >= 60% of the concept label length.
        - Alternatively, the keyword IS the full concept label (case-insensitive).

        Args:
            keywords: Extracted keywords from the query.
            entity_refs: Resolved concept IDs.

        Returns:
            True if at least one keyword is a strong match.
        """
        # Strong domain keywords that always indicate intentional queries
        domain_anchors = {
            "revenue", "sales", "product", "products", "catalog", "inventory",
            "stock", "price", "prices", "pricing", "supplier", "suppliers",
            "order", "orders", "volume", "category", "categories", "region",
            "regions", "report", "financial", "quarterly",
        }

        for keyword in keywords:
            kw_lower = keyword.lower()
            # Direct domain anchor match
            if kw_lower in domain_anchors:
                return True
            # Check if keyword substantially matches any concept label
            for concept_id in entity_refs:
                concept = self.ontology_store.lookup_concept(concept_id)
                if concept:
                    label_lower = concept.label.lower()
                    label_words = label_lower.split()
                    # Exact word match within label
                    if kw_lower in label_words:
                        return True
                    # Keyword covers >= 60% of label
                    if len(kw_lower) >= 5 and len(kw_lower) / len(label_lower) >= 0.6:
                        return True

        return False
