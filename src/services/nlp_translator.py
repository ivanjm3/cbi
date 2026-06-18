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

        Uses a two-tier approach:
        1. PRIMARY: LLM classification via Bedrock Claude (best accuracy)
        2. FALLBACK: Keyword-based heuristic if LLM is unavailable

        This ensures the system NEVER returns None — queries always get
        classified, even during Bedrock outages.

        Args:
            query_text: The natural language query to classify.
            ontology_context: List of resolved ontology concepts with their
                properties, providing domain context for classification.
        Returns:
            One of "count", "lookup", "aggregation", "comparison". Never returns None.
        """
        # PRIMARY: LLM classification
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
            
            content = response_body.get("content", [])
            if content and len(content) > 0:
                text = content[0].get("text", "").strip().lower()
                llm_result = self._parse_classification(text)
                if llm_result:
                    return llm_result

            # LLM returned unparseable response — fall through to heuristic
            logger.warning(
                json.dumps({
                    "service_name": "nlp_translator",
                    "operation": "classify_query_type",
                    "event": "llm_response_unparseable",
                    "fallback": "heuristic",
                })
            )
        except Exception as e:
            logger.error(
                json.dumps(
                    {
                        "service_name": "nlp_translator",
                        "operation": "classify_query_type",
                        "event": "llm_classification_failed",
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                        "fallback": "heuristic",
                    }
                )
            )

        # FALLBACK: Keyword-based heuristic classification
        # This ensures the system never fails due to Bedrock unavailability.
        return self._heuristic_classify(query_text)

    def _heuristic_classify(self, query_text: str) -> str:
        """Classify query type using keyword heuristics.

        Used as a fallback when Bedrock is unavailable or returns
        unparseable results. Provides reasonable accuracy for common
        query patterns.

        Args:
            query_text: The natural language query.

        Returns:
            One of "count", "lookup", "aggregation", "comparison".
        """
        text = query_text.lower()

        # Detect COUNT queries first (for "how many" questions)
        count_signals = [
            "how many", "total number", "how much", "how many total",
            "count", "what is the total", "number of",
        ]
        
        comparison_signals = [
            "compare", "comparison", "versus", " vs ", " vs.", "difference",
            "between", "against", "relative to", "compared to", "contrast",
        ]
        aggregation_signals = [
            "total", "sum", "average", "avg",
            "trend", "over time", "growth", "aggregate", "overall",
            "breakdown", "distribution", "percentage", "proportion",
            "minimum", "maximum", "median", "mean",
        ]

        if any(s in text for s in count_signals):
            return "count"
        if any(s in text for s in comparison_signals):
            return "comparison"
        if any(s in text for s in aggregation_signals):
            return "aggregation"
        return "lookup"  # Safe default for specific data requests

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
        registered_agent_ids: list[str] | None = None,
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
            registered_agent_ids: Optional list of currently registered agent IDs.
                Used for agent-aware tie-breaking during entity resolution.
        """
        self.ontology_store = ontology_store or OntologyStore()
        self.history_store = history_store
        self.classifier = classifier or BedrockClassifier()
        self.similarity_threshold = similarity_threshold
        self._registered_agent_ids = set(registered_agent_ids) if registered_agent_ids else set()
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
            # classify_query_type now ALWAYS returns a valid type (never None)
            # thanks to the heuristic fallback. No error case needed here.
            self._classification_cache.put(cache_key, query_type)

        # Step 4: Produce StructuredIntent
        return StructuredIntent(
            query_id=query_id,
            query_type=query_type,
            entity_refs=entity_refs,
            routing_metadata={
                **routing_metadata,
                "query_text": query_text,
                **self._extract_viz_hints(query_text),
                **self._extract_column_hints(query_text, entity_refs),
            },
            timestamp=datetime.now(timezone.utc),
        )

    def _extract_viz_hints(self, query_text: str) -> dict:
        """Extract visualization type hints from the query text.

        Detects if the user explicitly requests a specific chart type
        (scatter, line, pie, bar, table) and returns it as a hint for
        the visualization renderer.

        Args:
            query_text: The original user query.

        Returns:
            Dict with 'requested_chart_type' if detected, otherwise empty.
        """
        import re
        text_lower = query_text.lower()

        chart_patterns = {
            "scatter": r"\b(scatter\s*(plot|chart|graph)?)\b",
            "bubble": r"\b(bubble\s*(chart|plot|graph)?)\b",
            "line": r"\b(line\s*(chart|graph|plot)|trend\s*(line|chart|graph)|area\s*(chart|graph))\b",
            "pie": r"\b(pie\s*(chart|graph))\b",
            "doughnut": r"\b(doughnut|donut)\s*(chart|graph|plot)?\b",
            "radar": r"\b(radar|spider|web)\s*(chart|graph|plot|diagram)?\b",
            "polarArea": r"\b(polar\s*area|polar)\s*(chart|graph|plot)?\b",
            "bar": r"\b(bar\s*(chart|graph|plot)|histogram|column\s*(chart|graph))\b",
            "table": r"\b(table|tabular|spreadsheet)\b",
        }

        for chart_type, pattern in chart_patterns.items():
            if re.search(pattern, text_lower):
                return {"requested_chart_type": chart_type}

        return {}

    def _extract_column_hints(self, query_text: str, entity_refs: list[str]) -> dict:
        """Extract column-level hints from the query by matching against ontology metadata.

        When the user's query mentions keywords that map to specific columns
        (e.g., "remote" → is_remote, "department" → department), this extracts
        those as hints so the SQL generator can produce targeted queries instead
        of generic aggregations over all columns.

        Uses three sources of column information from the ontology:
        1. filter_keywords — user-facing keywords mapped to columns
        2. columns — full column definitions with descriptions
        3. categorical_properties — legacy list of categorical column names

        Args:
            query_text: The original user query text.
            entity_refs: Resolved entity reference IDs.

        Returns:
            Dict with 'target_columns' list and 'group_by_hint' if relevant
            column keywords are detected.
        """
        text_lower = query_text.lower()
        hints: dict = {}
        matched_columns: list[str] = []
        matched_filter_keywords: list[str] = []

        for concept_id in entity_refs:
            concept = self.ontology_store.lookup_concept(concept_id)
            if not concept:
                continue

            # Source 1: Check filter_keywords from ontology concept properties
            filter_keywords = concept.properties.get("filter_keywords", [])
            for kw in filter_keywords:
                kw_lower = kw.lower()
                if kw_lower in text_lower:
                    matched_filter_keywords.append(kw_lower)

            # Source 2: Check column definitions (the primary metadata source)
            columns_def = concept.properties.get("columns", {})
            if isinstance(columns_def, dict):
                for col_name, col_meta in columns_def.items():
                    if not isinstance(col_meta, dict):
                        continue
                    col_type = col_meta.get("type", "")
                    # Skip identifiers — they're never useful for grouping
                    if col_type == "identifier":
                        continue

                    # Match column name variants against query text
                    col_lower = col_name.lower()
                    # Generate user-facing variants: is_remote → "remote", "is remote"
                    variants = [col_lower, col_lower.replace("_", " ")]
                    if col_lower.startswith("is_"):
                        variants.append(col_lower[3:])  # "remote" from "is_remote"

                    # Also check the column description for keyword matches
                    col_desc = col_meta.get("description", "").lower()

                    for variant in variants:
                        if variant and len(variant) > 2 and variant in text_lower:
                            if col_name not in matched_columns:
                                matched_columns.append(col_name)
                            break

            # Source 3: Legacy categorical_properties list
            categorical_properties = concept.properties.get("categorical_properties", [])
            for col in categorical_properties:
                col_lower = col.lower().replace("_", " ")
                col_name_raw = col.lower()
                variants = [col_lower, col_name_raw]
                if col_name_raw.startswith("is_"):
                    variants.append(col_name_raw[3:])
                for variant in variants:
                    if variant and variant in text_lower:
                        if col not in matched_columns:
                            matched_columns.append(col)
                        break

        if matched_columns:
            hints["target_columns"] = matched_columns
            # If we found categorical columns mentioned in the query,
            # suggest grouping by them for aggregation queries
            hints["group_by_hint"] = matched_columns

        if matched_filter_keywords:
            hints["matched_keywords"] = matched_filter_keywords

        return hints

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

    # Mapping from detected keywords to ontology data_source property values
    DATA_SOURCE_KEYWORD_MAP: dict[str, str] = {
        "redshift": "redshift",
        "csv": "product_catalog",
        "product catalog": "product_catalog",
        "json": "financial_data",
    }

    def _detect_data_source(self, query_text: str) -> str | None:
        text_lower = query_text.lower()
        sorted_keywords = sorted(
            self.DATA_SOURCE_KEYWORD_MAP.keys(), key=len, reverse=True
        )
        for keyword in sorted_keywords:
            if keyword in text_lower:
                return self.DATA_SOURCE_KEYWORD_MAP[keyword]
        return None

    def _resolve_entities(self, query_text: str) -> list[str]:
        """Resolve entity references in the query against the Ontology Store.

        Collects ALL matching concepts per keyword, then applies filtering
        and re-ranking before selecting the best candidate for each keyword.

        Pipeline per keyword:
        1. Retrieve all matching concepts from the ontology store
        2. Filter to data-source concepts (those with an agent_id)
        3. Apply data-source filtering if an explicit source was detected
           - If filtering removes all candidates, fall back to unfiltered set
        4. Re-rank candidates using tie-breaking rules
        5. Select the best candidate after filtering/re-ranking

        Data-source filtering behavior:
        - When user mentions "redshift", "csv", "json", or "product catalog" in query
        - Concepts without matching data_source property are filtered out
        - If no concepts remain after filtering, fall back to all data-source concepts

        Args:
            query_text: The natural language query text.

        Returns:
            List of canonical ontology concept identifiers (concept_ids).
            Empty list if no concepts match.
        """
        keywords = self._extract_keywords(query_text)
        detected_source = self._detect_data_source(query_text)
        resolved_ids: list[str] = []
        seen: set[str] = set()

        for keyword in keywords:
            concepts = self.ontology_store.search_concepts(keyword)
            if not concepts:
                continue

            # Step 1: Collect ALL candidates that are data-source concepts
            candidates = [
                c for c in concepts if c.properties.get("agent_id")
            ]
            if not candidates:
                continue

            # Step 2: Apply data-source filtering if explicit source detected
            if detected_source:
                filtered = [
                    c for c in candidates
                    if c.properties.get("data_source") == detected_source
                ]
                # Only use filtered set if it contains at least one candidate
                if filtered:
                    candidates = filtered
                else:
                    # Log fallback when filtering would remove all candidates
                    logger.debug(
                        json.dumps({
                            "service_name": "nlp_translator",
                            "operation": "resolve_entities",
                            "event": "data_source_filter_fallback",
                            "keyword": keyword,
                            "detected_source": detected_source,
                            "unfiltered_count": len(candidates),
                        })
                    )

            # Step 3: Re-rank candidates
            # Currently uses ontology store ordering (score-based).
            # Future tasks (2.3, 2.4) will add agent-aware tie-breaking
            # and default Redshift preference here.
            candidates = self._rank_candidates(candidates)

            # Step 4: Select the best candidate
            best = candidates[0]
            if best.concept_id not in seen:
                resolved_ids.append(best.concept_id)
                seen.add(best.concept_id)

        return resolved_ids

    def _rank_candidates(self, candidates: list) -> list:
        """Re-rank a list of candidate concepts after filtering.

        Implements multi-stage tie-breaking:
        1. Primary: Concepts backed by registered/active agents are preferred
        2. Secondary: Redshift-backed concepts are preferred over legacy
           JSON/CSV concepts (task 2.4)
        3. Tertiary: Preserve ontology store's original ordering (stable sort)

        Args:
            candidates: List of OntologyConcept objects, pre-sorted by
                ontology store match score.

        Returns:
            Re-ranked list of OntologyConcept objects (best first).
        """
        if not candidates:
            return candidates

        # Get the base score from the first candidate (all should have same score
        # when we're doing tie-breaking)
        base_score = candidates[0].properties.get("score", 0)

        # Group candidates by their base score to identify ties
        score_groups: dict[int | float, list] = {}
        for candidate in candidates:
            score = candidate.properties.get("score", 0)
            if score not in score_groups:
                score_groups[score] = []
            score_groups[score].append(candidate)

        # If there's only one group (all candidates have same score), apply tie-breaking
        if len(score_groups) == 1:
            # Apply agent-aware tie-breaking
            return self._apply_agent_aware_tie_breaking(candidates)

        # Multiple scores - return candidates sorted by score (descending)
        # and apply agent-aware tie-breaking within each score group
        sorted_groups = sorted(score_groups.items(), key=lambda x: x[0], reverse=True)
        result = []
        for score, group in sorted_groups:
            result.extend(self._apply_agent_aware_tie_breaking(group))
        return result

    def _apply_agent_aware_tie_breaking(self, candidates: list) -> list:
        """Apply agent-aware tie-breaking to a list of candidates.

        Prefer concepts whose agent_id matches a currently registered agent.
        Among registered agents, prefer Redshift-backed concepts over legacy
        JSON/CSV concepts.

        Args:
            candidates: List of OntologyConcept objects (all with same base score).

        Returns:
            Re-ranked list with registered agents first, then Redshift preference.
        """
        if not candidates:
            return candidates

        registered_ids = self._registered_agent_ids

        # Score each candidate: lower = better
        def candidate_rank(c):
            """Calculate rank score for a candidate.
            
            Priority:
            1. Registered agent (rank 0) vs unregistered (rank 1)
            2. Redshift data source (rank 0) vs legacy (rank 1)
            3. Original position (to maintain stable sorting)
            """
            agent_id = c.properties.get("agent_id", "")
            data_source = c.properties.get("data_source", "")
            
            is_registered = 0 if agent_id in registered_ids else 1
            is_redshift = 0 if data_source == "redshift" else 1
            
            return (is_registered, is_redshift)

        # Sort by rank score, then preserve original order for ties (stable sort)
        return sorted(candidates, key=candidate_rank)

    def update_registered_agents(self, agent_ids: list[str]) -> None:
        """Update the list of registered agent IDs for tie-breaking.

        Call this when the orchestrator's agent registry changes to ensure
        entity resolution always has the latest agent availability.

        Args:
            agent_ids: List of currently registered agent IDs.
        """
        self._registered_agent_ids = set(agent_ids)
        logger.debug(
            json.dumps({
                "service_name": "nlp_translator",
                "operation": "update_registered_agents",
                "event": "agent_registry_updated",
                "agent_count": len(agent_ids),
            })
        )

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
            "transactions", "transaction", "segments", "segment", "customer",
            "customers", "employee", "employees", "performance", "department",
            "departments", "satisfaction", "deals", "targets", "lifetime",
            "shipments", "payment", "remote", "in-office", "escalation",
            "escalated", "resolution", "tickets", "ticket", "campaign",
            "campaigns", "marketing", "workforce", "salary", "salaries",
            "utilization", "engagement", "training", "certifications",
            "budget", "spend", "impressions", "clicks", "conversions",
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
