"""Query History Store backed by S3.

Persists past queries and resolved intents to S3 as JSON objects.
Embeddings are stored as float lists within each record.
Similarity search loads embeddings into memory and computes cosine
similarity with numpy.

S3 structure:
  s3://visualization-poc-bucket/history/{record_id}.json

Each record contains:
  - record_id, query_text, structured_intent, embedding (list[float])
  - created_at, user_id, expires_at

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from botocore.exceptions import ClientError

from src.config import (
    AWS_PROFILE,
    EMBEDDINGS_MODEL_ID,
    S3_BUCKET,
    S3_HISTORY_PREFIX,
    get_s3_client,
)
from src.models.shared import StructuredIntent

logger = logging.getLogger(__name__)


@dataclass
class HistoryMatch:
    """A matching history record with similarity score."""

    intent: StructuredIntent
    similarity_score: float
    original_query: str
    timestamp: datetime


class EmbeddingGenerator:
    """Generates text embeddings using Amazon Bedrock Titan Embeddings V2."""

    def __init__(self, model_id: str = EMBEDDINGS_MODEL_ID):
        """Initialize with the Bedrock model identifier."""
        self.model_id = model_id
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazily initialize the Bedrock runtime client."""
        if self._client is None:
            from src.config import get_bedrock_client
            self._client = get_bedrock_client()
        return self._client

    def generate(self, text: str) -> list[float] | None:
        """Generate an embedding vector for the given text.

        Args:
            text: The text to embed.

        Returns:
            List of floats representing the embedding, or None on failure.
        """
        try:
            client = self._get_client()
            body = json.dumps({"inputText": text})
            response = client.invoke_model(
                modelId=self.model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            response_body = json.loads(response["body"].read())
            embedding = response_body.get("embedding")

            # Track embedding generation cost
            try:
                from src.services.cost_tracker import get_cost_tracker
                # Titan Embeddings: input tokens only (no output tokens billed)
                # Estimate ~1 token per 4 chars for input text
                estimated_input_tokens = max(1, len(text) // 4)
                get_cost_tracker().log_invocation(
                    model_id=self.model_id,
                    component="query_history_embeddings",
                    input_tokens=estimated_input_tokens,
                    output_tokens=0,
                    metadata={"source": "estimated", "text_length": len(text)},
                )
            except Exception:
                pass  # Don't let cost tracking break embedding generation

            return embedding
        except Exception as e:
            logger.error(
                json.dumps({
                    "service_name": "query_history_store",
                    "operation": "generate_embedding",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                })
            )
            return None


class QueryHistoryStore:
    """S3-backed store for query history with embedding similarity search.

    Each history record is stored as a JSON file in S3 at:
        s3://{bucket}/history/{record_id}.json

    Similarity search loads all embeddings into memory and computes
    cosine similarity with numpy. Suitable for development and POC
    workloads (up to thousands of records).
    """

    def __init__(
        self,
        embedding_generator: EmbeddingGenerator | None = None,
        bucket: str = S3_BUCKET,
        prefix: str = S3_HISTORY_PREFIX,
    ):
        """Initialize the query history store.

        Args:
            embedding_generator: Generator for text embeddings.
                Defaults to Bedrock Titan Embeddings V2.
            bucket: S3 bucket name.
            prefix: S3 key prefix for history records.
        """
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
        self.bucket = bucket
        self.prefix = prefix
        self._s3 = get_s3_client()

    def persist(
        self,
        query_text: str,
        intent: StructuredIntent,
        user_id: str = "anonymous",
    ) -> str | None:
        """Persist a query and its resolved intent to S3.

        Generates an embedding for the query text and stores the full
        record as a JSON object in S3.

        Args:
            query_text: The original natural language query.
            intent: The resolved structured intent.
            user_id: The user who made the query.

        Returns:
            The record_id on success, None on failure.
        """
        embedding = self.embedding_generator.generate(query_text)
        if embedding is None:
            logger.warning("Failed to generate embedding, persisting without it")
            embedding = []

        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        record = {
            "record_id": record_id,
            "query_text": query_text,
            "structured_intent": intent.model_dump(mode="json"),
            "embedding": embedding,
            "created_at": now.isoformat(),
            "user_id": user_id,
        }

        try:
            key = f"{self.prefix}{record_id}.json"
            self._s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(record),
                ContentType="application/json",
            )
            return record_id
        except Exception as e:
            logger.error(
                json.dumps({
                    "service_name": "query_history_store",
                    "operation": "persist",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                })
            )
            return None

    def find_similar(
        self, query_text: str, threshold: float = 0.85
    ) -> list[HistoryMatch]:
        """Find historically similar queries by embedding cosine similarity.

        Generates an embedding for the query, loads all stored embeddings
        from S3, and returns matches with similarity >= threshold.

        Args:
            query_text: The query to find similar past queries for.
            threshold: Minimum cosine similarity (0-1). Default 0.85.

        Returns:
            List of HistoryMatch objects sorted by similarity (descending).
            Empty list on failure or no matches.
        """
        query_embedding = self.embedding_generator.generate(query_text)
        if query_embedding is None:
            return []

        query_vec = np.array(query_embedding)

        # Load all history records from S3
        records = self._load_all_records()
        if not records:
            return []

        matches: list[HistoryMatch] = []

        for record in records:
            stored_embedding = record.get("embedding", [])
            if not stored_embedding:
                continue

            stored_vec = np.array(stored_embedding)

            # Compute cosine similarity
            similarity = self._cosine_similarity(query_vec, stored_vec)

            if similarity >= threshold:
                try:
                    intent = StructuredIntent.model_validate(
                        record["structured_intent"]
                    )
                    matches.append(
                        HistoryMatch(
                            intent=intent,
                            similarity_score=float(similarity),
                            original_query=record["query_text"],
                            timestamp=datetime.fromisoformat(record["created_at"]),
                        )
                    )
                except Exception:
                    continue

        # Sort by similarity descending
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        return matches

    def expire_old_records(self, retention_days: int) -> int:
        """Delete history records older than the retention period.

        Args:
            retention_days: Records older than this many days are deleted.

        Returns:
            Number of records deleted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        records = self._load_all_records()
        deleted = 0

        for record in records:
            try:
                created = datetime.fromisoformat(record["created_at"])
                if created < cutoff:
                    key = f"{self.prefix}{record['record_id']}.json"
                    self._s3.delete_object(Bucket=self.bucket, Key=key)
                    deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete record: {e}")

        return deleted

    def _load_all_records(self) -> list[dict]:
        """Load all history records from S3.

        Returns:
            List of record dicts.
        """
        records: list[dict] = []
        try:
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=self.prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    if key.endswith(".json"):
                        try:
                            response = self._s3.get_object(
                                Bucket=self.bucket, Key=key
                            )
                            body = response["Body"].read().decode("utf-8")
                            record = json.loads(body)
                            records.append(record)
                        except Exception as e:
                            logger.warning(f"Failed to read {key}: {e}")
        except Exception as e:
            logger.error(
                json.dumps({
                    "service_name": "query_history_store",
                    "operation": "load_all_records",
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                })
            )
        return records

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            a: First vector.
            b: Second vector.

        Returns:
            Cosine similarity (0-1).
        """
        if a.shape != b.shape:
            return 0.0
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
