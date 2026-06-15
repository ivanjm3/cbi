"""Shared configuration module for the Ontology NLP Query System.

Defines port assignments and shared constants used across all services.
All persistent storage uses S3 (no local SQLite or flat files).
"""

import os
import ssl
import urllib3
import boto3
from pydantic import BaseModel, Field

# Suppress SSL verification warnings (corporate proxy / self-signed certs)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Disable SSL verification for all boto3/botocore calls
# This is needed for environments with corporate proxies / self-signed certs
os.environ.setdefault("AWS_VERIFY_SSL", "false")

# Service port assignments
NLP_PORT = 8001
ORCHESTRATOR_PORT = 8002
GUARDRAIL_PORT = 8003
VIZ_PORT = 8004
AGENT_A_PORT = 8010
REDSHIFT_AGENT_PORT = 8011

# Service base URLs (localhost for Phase 1)
NLP_URL = f"http://localhost:{NLP_PORT}"
ORCHESTRATOR_URL = f"http://localhost:{ORCHESTRATOR_PORT}"
GUARDRAIL_URL = f"http://localhost:{GUARDRAIL_PORT}"
VIZ_URL = f"http://localhost:{VIZ_PORT}"
AGENT_A_URL = f"http://localhost:{AGENT_A_PORT}"
REDSHIFT_AGENT_URL = f"http://localhost:{REDSHIFT_AGENT_PORT}"

# AWS Configuration
AWS_PROFILE = os.environ.get("AWS_PROFILE", "PowerUserAccess-654654478821")
S3_BUCKET = os.environ.get("S3_BUCKET", "visualization-poc-bucket")

# S3 Key Prefixes
S3_ONTOLOGY_PREFIX = "ontology/"
S3_HISTORY_PREFIX = "history/"
S3_COSTS_PREFIX = "costs/"
S3_GUARDRAIL_RULES_KEY = "config/guardrail_rules.json"
S3_DATA_SOURCES_PREFIX = "data-sources/"

# Default timeouts (seconds)
AGENT_TIMEOUT_DEFAULT = 30
AGENT_TIMEOUT_MIN = 1
AGENT_TIMEOUT_MAX = 300

# Query History
SIMILARITY_THRESHOLD = 0.85
RETENTION_DAYS_MIN = 1
RETENTION_DAYS_MAX = 90

# Model configuration
DEFAULT_MODEL_ID = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
EMBEDDINGS_MODEL_ID = "amazon.titan-embed-text-v2:0"

# Bedrock Guardrails
BEDROCK_GUARDRAIL_ID = os.environ.get("GUARDRAIL_ID", "joes1p3j7sa4")
BEDROCK_GUARDRAIL_VERSION = os.environ.get("GUARDRAIL_VERSION", "DRAFT")


def get_boto3_session() -> boto3.Session:
    """Get a boto3 session using the configured AWS profile.

    In ECS/Lambda, uses the task role automatically (no profile needed).
    Locally, uses the configured AWS_PROFILE.

    Returns:
        A boto3.Session configured with appropriate credentials.
    """
    # In ECS, the ECS_CONTAINER_METADATA_URI env var is set — use default creds
    if os.environ.get("ECS_CONTAINER_METADATA_URI") or os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
        return boto3.Session(region_name="us-east-1")
    return boto3.Session(profile_name=AWS_PROFILE)


def get_s3_client():
    """Get an S3 client using the configured AWS profile.
    SSL verification is disabled for environments with corporate proxies
    or self-signed certificates. Uses explicit regional endpoint to avoid
    the global s3.amazonaws.com which corporate proxies may block.
    Returns:
        A boto3 S3 client.
    """
    session = get_boto3_session()
    return session.client(
        "s3",
        region_name="us-east-1",
        endpoint_url="https://s3.us-east-1.amazonaws.com",
        verify=False,
    )


def get_bedrock_client():
    """Get a Bedrock Runtime client with SSL verification disabled.

    Returns:
        A boto3 bedrock-runtime client.
    """
    session = get_boto3_session()
    return session.client("bedrock-runtime", verify=False)


def get_strands_bedrock_model(model_id: str | None = None, max_tokens: int | None = None):
    """Get a Strands BedrockModel configured with our AWS profile.

    Passes the boto session so Strands uses the correct profile credentials.

    Args:
        model_id: Override model ID. Defaults to DEFAULT_MODEL_ID.
        max_tokens: Optional max tokens limit for model output.

    Returns:
        A configured BedrockModel instance.
    """
    from strands.models import BedrockModel

    session = get_boto3_session()
    kwargs: dict = {
        "model_id": model_id or DEFAULT_MODEL_ID,
        "boto_session": session,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return BedrockModel(**kwargs)


# Redshift Configuration
class RedshiftConfig(BaseModel):
    """Configuration for the Redshift Data API connection."""

    cluster_id: str = Field(default="talktodata")
    database: str = Field(default="analytics")
    db_user: str = Field(default="admin")
    region: str = Field(default="us-east-1")

    @classmethod
    def from_env(cls) -> "RedshiftConfig":
        """Create a RedshiftConfig from environment variables with defaults."""
        return cls(
            cluster_id=os.environ.get("REDSHIFT_CLUSTER_ID", "talktodata"),
            database=os.environ.get("REDSHIFT_DATABASE", "analytics"),
            db_user=os.environ.get("REDSHIFT_DB_USER", "admin"),
            region=os.environ.get("REDSHIFT_REGION", "us-east-1"),
        )


def get_redshift_data_client():
    """Get a Redshift Data API client using the configured AWS profile.

    Returns:
        A boto3 redshift-data client.
    """
    session = get_boto3_session()
    return session.client("redshift-data", region_name="us-east-1", verify=False)
