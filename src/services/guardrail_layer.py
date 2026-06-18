"""Guardrail Layer with Bedrock Guardrails only.

Validates every merged response from the Orchestrator Hub using:
1. Schema validation (structural correctness)
2. Amazon Bedrock Guardrails (ML-based content filtering with source=OUTPUT)

On Bedrock unavailability: fail open (allow content, log structured warning).

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 10.1
"""

import hashlib
import json
import logging
from typing import Any

from botocore.exceptions import ClientError

from src.config import DEFAULT_MODEL_ID
from src.models.shared import (
    GuardrailResult,
    OrchestratorResponse,
    StructuredIntent,
)
from src.services.lru_cache import LRUCache

logger = logging.getLogger(__name__)


class GuardrailLayer:
    """Validates orchestrator responses against schemas and Bedrock Guardrails.

    Uses a streamlined approach:
    1. Schema validation (structural correctness)
    2. Amazon Bedrock Guardrails with source=OUTPUT (ML-based content filtering)

    On Bedrock unavailability: fail open (allow content, log structured warning).
    """

    def __init__(
        self,
        bedrock_guardrail_id: str | None = None,
        bedrock_guardrail_version: str = "DRAFT",
    ):
        """Initialize the guardrail layer.

        Args:
            bedrock_guardrail_id: The Bedrock Guardrail ID. If None, Bedrock
                Guardrails are skipped and content passes through.
            bedrock_guardrail_version: The guardrail version (default "DRAFT").
        """
        self._bedrock_guardrail_id = bedrock_guardrail_id
        self._bedrock_guardrail_version = bedrock_guardrail_version
        self._bedrock_client: Any = None
        self._guardrail_cache: LRUCache[str, GuardrailResult] = LRUCache(max_size=500)

    async def validate(
        self, response: OrchestratorResponse, intent: StructuredIntent
    ) -> GuardrailResult:
        """Validate an orchestrator response against schemas and Bedrock Guardrails.

        Evaluation order:
        1. Schema validation (structural correctness)
        2. Bedrock Guardrails (ML-based content filtering with source=OUTPUT)

        On Bedrock unavailability: fail open (allow content, log warning).

        Args:
            response: The merged response from the Orchestrator Hub.
            intent: The original structured intent for context.

        Returns:
            GuardrailResult indicating pass, rejection, or error.
        """
        try:
            # Step 1: Schema validation
            schema_error = self._validate_schema(response, intent)
            if schema_error:
                return GuardrailResult(
                    status="rejected",
                    validated_response=None,
                    applied_rules=[],
                    error_details=schema_error,
                )

            # Step 2: Check guardrail cache
            content_hash = self._compute_content_hash(response)
            cached = self._guardrail_cache.get(content_hash)
            if cached is not None:
                return cached

            # Step 3: Bedrock Guardrails (OUTPUT)
            bedrock_result = self._evaluate_bedrock_guardrails(response)
            if bedrock_result and bedrock_result["action"] == "BLOCKED":
                result = GuardrailResult(
                    status="rejected",
                    validated_response=None,
                    applied_rules=bedrock_result.get("triggered_policies", []),
                    error_details=(
                        f"Blocked by Bedrock Guardrails: "
                        f"{bedrock_result.get('reason', 'Content policy violation')}"
                    ),
                )
                self._guardrail_cache.put(content_hash, result)
                return result

            # All clear — response passes
            result = GuardrailResult(
                status="passed",
                validated_response=response,
                applied_rules=[],
                error_details=None,
            )
            self._guardrail_cache.put(content_hash, result)
            return result

        except Exception as e:
            logger.error(f"Guardrail internal error: {e}")
            return GuardrailResult(
                status="error",
                validated_response=None,
                applied_rules=[],
                error_details=f"Internal guardrail error: {type(e).__name__}: {e}",
            )

    def _get_bedrock_client(self):
        """Lazily initialize the Bedrock runtime client."""
        if self._bedrock_client is None:
            from src.config import get_bedrock_client
            self._bedrock_client = get_bedrock_client()
        return self._bedrock_client

    def _evaluate_bedrock_guardrails(
        self, response: OrchestratorResponse
    ) -> dict[str, Any] | None:
        """Evaluate response content against Amazon Bedrock Guardrails.

        Uses the ApplyGuardrail API to check content against configured
        guardrail policies (hate, violence, sexual, insults, misconduct, PII).

        Args:
            response: The orchestrator response to check.

        Returns:
            Dict with action and details if blocked, None if passed or not configured.
        """
        if not self._bedrock_guardrail_id:
            return None  # No guardrail configured, skip

        content_text = self._extract_text_content(response)
        if not content_text.strip():
            return None

        try:
            client = self._get_bedrock_client()
            result = client.apply_guardrail(
                guardrailIdentifier=self._bedrock_guardrail_id,
                guardrailVersion=self._bedrock_guardrail_version,
                source="OUTPUT",
                content=[{"text": {"text": content_text}}],
            )



            action = result.get("action", "NONE")

            if action == "GUARDRAIL_INTERVENED":
                # Content was blocked
                outputs = result.get("outputs", [])
                assessments = result.get("assessments", [])
                triggered_policies = []

                for assessment in assessments:
                    for policy_type, policy_data in assessment.items():
                        if isinstance(policy_data, list):
                            for item in policy_data:
                                if item.get("action") == "BLOCKED":
                                    triggered_policies.append(
                                        f"{policy_type}:{item.get('type', 'unknown')}"
                                    )

                return {
                    "action": "BLOCKED",
                    "reason": outputs[0].get("text", "Content blocked") if outputs else "Content policy violation",
                    "triggered_policies": triggered_policies,
                }

            # Content passed
            return None

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            logger.warning(
                json.dumps({
                    "service_name": "guardrail_layer",
                    "operation": "evaluate_bedrock_guardrails",
                    "event": "bedrock_guardrail_error",
                    "error_code": error_code,
                    "error_message": str(e),
                })
            )
            # Fail open — if Bedrock Guardrails are unavailable, fall through to local rules
            return None
        except Exception as e:
            logger.warning(f"Bedrock Guardrails check failed: {e}")
            return None

    def _validate_schema(
        self, response: OrchestratorResponse, intent: StructuredIntent
    ) -> str | None:
        """Validate response against the expected schema for the query type.

        Args:
            response: The orchestrator response to validate.
            intent: The structured intent with query_type context.

        Returns:
            Error string if validation fails, None if valid.
        """
        # Validate basic structure
        if not response.results and not response.unavailable_agents:
            return "Response contains no results and no unavailable agents."

        # Validate each agent result has required fields
        for result in response.results:
            if result.status == "success" and result.payload is None:
                return (
                    f"Agent {result.agent_id} reports success but has no payload."
                )
            if result.status == "error" and not result.error_type:
                return (
                    f"Agent {result.agent_id} reports error but has no error_type."
                )

        return None

    def _extract_text_content(self, response: OrchestratorResponse) -> str:
        """Extract all text content from a response for guardrail evaluation.

        Args:
            response: The orchestrator response.

        Returns:
            Combined text content from all agent results.
        """
        parts: list[str] = []
        for result in response.results:
            if result.payload:
                parts.append(json.dumps(result.payload))
            if result.error_description:
                parts.append(result.error_description)
        return " ".join(parts)

    def _compute_content_hash(self, response: OrchestratorResponse) -> str:
        """Compute a deterministic SHA-256 hash of the response content.

        Uses deterministic JSON serialization (sort_keys=True) to ensure
        identical content always produces the same hash.

        Args:
            response: The orchestrator response to hash.

        Returns:
            Hex digest string for use as cache key.
        """
        serialized = json.dumps(
            response.model_dump(mode="json"), sort_keys=True
        )
        return hashlib.sha256(serialized.encode()).hexdigest()
