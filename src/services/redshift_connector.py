"""Redshift Connector for executing SQL via the AWS Redshift Data API.

Manages SQL statement execution against Amazon Redshift using the boto3
redshift-data client. Handles polling for statement completion, result
retrieval, error classification, and connectivity validation.
"""

import asyncio
import logging
import time

from botocore.exceptions import ClientError

from src.config import RedshiftConfig, get_redshift_data_client
from src.models.redshift_models import RedshiftError, RedshiftResult

logger = logging.getLogger(__name__)

# Polling configuration
POLL_INTERVAL_MIN_MS = 500
POLL_INTERVAL_MAX_MS = 2000
POLL_TIMEOUT_SECONDS = 30

# Terminal states for statement execution
_TERMINAL_STATES = {"FINISHED", "FAILED", "ABORTED"}
_PENDING_STATES = {"SUBMITTED", "PICKED", "STARTED"}


class RedshiftConnector:
    """Executes SQL against Redshift via the Data API with polling.

    Uses the boto3 redshift-data client to submit SQL statements,
    poll for completion, and retrieve result sets. All operations are
    async-friendly and classify errors into standard error types.
    """

    def __init__(self, config: RedshiftConfig | None = None) -> None:
        """Initialize with cluster config from env vars.

        Args:
            config: Optional RedshiftConfig. If not provided, loads from
                    environment variables with defaults.
        """
        self._config = config or RedshiftConfig.from_env()
        self._client = get_redshift_data_client()

    async def execute_statement(
        self, sql: str, parameters: list[dict] | None = None
    ) -> RedshiftResult | RedshiftError:
        """Submit SQL, poll for completion, return results.

        Executes a SQL statement against the configured Redshift cluster,
        polls for completion within the timeout window, and retrieves the
        result set on success.

        Args:
            sql: The SQL statement to execute.
            parameters: Optional list of named parameters for parameterized queries.
                        Each dict should have 'name' and 'value' keys.

        Returns:
            RedshiftResult on success, or RedshiftError on failure.
        """
        try:
            # Build execute_statement kwargs
            kwargs: dict = {
                "ClusterIdentifier": self._config.cluster_id,
                "Database": self._config.database,
                "DbUser": self._config.db_user,
                "Sql": sql,
            }
            if parameters:
                kwargs["Parameters"] = [
                    {"name": p["name"], "value": str(p["value"])}
                    for p in parameters
                ]

            # Submit the statement
            response = await asyncio.to_thread(
                self._client.execute_statement, **kwargs
            )
            statement_id = response["Id"]
            logger.debug("Submitted statement %s", statement_id)

        except ClientError as e:
            return self._classify_client_error(e)
        except Exception as e:
            return RedshiftError(
                error_type="CONNECTION_ERROR",
                description=f"Failed to submit statement: {e}",
            )

        # Poll for completion
        poll_result = await self._poll_statement(statement_id)
        if isinstance(poll_result, RedshiftError):
            return poll_result

        # Check if statement has a result set (DDL statements don't)
        try:
            desc = await asyncio.to_thread(
                self._client.describe_statement, Id=statement_id
            )
            has_result_set = desc.get("HasResultSet", False)
        except Exception:
            has_result_set = False

        if not has_result_set:
            # DDL or INSERT — no result set to fetch
            return RedshiftResult(
                columns=[],
                rows=[],
                row_count=0,
                statement_id=statement_id,
            )

        # Statement completed — retrieve results
        return await self._get_result_set(statement_id)

    async def validate_connectivity(self) -> bool:
        """Test connectivity by executing a simple query.

        Returns:
            True if the connectivity check succeeds, False otherwise.
        """
        result = await self.execute_statement("SELECT 1")
        if isinstance(result, RedshiftError):
            logger.warning(
                "Redshift connectivity check failed: %s - %s",
                result.error_type,
                result.description,
            )
            return False
        return True

    async def _poll_statement(self, statement_id: str) -> str | RedshiftError:
        """Poll statement status at 500ms-2s intervals, max 30s.

        Uses exponential backoff starting at 500ms, capping at 2s per interval.
        If the total elapsed time exceeds 30 seconds, cancels the statement
        and returns a TIMEOUT error.

        Args:
            statement_id: The Redshift Data API statement identifier.

        Returns:
            The terminal status string on success, or RedshiftError on
            timeout or failure.
        """
        start_time = time.monotonic()
        poll_interval_s = POLL_INTERVAL_MIN_MS / 1000.0

        while True:
            elapsed = time.monotonic() - start_time

            if elapsed >= POLL_TIMEOUT_SECONDS:
                # Cancel the statement and return timeout error
                try:
                    await asyncio.to_thread(
                        self._client.cancel_statement, Id=statement_id
                    )
                    logger.warning(
                        "Cancelled statement %s after %.1fs timeout",
                        statement_id,
                        elapsed,
                    )
                except Exception as cancel_err:
                    logger.error(
                        "Failed to cancel statement %s: %s",
                        statement_id,
                        cancel_err,
                    )
                return RedshiftError(
                    error_type="TIMEOUT",
                    description=(
                        f"Statement {statement_id} exceeded {POLL_TIMEOUT_SECONDS}s timeout"
                    ),
                    elapsed_seconds=elapsed,
                )

            # Check statement status
            try:
                desc = await asyncio.to_thread(
                    self._client.describe_statement, Id=statement_id
                )
            except ClientError as e:
                return self._classify_client_error(e)
            except Exception as e:
                return RedshiftError(
                    error_type="CONNECTION_ERROR",
                    description=f"Failed to describe statement {statement_id}: {e}",
                )

            status = desc.get("Status", "")

            if status == "FINISHED":
                return status

            if status == "FAILED":
                error_msg = desc.get("Error", "Unknown execution error")
                return RedshiftError(
                    error_type="QUERY_FAILURE",
                    description=error_msg,
                    elapsed_seconds=time.monotonic() - start_time,
                )

            if status == "ABORTED":
                return RedshiftError(
                    error_type="QUERY_FAILURE",
                    description=f"Statement {statement_id} was aborted",
                    elapsed_seconds=time.monotonic() - start_time,
                )

            # Still pending — wait before next poll
            await asyncio.sleep(poll_interval_s)

            # Increase interval with exponential backoff, capped at max
            poll_interval_s = min(
                poll_interval_s * 1.5, POLL_INTERVAL_MAX_MS / 1000.0
            )

    async def _get_result_set(self, statement_id: str) -> RedshiftResult | RedshiftError:
        """Retrieve column metadata and row data for a completed statement.

        Args:
            statement_id: The Redshift Data API statement identifier for
                          a completed (FINISHED) statement.

        Returns:
            RedshiftResult with columns, rows, row_count, and statement_id.
            RedshiftError if retrieval fails.
        """
        try:
            response = await asyncio.to_thread(
                self._client.get_statement_result, Id=statement_id
            )
        except ClientError as e:
            return self._classify_client_error(e)
        except Exception as e:
            return RedshiftError(
                error_type="CONNECTION_ERROR",
                description=f"Failed to retrieve results for statement {statement_id}: {e}",
            )

        # Parse column metadata
        column_metadata = response.get("ColumnMetadata", [])
        columns = [
            {"name": col.get("name", ""), "type": col.get("typeName", "unknown")}
            for col in column_metadata
        ]

        # Parse row data — each record is a list of typed value dicts
        raw_records = response.get("Records", [])
        rows: list[list] = []
        for record in raw_records:
            row = []
            for field in record:
                # Redshift Data API returns typed fields like
                # {"stringValue": "x"}, {"longValue": 1}, {"doubleValue": 1.5}, etc.
                value = self._extract_field_value(field)
                row.append(value)
            rows.append(row)

        return RedshiftResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            statement_id=statement_id,
        )

    @staticmethod
    def _extract_field_value(field: dict):
        """Extract the typed value from a Redshift Data API field dict.

        The API returns fields as dicts with a single typed key like
        'stringValue', 'longValue', 'doubleValue', 'booleanValue', or
        'isNull'.

        Args:
            field: A single field dict from the Records response.

        Returns:
            The extracted Python value, or None for null fields.
        """
        if field.get("isNull", False):
            return None
        if "stringValue" in field:
            return field["stringValue"]
        if "longValue" in field:
            return field["longValue"]
        if "doubleValue" in field:
            return field["doubleValue"]
        if "booleanValue" in field:
            return field["booleanValue"]
        if "blobValue" in field:
            return field["blobValue"]
        # Fallback — return the first value found
        for value in field.values():
            return value
        return None

    def _classify_client_error(self, error: ClientError) -> RedshiftError:
        """Classify a botocore ClientError into the appropriate RedshiftError type.

        Maps AWS error codes to the standard error types:
        - AUTH_FAILURE: credential/permission errors
        - CONNECTION_ERROR: network/endpoint issues
        - QUERY_FAILURE: everything else

        Args:
            error: The botocore ClientError to classify.

        Returns:
            A RedshiftError with the appropriate error_type.
        """
        error_code = error.response.get("Error", {}).get("Code", "")
        error_message = error.response.get("Error", {}).get("Message", str(error))

        auth_codes = {
            "AccessDeniedException",
            "UnauthorizedOperation",
            "InvalidCredentials",
            "ExpiredTokenException",
            "InvalidIdentityToken",
            "AccessDenied",
        }
        connection_codes = {
            "EndpointConnectionError",
            "ConnectTimeoutError",
            "ConnectionClosedError",
            "NetworkError",
        }

        if error_code in auth_codes:
            return RedshiftError(
                error_type="AUTH_FAILURE",
                description=(
                    f"Authentication failed for cluster '{self._config.cluster_id}': "
                    f"{error_message}"
                ),
            )
        elif error_code in connection_codes:
            return RedshiftError(
                error_type="CONNECTION_ERROR",
                description=(
                    f"Connection failed to cluster '{self._config.cluster_id}': "
                    f"{error_message}"
                ),
            )
        else:
            return RedshiftError(
                error_type="QUERY_FAILURE",
                description=f"{error_code}: {error_message}",
            )
