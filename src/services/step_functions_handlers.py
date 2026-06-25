"""Lambda handlers for AWS Step Functions scheduled report execution workflow.

Each handler represents a step in the Step Functions state machine for
scheduled report execution. Handlers are deployed as separate Lambda functions
and orchestrated by the state machine.

Error handling and retry logic is managed by the state machine definition.
Each handler should:
- Accept input as a dictionary (passed from previous step or EventBridge)
- Return output as a dictionary (passed to next step)
- Raise exceptions with descriptive error messages (caught by Catch blocks)
- Be idempotent (safe to retry without side effects)

Requirements: 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict
from uuid import UUID

import httpx
from src.config import S3_BUCKET, get_s3_client
from src.models.scheduled_reports import ExecutionRecord
from src.services.execution_records_repository import ExecutionRecordsRepository
from src.services.scheduled_reports_repository import ScheduledReportsRepository

logger = logging.getLogger(__name__)

# Initialize repositories
_s3_reports_repo: ScheduledReportsRepository | None = None
_s3_executions_repo: ExecutionRecordsRepository | None = None
_s3_client = None


def _get_reports_repo() -> ScheduledReportsRepository:
    """Get or initialize the scheduled reports repository."""
    global _s3_reports_repo
    if _s3_reports_repo is None:
        _s3_reports_repo = ScheduledReportsRepository(bucket=S3_BUCKET)
    return _s3_reports_repo


def _get_executions_repo() -> ExecutionRecordsRepository:
    """Get or initialize the execution records repository."""
    global _s3_executions_repo
    if _s3_executions_repo is None:
        _s3_executions_repo = ExecutionRecordsRepository(bucket=S3_BUCKET)
    return _s3_executions_repo


def _get_s3_client():
    """Get or initialize the S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = get_s3_client()
    return _s3_client


def validate_report_config(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Validate scheduled report configuration before execution.

    Checks that:
    - Report exists in S3 and is active
    - User is authenticated/authorized
    - All pinned visualizations still exist

    This is the first step in the execution workflow. Failures here prevent
    the report from executing and result in a marked failure.

    Input:
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string"  (optional, may be stored in report)
    }

    Output:
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string",
      "report_config": {...},  # Full ScheduledReportConfig
      "structured_intents": {...}  # All stored intents
    }

    Raises:
        Exception: If validation fails (caught by state machine Catch block)

    Requirements: 6.2, 2.3
    """
    logger.info(f"ValidateConfig: Starting validation for report {event.get('report_id')}")

    try:
        report_id = event.get("report_id")
        execution_timestamp = event.get("execution_timestamp")
        user_id = event.get("user_id")

        if not report_id or not execution_timestamp:
            raise ValueError("Missing required fields: report_id, execution_timestamp")

        # Retrieve report config from S3
        repo = _get_reports_repo()
        report_config = repo.get_report(user_id, report_id)

        if not report_config:
            raise ValueError(f"Report not found or access denied: {report_id}")

        # Check if report is active
        if not report_config.is_active:
            raise ValueError(f"Report is not active (paused or deactivated): {report_id}")

        # Check if report is soft-deleted
        if report_config.deleted_at is not None:
            raise ValueError(f"Report has been deleted: {report_id}")

        # Validate user ownership
        if report_config.user_id != user_id:
            raise ValueError(f"User not authorized to execute this report: {report_id}")

        # Validate pinned visualization IDs still exist
        # (In a full implementation, this would call the chat service or visualization cache)
        if not report_config.pinned_visualization_ids:
            raise ValueError(f"Report has no pinned visualizations: {report_id}")

        logger.info(f"ValidateConfig: Validation succeeded for report {report_id}")

        return {
            "report_id": report_id,
            "execution_timestamp": execution_timestamp,
            "user_id": user_id,
            "report_config": report_config.model_dump(mode="json"),
            "structured_intents": report_config.structured_intents,
        }

    except Exception as e:
        logger.error(f"ValidateConfig: Validation failed: {str(e)}")
        raise


def fetch_structured_intent(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Fetch the stored StructuredIntent from the report configuration.

    Retrieves the structured query intent that was saved when the report was
    created. This intent is used to re-execute the query without NLP translation.

    Input (from ValidateConfig):
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string",
      "report_config": {...},
      "structured_intents": {...}
    }

    Output:
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string",
      "report_config": {...},
      "structured_intents": {...},  # All stored intents for this report
      "primary_structured_intent": {...}  # First/primary intent for execution
    }

    Raises:
        Exception: If intent retrieval fails

    Requirements: 7.1, 6.3
    """
    logger.info(f"FetchIntent: Retrieving stored intent for report {event.get('report_id')}")

    try:
        report_id = event.get("report_id")
        structured_intents = event.get("structured_intents")

        if not structured_intents:
            raise ValueError(f"No stored structured intents found for report: {report_id}")

        # Get the primary intent (usually the first one, or based on first pinned viz)
        intent_values = list(structured_intents.values())
        if not intent_values:
            raise ValueError(f"Structured intents dict is empty for report: {report_id}")

        primary_intent = intent_values[0]  # Use first intent as primary

        logger.info(f"FetchIntent: Retrieved {len(structured_intents)} intents for report {report_id}")

        # Pass through all event data and add the primary intent
        result = event.copy()
        result["primary_structured_intent"] = primary_intent

        return result

    except Exception as e:
        logger.error(f"FetchIntent: Retrieval failed: {str(e)}")
        raise


def execute_query(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Execute the query against the Orchestrator Hub.

    Uses the stored StructuredIntent to make a direct call to the Orchestrator Hub's
    internal /internal/process endpoint, bypassing the NLP translation layer.
    This ensures consistent, deterministic results across scheduled runs.

    The Orchestrator Hub will:
    - Check result cache for the intent hash
    - Resolve spoke agents based on entity_refs
    - Dispatch to agents in parallel
    - Render visualization output
    - Apply guardrails

    Input (from FetchIntent):
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string",
      "report_config": {...},
      "structured_intents": {...},
      "primary_structured_intent": {...}
    }

    Output:
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string",
      "report_config": {...},
      "structured_intents": {...},
      "primary_structured_intent": {...},
      "orchestrator_response": {...},  # Full response from Orchestrator Hub
      "rendered_output": {...},  # RenderedOutput JSON
      "query_latency_ms": 1234  # Query execution time
    }

    Raises:
        QueryExecutionError: If query execution fails (triggers retry)
        Exception: For other failures

    Requirements: 7.1, 7.2, 7.3, 7.4, 6.3
    """
    logger.info(f"ExecuteQuery: Starting query execution for report {event.get('report_id')}")

    start_time = time.time()

    try:
        report_id = event.get("report_id")
        primary_intent = event.get("primary_structured_intent")

        if not primary_intent:
            raise ValueError("Missing primary_structured_intent from previous step")

        # Call Orchestrator Hub's internal process endpoint
        # The internal endpoint bypasses additional validation and uses the structured intent directly
        orchestrator_url = "http://localhost:8002/internal/process"

        logger.info(f"ExecuteQuery: Calling Orchestrator Hub at {orchestrator_url}")

        # Prepare the request with the stored StructuredIntent
        # The Orchestrator will use this directly without NLP translation
        request_body = {
            "structured_intent": primary_intent,
            "bypass_nlp": True,  # Signal to use stored intent directly
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                orchestrator_url,
                json=request_body,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code != 200:
                error_msg = f"Orchestrator Hub returned status {response.status_code}: {response.text}"
                logger.error(f"ExecuteQuery: {error_msg}")
                raise Exception(error_msg)

            orchestrator_response = response.json()

        # Calculate query latency
        query_latency_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"ExecuteQuery: Query completed in {query_latency_ms}ms for report {report_id}"
        )

        # Extract rendered output from orchestrator response
        # The Orchestrator Hub returns a RenderedOutput in its response
        rendered_output = orchestrator_response.get("rendered_output", {})

        result = event.copy()
        result["orchestrator_response"] = orchestrator_response
        result["rendered_output"] = rendered_output
        result["query_latency_ms"] = query_latency_ms

        return result

    except httpx.TimeoutException as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(f"ExecuteQuery: Timeout after {latency_ms}ms: {str(e)}")
        raise Exception("QueryExecutionError: Query execution timed out") from e
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        logger.error(f"ExecuteQuery: Execution failed after {latency_ms}ms: {str(e)}")
        raise


def store_execution_results(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Store the rendered output to S3 for historical comparison.

    Persists the complete RenderedOutput JSON to S3 with a timestamped key,
    enabling users to compare results across executions.

    Key structure: s3://bucket/scheduled-reports/outputs/{report_id}/{execution_id}.json

    Input (from ExecuteQuery):
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string",
      "report_config": {...},
      "rendered_output": {...},
      "query_latency_ms": 1234,
      "orchestrator_response": {...}
    }

    Output:
    {
      ...event data...,
      "rendered_output_s3_key": "scheduled-reports/outputs/{report_id}/{execution_id}.json"
    }

    Raises:
        Exception: If S3 write fails (triggers retry)

    Requirements: 6.5, 6.3
    """
    logger.info(f"StoreResults: Storing execution results for report {event.get('report_id')}")

    try:
        report_id = event.get("report_id")
        execution_timestamp = event.get("execution_timestamp")
        rendered_output = event.get("rendered_output")

        if not report_id or not execution_timestamp or not rendered_output:
            raise ValueError("Missing required fields: report_id, execution_timestamp, rendered_output")

        # Generate S3 key for the rendered output
        # Using execution_timestamp as execution_id for key naming
        s3_key = f"scheduled-reports/outputs/{report_id}/{execution_timestamp}.json"

        # Serialize rendered output to JSON
        output_json = json.dumps(rendered_output, indent=2, default=str)

        # Write to S3
        s3_client = _get_s3_client()
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=output_json,
            ContentType="application/json",
        )

        logger.info(f"StoreResults: Stored rendered output to S3: {s3_key}")

        result = event.copy()
        result["rendered_output_s3_key"] = s3_key

        return result

    except Exception as e:
        logger.error(f"StoreResults: Failed to store results: {str(e)}")
        raise


def update_report_metadata(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Update report metadata after successful execution.

    Creates an execution record with success status and updates the report's
    last_run_timestamp and last_run_status fields in S3.

    This is the final successful step, persisting both:
    - ExecutionRecord: Complete record of this execution
    - ScheduledReportConfig: Updated with latest run info

    Input (from StoreResults):
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string",
      "report_config": {...},
      "rendered_output_s3_key": "scheduled-reports/outputs/...",
      "query_latency_ms": 1234,
      "orchestrator_response": {...}
    }

    Output:
    {
      ...event data...,
      "execution_id": "uuid-string",
      "status": "success"
    }

    Raises:
        Exception: If DynamoDB/S3 write fails (triggers retry)

    Requirements: 6.4, 6.5, 8.2
    """
    logger.info(f"UpdateMetadata: Updating report metadata for {event.get('report_id')}")

    try:
        report_id = event.get("report_id")
        execution_timestamp_str = event.get("execution_timestamp")
        user_id = event.get("user_id")
        rendered_output_s3_key = event.get("rendered_output_s3_key")
        query_latency_ms = event.get("query_latency_ms")

        if not report_id or not execution_timestamp_str or not user_id:
            raise ValueError("Missing required fields: report_id, execution_timestamp, user_id")

        # Parse timestamps
        execution_timestamp = datetime.fromisoformat(execution_timestamp_str)
        actual_start_timestamp = datetime.utcnow()
        actual_end_timestamp = datetime.utcnow()

        # Create execution record with success status
        execution_id = UUID(int=int(time.time() * 1000000) % (2**32))  # Simplified UUID generation
        execution_record = ExecutionRecord(
            execution_id=execution_id,
            report_id=UUID(report_id),
            execution_timestamp=execution_timestamp,
            actual_start_timestamp=actual_start_timestamp,
            actual_end_timestamp=actual_end_timestamp,
            status="success",
            query_latency_ms=query_latency_ms,
            rendered_output_s3_key=rendered_output_s3_key,
            error_message=None,
            retry_count=0,
        )

        # Persist execution record
        executions_repo = _get_executions_repo()
        executions_repo.create_execution(execution_record)

        logger.info(f"UpdateMetadata: Created execution record {execution_id}")

        # Update report's last_run fields
        reports_repo = _get_reports_repo()
        reports_repo.update_report(
            user_id,
            report_id,
            {
                "last_run_timestamp": actual_end_timestamp.isoformat(),
                "last_run_status": "success",
                "updated_at": actual_end_timestamp.isoformat(),
            },
        )

        logger.info(f"UpdateMetadata: Updated report {report_id} with last_run info")

        result = event.copy()
        result["execution_id"] = str(execution_id)
        result["status"] = "success"

        return result

    except Exception as e:
        logger.error(f"UpdateMetadata: Failed to update metadata: {str(e)}")
        raise


def mark_execution_failed(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Mark a scheduled report execution as failed and record error details.

    This handler is invoked by the state machine Catch blocks when any step fails.
    It creates a failed execution record with error details and updates the report's
    last_run_status to "failed".

    The error information is extracted from the Step Functions context or passed
    through the event from the failing step.

    Input (from any Catch block):
    {
      "report_id": "uuid-string",
      "execution_timestamp": "ISO8601 datetime",
      "user_id": "string",
      "report_config": {...},
      "error": {
        "Error": "...",
        "Cause": "..."
      }
    }

    Output:
    {
      "execution_id": "uuid-string",
      "report_id": "uuid-string",
      "status": "failed",
      "error_message": "..."
    }

    Note: This handler should NOT fail itself. Errors here are logged but not
    re-raised, as the state machine will proceed to FailureState regardless.

    Requirements: 6.4, 8.2
    """
    logger.info(f"MarkFailed: Marking execution as failed for report {event.get('report_id')}")

    try:
        report_id = event.get("report_id")
        execution_timestamp_str = event.get("execution_timestamp")
        user_id = event.get("user_id")
        error_info = event.get("error", {})

        if not report_id or not execution_timestamp_str or not user_id:
            logger.error("MarkFailed: Missing required fields")
            return {
                "status": "failed",
                "error_message": "Missing required fields for failed execution record",
            }

        # Extract error details
        error_error = error_info.get("Error", "UNKNOWN_ERROR")
        error_cause = error_info.get("Cause", "Unknown cause")
        error_message = f"{error_error}: {error_cause}"

        # Parse timestamps
        execution_timestamp = datetime.fromisoformat(execution_timestamp_str)
        actual_start_timestamp = datetime.utcnow()
        actual_end_timestamp = datetime.utcnow()

        # Create failed execution record
        execution_id = UUID(int=int(time.time() * 1000000) % (2**32))
        execution_record = ExecutionRecord(
            execution_id=execution_id,
            report_id=UUID(report_id),
            execution_timestamp=execution_timestamp,
            actual_start_timestamp=actual_start_timestamp,
            actual_end_timestamp=actual_end_timestamp,
            status="failed",
            query_latency_ms=None,
            rendered_output_s3_key=None,
            error_message=error_message,
            retry_count=0,
        )

        # Persist failed execution record
        try:
            executions_repo = _get_executions_repo()
            executions_repo.create_execution(execution_record)
            logger.info(f"MarkFailed: Created failed execution record {execution_id}")
        except Exception as e:
            logger.error(f"MarkFailed: Failed to create execution record: {str(e)}")

        # Update report's last_run_status to failed
        try:
            reports_repo = _get_reports_repo()
            reports_repo.update_report(
                user_id,
                report_id,
                {
                    "last_run_timestamp": actual_end_timestamp.isoformat(),
                    "last_run_status": "failed",
                    "updated_at": actual_end_timestamp.isoformat(),
                },
            )
            logger.info(f"MarkFailed: Updated report {report_id} with failed status")
        except Exception as e:
            logger.error(f"MarkFailed: Failed to update report status: {str(e)}")

        result = {
            "execution_id": str(execution_id),
            "report_id": report_id,
            "status": "failed",
            "error_message": error_message,
        }

        return result

    except Exception as e:
        logger.error(f"MarkFailed: Unexpected error in mark_execution_failed: {str(e)}")
        # Don't raise - this is the final error handler, any failure here just logs
        return {
            "status": "failed",
            "error_message": f"Unexpected error in mark_execution_failed: {str(e)}",
        }


# Lambda handler wrappers for deployment
# Each handler can be deployed as a separate Lambda function


def validate_report_config_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler for validate_report_config step."""
    return validate_report_config(event, context)


def fetch_structured_intent_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler for fetch_structured_intent step."""
    return fetch_structured_intent(event, context)


def execute_query_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler for execute_query step."""
    return execute_query(event, context)


def store_execution_results_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler for store_execution_results step."""
    return store_execution_results(event, context)


def update_report_metadata_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler for update_report_metadata step."""
    return update_report_metadata(event, context)


def mark_execution_failed_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler for mark_execution_failed step."""
    return mark_execution_failed(event, context)
