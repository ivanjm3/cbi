#!/usr/bin/env python
"""Upload initial data files to S3 bucket for the Ontology NLP Query System.

Uploads:
  - data/ontology/enterprise_ontology.json → s3://visualization-poc-bucket/ontology/
  - data/guardrail_rules.json → s3://visualization-poc-bucket/config/
  - data/sources/financial_data.json → s3://visualization-poc-bucket/data-sources/
  - data/sources/product_catalog.csv → s3://visualization-poc-bucket/data-sources/

Usage:
    python scripts/setup_s3.py
"""

import json
from pathlib import Path

from src.config import (
    AWS_PROFILE,
    S3_BUCKET,
    S3_DATA_SOURCES_PREFIX,
    S3_GUARDRAIL_RULES_KEY,
    S3_ONTOLOGY_PREFIX,
)


def get_s3_client_no_verify():
    """Get an S3 client matching the app's configuration.
    
    Uses explicit regional endpoint and disabled SSL verification
    to work behind corporate proxies.
    """
    import boto3
    session = boto3.Session(profile_name=AWS_PROFILE)
    return session.client(
        "s3",
        region_name="us-east-1",
        endpoint_url="https://s3.us-east-1.amazonaws.com",
        verify=False,
    )


def main():
    s3 = get_s3_client_no_verify()
    print(f"Uploading to S3 bucket: {S3_BUCKET}")
    print("=" * 60)

    uploads = [
        {
            "local": "data/ontology/enterprise_ontology.json",
            "s3_key": f"{S3_ONTOLOGY_PREFIX}enterprise_ontology.json",
            "content_type": "application/json",
        },
        {
            "local": "data/guardrail_rules.json",
            "s3_key": S3_GUARDRAIL_RULES_KEY,
            "content_type": "application/json",
        },
        {
            "local": "data/sources/financial_data.json",
            "s3_key": f"{S3_DATA_SOURCES_PREFIX}financial_data.json",
            "content_type": "application/json",
        },
        {
            "local": "data/sources/product_catalog.csv",
            "s3_key": f"{S3_DATA_SOURCES_PREFIX}product_catalog.csv",
            "content_type": "text/csv",
        },
    ]

    for upload in uploads:
        local_path = Path(upload["local"])
        if not local_path.exists():
            print(f"  [SKIP] {upload['local']} (file not found)")
            continue

        try:
            s3.put_object(
                Bucket=S3_BUCKET,
                Key=upload["s3_key"],
                Body=local_path.read_bytes(),
                ContentType=upload["content_type"],
            )
            print(f"  [OK] {upload['local']} -> s3://{S3_BUCKET}/{upload['s3_key']}")
        except Exception as e:
            print(f"  [FAILED] {upload['local']}: {e}")

    print()
    print("=" * 60)
    print("S3 setup complete!")
    print()
    print("Bucket structure:")
    print(f"  s3://{S3_BUCKET}/ontology/         - Ontology definitions")
    print(f"  s3://{S3_BUCKET}/history/          - Query history records")
    print(f"  s3://{S3_BUCKET}/config/           - Guardrail rules")
    print(f"  s3://{S3_BUCKET}/data-sources/     - Spoke agent data files")


if __name__ == "__main__":
    main()
