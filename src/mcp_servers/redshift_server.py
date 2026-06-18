"""Redshift MCP Server — Exposes Redshift tables and queries as MCP tools and resources.

Tools:
  - get_tables: Discover available tables in the analytics database
  - get_schema: Get column definitions and types for a specific table
  - run_query: Execute a SQL query against Redshift
  - preview_table: Return sample rows from a table (helps LLM generate better SQL)
  - get_query_history: Retrieve recent query execution history for audit trails

Resources:
  - redshift://tables/{table_name}/schema — table schema as read-only context

Runs via stdio transport for local MCP client integration.
"""

import asyncio
import logging
from typing import Any

from fastmcp import FastMCP

from src.config import RedshiftConfig, get_redshift_data_client

logger = logging.getLogger(__name__)

mcp = FastMCP(name="Redshift Data Server")

# Module-level config and client
_config = RedshiftConfig.from_env()

# Query history storage (in-memory for the MCP session)
_query_history: list[dict[str, Any]] = []


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool
def get_tables() -> list[dict[str, Any]]:
    """Discover available tables in the Redshift analytics database.

    Queries the information_schema to list all user-created tables with
    their schema, row count estimate, and description.

    Returns:
        List of table objects with schema_name, table_name, and table_type.
    """
    sql = """
        SELECT table_schema, table_name, table_type
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_internal')
        ORDER BY table_schema, table_name;
    """
    result = _execute_sync(sql)
    if "error" in result:
        return [result]

    tables = []
    for row in result.get("rows", []):
        tables.append({
            "schema_name": row[0] if len(row) > 0 else None,
            "table_name": row[1] if len(row) > 1 else None,
            "table_type": row[2] if len(row) > 2 else None,
        })
    return tables


@mcp.tool
def get_schema(table_name: str, schema_name: str = "public") -> dict[str, Any]:
    """Get the column definitions and data types for a Redshift table.

    Args:
        table_name: The table name to inspect.
        schema_name: The schema name (default: 'public').

    Returns:
        Dictionary with table_name, schema, and list of column definitions
        including name, data_type, is_nullable, and ordinal_position.
    """
    sql = f"""
        SELECT column_name, data_type, is_nullable, ordinal_position,
               character_maximum_length, numeric_precision, numeric_scale
        FROM information_schema.columns
        WHERE table_schema = '{schema_name}'
          AND table_name = '{table_name}'
        ORDER BY ordinal_position;
    """
    result = _execute_sync(sql)
    if "error" in result:
        return result

    columns = []
    for row in result.get("rows", []):
        col_def: dict[str, Any] = {
            "column_name": row[0] if len(row) > 0 else None,
            "data_type": row[1] if len(row) > 1 else None,
            "is_nullable": row[2] if len(row) > 2 else None,
            "ordinal_position": row[3] if len(row) > 3 else None,
        }
        if row[4]:  # character_maximum_length
            col_def["max_length"] = row[4]
        if row[5]:  # numeric_precision
            col_def["precision"] = row[5]
            col_def["scale"] = row[6]
        columns.append(col_def)

    return {
        "table_name": table_name,
        "schema_name": schema_name,
        "column_count": len(columns),
        "columns": columns,
    }


@mcp.tool
def run_query(sql: str) -> dict[str, Any]:
    """Execute a SQL query against the Redshift analytics database.

    Supports SELECT, and DDL/DML statements. Results are returned with
    column metadata and row data.

    Args:
        sql: The SQL statement to execute. Must be a valid Redshift SQL query.

    Returns:
        Dictionary with columns, rows, row_count, and statement_id on success,
        or error information on failure.
    """
    result = _execute_sync(sql)

    # Track in query history
    _query_history.append({
        "sql": sql,
        "success": "error" not in result,
        "row_count": result.get("row_count", 0),
        "statement_id": result.get("statement_id", None),
    })

    return result


@mcp.tool
def preview_table(table_name: str, limit: int = 10, schema_name: str = "public") -> dict[str, Any]:
    """Return sample rows from a Redshift table.

    Useful for understanding the data shape and content before writing
    more complex queries. Returns both schema info and sample data.

    Args:
        table_name: The table to preview.
        limit: Number of sample rows to return (default 10, max 100).
        schema_name: The schema name (default: 'public').

    Returns:
        Dictionary with table info, column metadata, and sample rows.
    """
    limit = min(max(limit, 1), 100)
    sql = f'SELECT * FROM "{schema_name}"."{table_name}" LIMIT {limit};'
    result = _execute_sync(sql)

    if "error" in result:
        return result

    return {
        "table_name": table_name,
        "schema_name": schema_name,
        "preview_rows": limit,
        "columns": result.get("columns", []),
        "rows": result.get("rows", []),
        "row_count": result.get("row_count", 0),
    }


@mcp.tool
def get_query_history(limit: int = 20) -> list[dict[str, Any]]:
    """Retrieve recent query execution history for this session.

    Useful for BI audit trails and understanding what queries have been
    run during the current session.

    Args:
        limit: Maximum number of history entries to return (default 20).

    Returns:
        List of query history entries with sql, success status, and row count.
    """
    return _query_history[-limit:]


# ---------------------------------------------------------------------------
# Resources — Injected as read-only context before tool calls
# ---------------------------------------------------------------------------


@mcp.resource("redshift://tables/{table_name}/schema")
def table_schema_resource(table_name: str) -> dict[str, Any]:
    """Table schema resource for context injection.

    Exposes the full column definition of a Redshift table as a read-only
    resource so the LLM has schema context before deciding on queries.
    URI pattern: redshift://tables/{table_name}/schema
    """
    return get_schema(table_name)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _execute_sync(sql: str) -> dict[str, Any]:
    """Execute SQL synchronously using the Redshift Data API with polling.

    Uses the same polling pattern as the existing RedshiftConnector but
    adapted for synchronous MCP server context.
    """
    import time

    client = get_redshift_data_client()

    try:
        response = client.execute_statement(
            ClusterIdentifier=_config.cluster_id,
            Database=_config.database,
            DbUser=_config.db_user,
            Sql=sql,
        )
        statement_id = response["Id"]
    except Exception as e:
        return {"error": f"Failed to submit statement: {e}"}

    # Poll for completion (30s timeout)
    start = time.time()
    timeout = 30.0
    poll_interval = 0.5

    while True:
        elapsed = time.time() - start
        if elapsed > timeout:
            return {"error": "Query timed out after 30 seconds", "statement_id": statement_id}

        try:
            desc = client.describe_statement(Id=statement_id)
            status = desc["Status"]

            if status == "FINISHED":
                break
            elif status in ("FAILED", "ABORTED"):
                error_msg = desc.get("Error", "Unknown error")
                return {
                    "error": f"Query {status.lower()}: {error_msg}",
                    "statement_id": statement_id,
                }
            # Still running — wait and poll again
            time.sleep(min(poll_interval, max(0.1, timeout - elapsed)))
            poll_interval = min(poll_interval * 1.5, 2.0)
        except Exception as e:
            return {"error": f"Polling error: {e}", "statement_id": statement_id}

    # Retrieve results
    try:
        has_result = desc.get("HasResultSet", False)
        if not has_result:
            return {
                "message": "Statement executed successfully (no result set)",
                "statement_id": statement_id,
                "row_count": 0,
            }

        result_response = client.get_statement_result(Id=statement_id)
        columns = [
            {"name": col["name"], "type": col.get("typeName", "unknown")}
            for col in result_response.get("ColumnMetadata", [])
        ]
        rows = []
        for record in result_response.get("Records", []):
            row = []
            for field in record:
                # Redshift Data API returns typed fields
                if "stringValue" in field:
                    row.append(field["stringValue"])
                elif "longValue" in field:
                    row.append(field["longValue"])
                elif "doubleValue" in field:
                    row.append(field["doubleValue"])
                elif "booleanValue" in field:
                    row.append(field["booleanValue"])
                elif "isNull" in field and field["isNull"]:
                    row.append(None)
                else:
                    row.append(str(field))
            rows.append(row)

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "statement_id": statement_id,
        }
    except Exception as e:
        return {"error": f"Failed to retrieve results: {e}", "statement_id": statement_id}


if __name__ == "__main__":
    from src.config import MCP_REDSHIFT_PORT
    mcp.run(transport="streamable-http", host="0.0.0.0", port=MCP_REDSHIFT_PORT, path="/mcp")
