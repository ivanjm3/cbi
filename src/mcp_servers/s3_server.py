"""S3 MCP Server — Exposes S3-backed datasets as MCP tools and resources.

Tools:
  - list_datasets: Discover available CSV/JSON files in the data-sources prefix
  - read_dataset: Read the content of a CSV or JSON dataset
  - get_schema: Retrieve column names, types, and sample values for a dataset

Resources:
  - s3://{bucket}/data-sources/{filename}/schema — file schema as read-only context

Runs via stdio transport for local MCP client integration.
"""

import csv
import io
import json
import logging
from typing import Any

from fastmcp import FastMCP

from src.config import S3_BUCKET, S3_DATA_SOURCES_PREFIX, get_s3_client

logger = logging.getLogger(__name__)

mcp = FastMCP(name="S3 Data Server")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
def list_datasets() -> list[dict[str, Any]]:
    """Discover available data files in S3.

    Returns a list of dataset objects with key, size, and last modified date
    for all CSV and JSON files in the data-sources prefix.
    """
    s3 = get_s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    datasets: list[dict[str, Any]] = []

    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_DATA_SOURCES_PREFIX):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".csv") or key.endswith(".json"):
                datasets.append({
                    "key": key,
                    "filename": key.split("/")[-1],
                    "size_bytes": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "format": "csv" if key.endswith(".csv") else "json",
                })

    return datasets


@mcp.tool
def read_dataset(filename: str, limit: int = 100) -> dict[str, Any]:
    """Read the contents of a CSV or JSON dataset from S3.

    Args:
        filename: The filename (e.g. 'financial_data.json' or 'product_catalog.csv').
                  Will be resolved under the data-sources/ prefix.
        limit: Maximum number of rows to return (default 100). Use 0 for all rows.

    Returns:
        Dictionary with format, columns, rows, and total row count.
    """
    s3 = get_s3_client()
    key = f"{S3_DATA_SOURCES_PREFIX}{filename}"

    response = s3.get_object(Bucket=S3_BUCKET, Key=key)
    content = response["Body"].read().decode("utf-8")

    if filename.endswith(".json"):
        data = json.loads(content)
        rows = data.get("rows", data if isinstance(data, list) else [data])
        columns = data.get("columns", list(rows[0].keys()) if rows else [])
        total = len(rows)
        if limit > 0:
            rows = rows[:limit]
        return {
            "format": "json",
            "filename": filename,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "total_rows": total,
        }

    elif filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content))
        columns = list(reader.fieldnames or [])
        rows: list[dict[str, str]] = []
        total = 0
        for row in reader:
            total += 1
            if limit == 0 or len(rows) < limit:
                rows.append(dict(row))
        return {
            "format": "csv",
            "filename": filename,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "total_rows": total,
        }

    else:
        return {"error": f"Unsupported file format for '{filename}'. Use .csv or .json files."}


@mcp.tool
def get_schema(filename: str) -> dict[str, Any]:
    """Get the schema (column names, inferred types, sample values) for a dataset.

    Reads the first few rows to infer column types and provide representative
    sample values for each column.

    Args:
        filename: The dataset filename (e.g. 'product_catalog.csv').

    Returns:
        Dictionary with filename, format, columns (name, inferred_type, samples).
    """
    s3 = get_s3_client()
    key = f"{S3_DATA_SOURCES_PREFIX}{filename}"

    response = s3.get_object(Bucket=S3_BUCKET, Key=key)
    content = response["Body"].read().decode("utf-8")

    if filename.endswith(".json"):
        data = json.loads(content)
        rows = data.get("rows", data if isinstance(data, list) else [data])
        columns = data.get("columns", list(rows[0].keys()) if rows else [])
        sample_rows = rows[:5]
    elif filename.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(content))
        columns = list(reader.fieldnames or [])
        sample_rows = []
        for i, row in enumerate(reader):
            if i >= 5:
                break
            sample_rows.append(dict(row))
    else:
        return {"error": f"Unsupported format: {filename}"}

    # Infer column types from sample data
    schema_columns: list[dict[str, Any]] = []
    for col in columns:
        values = [row.get(col) for row in sample_rows if row.get(col) is not None]
        inferred_type = _infer_type(values)
        samples = [str(v) for v in values[:3]]
        schema_columns.append({
            "name": col,
            "inferred_type": inferred_type,
            "sample_values": samples,
            "nullable": any(row.get(col) is None or row.get(col) == "" for row in sample_rows),
        })

    return {
        "filename": filename,
        "format": "csv" if filename.endswith(".csv") else "json",
        "column_count": len(columns),
        "columns": schema_columns,
        "sample_row_count": len(sample_rows),
    }


# ---------------------------------------------------------------------------
# Resources — Injected as read-only context before tool calls
# ---------------------------------------------------------------------------


@mcp.resource("s3://{filename}/schema")
def dataset_schema_resource(filename: str) -> dict[str, Any]:
    """Schema resource for a dataset file.

    Exposes file schema as a read-only resource that can be injected as
    context before the LLM decides which tools to call.
    URI pattern: s3://{filename}/schema
    """
    return get_schema(filename)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_type(values: list[Any]) -> str:
    """Infer column type from a list of sample values."""
    if not values:
        return "unknown"

    numeric_count = 0
    int_count = 0
    bool_count = 0

    for v in values:
        if isinstance(v, bool):
            bool_count += 1
            continue
        if isinstance(v, (int, float)):
            numeric_count += 1
            if isinstance(v, int):
                int_count += 1
            continue
        # String values — try parsing
        sv = str(v).strip()
        if sv.lower() in ("true", "false"):
            bool_count += 1
        else:
            try:
                int(sv)
                numeric_count += 1
                int_count += 1
            except ValueError:
                try:
                    float(sv)
                    numeric_count += 1
                except ValueError:
                    pass

    total = len(values)
    if bool_count == total:
        return "boolean"
    if numeric_count == total:
        return "integer" if int_count == total else "number"
    if numeric_count > 0:
        return "mixed (string/number)"
    return "string"


if __name__ == "__main__":
    from src.config import MCP_S3_PORT
    mcp.run(transport="streamable-http", host="0.0.0.0", port=MCP_S3_PORT, path="/mcp")
