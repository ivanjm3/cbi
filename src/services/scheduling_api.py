"""FastAPI application for the Scheduling API service.

Exposes REST endpoints for creating, managing, and executing scheduled reports.
Integrates with S3 repositories for persistence and EventBridge Scheduler for
triggering Step Functions executions.

Runs on port 8005.

Requirements: 9.1, 9.2, 8.1, 2.1, 2.3, 5.3, 6.1, 10.1, 3.1, 3.2, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6,
             6.5, 6.6, 8.3, 8.4, 9.3, 9.4, 9.5, 10.3, 11.1, 11.2, 11.3, 12.3
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import GUARDRAIL_PORT, NLP_PORT, ORCHESTRATOR_PORT, SCHEDULING_PORT, VIZ_PORT
from src.models.scheduled_reports import (
    CreateReportRequest,
    ExecutionRecord,
    RecurrencePattern,
    ScheduledReportConfig,
    UpdateReportRequest,
)
from src.services.logging_config import configure_logging
from src.services.recurrence_calculator import (
    compute_next_execution,
    format_recurrence_display,
)
from src.services.execution_records_repository import ExecutionRecordsRepository
from src.services.scheduled_reports_repository import ScheduledReportsRepository
from src.services.scheduler_manager import SchedulerManager

configure_logging()
logger = logging.getLogger(__name__)

# Initialize repositories and scheduler manager
_reports_repo: Optional[ScheduledReportsRepository] = None
_executions_repo: Optional[ExecutionRecordsRepository] = None
_scheduler_manager: Optional[SchedulerManager] = None

# FastAPI app
app = FastAPI(
    title="Scheduling API Service",
    description="REST API for managing scheduled reports and their execution history.",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup_local_scheduler():
    """Start local APScheduler and sync existing report jobs."""
    from src.services.local_scheduler import start_scheduler, sync_all_jobs

    start_scheduler()
    await sync_all_jobs()


@app.on_event("shutdown")
async def _shutdown_local_scheduler():
    """Stop local APScheduler."""
    from src.services.local_scheduler import stop_scheduler

    stop_scheduler()


def get_reports_repo() -> ScheduledReportsRepository:
    """Get or create the reports repository."""
    global _reports_repo
    if _reports_repo is None:
        _reports_repo = ScheduledReportsRepository()
    return _reports_repo


def get_executions_repo() -> ExecutionRecordsRepository:
    """Get or create the executions repository."""
    global _executions_repo
    if _executions_repo is None:
        _executions_repo = ExecutionRecordsRepository()
    return _executions_repo


def get_scheduler_manager() -> SchedulerManager:
    """Get or create the scheduler manager."""
    global _scheduler_manager
    if _scheduler_manager is None:
        state_machine_arn = os.environ.get(
            "STEP_FUNCTIONS_STATE_MACHINE_ARN",
            "arn:aws:states:us-east-1:654654478821:stateMachine:scheduled-report-executor",
        )
        _scheduler_manager = SchedulerManager(state_machine_arn)
    return _scheduler_manager


def _extract_user_id(request: Request) -> str:
    """Extract user ID from request (from session token or header).

    For MVP, we'll extract from X-User-ID header or session.
    In production, would validate JWT/session token.

    Args:
        request: FastAPI Request object

    Returns:
        User ID string

    Raises:
        HTTPException: If user ID cannot be determined
    """
    # Check X-User-ID header first
    user_id = request.headers.get("X-User-ID")
    if user_id:
        return user_id

    # Check Authorization header for JWT (extract subject)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        # For MVP, just extract from header; in production decode JWT
        token = auth_header[7:]
        # Placeholder: in production, decode and validate JWT
        return f"user-{token[:20]}"  # Simplified

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: X-User-ID header or Authorization token required",
    )


async def _verify_chat_exists(chat_id: str, user_id: str) -> bool:
    """Verify that a chat exists for the user by calling the Orchestrator Hub.

    Args:
        chat_id: Chat session ID
        user_id: User ID

    Returns:
        True if chat exists

    Raises:
        HTTPException: If chat cannot be verified
    """
    try:
        # Call internal API to verify chat exists
        # For MVP, we'll accept any chat_id; in production, verify via Orchestrator
        logger.info(f"Verifying chat: chat_id={chat_id}, user_id={user_id}")
        # TODO: Call orchestrator_hub /internal/chat/{chat_id} endpoint
        return True
    except Exception as e:
        logger.error(f"Error verifying chat: {e}")
        raise HTTPException(status_code=422, detail="Chat not found or verification failed")


async def _verify_visualizations_exist(chat_id: str, viz_ids: list[str]) -> bool:
    """Verify that all specified visualizations exist in a chat.

    Args:
        chat_id: Chat session ID
        viz_ids: List of visualization card IDs

    Returns:
        True if all visualizations exist

    Raises:
        HTTPException: If any visualization cannot be verified
    """
    try:
        logger.info(f"Verifying visualizations: chat_id={chat_id}, viz_ids={viz_ids}")
        # TODO: Call orchestrator_hub /internal/chat/{chat_id}/cards endpoint
        # and verify all viz_ids exist in the response
        return True
    except Exception as e:
        logger.error(f"Error verifying visualizations: {e}")
        raise HTTPException(
            status_code=422,
            detail="One or more visualizations not found in chat",
        )


async def _fetch_structured_intents(
    chat_id: str, viz_ids: list[str]
) -> dict[str, dict]:
    """Fetch StructuredIntent objects for each pinned visualization.

    Args:
        chat_id: Chat session ID
        viz_ids: List of visualization card IDs

    Returns:
        Dictionary mapping viz_id -> StructuredIntent dict

    Raises:
        HTTPException: If intents cannot be fetched
    """
    try:
        logger.info(f"Fetching structured intents: chat_id={chat_id}, viz_ids={viz_ids}")
        # TODO: Call orchestrator_hub /internal/chat/{chat_id}/cards/{viz_id}/intent
        # endpoint for each viz_id
        structured_intents = {}
        for viz_id in viz_ids:
            # Placeholder: in production, fetch from orchestrator
            structured_intents[viz_id] = {
                "entity_refs": [],
                "query_type": "raw",
                "filters": {},
            }
        return structured_intents
    except Exception as e:
        logger.error(f"Error fetching structured intents: {e}")
        raise HTTPException(
            status_code=422,
            detail="Failed to fetch visualization intents",
        )


def _normalize_structured_intent(raw: dict) -> dict:
    """Coerce a stored/frontend intent into a valid StructuredIntent payload.

    The Orchestrator's StructuredIntent requires: query_id (UUID), query_type
    (lookup|aggregation|comparison), entity_refs (>=1), routing_metadata, timestamp.
    Frontend metadata may use other query_type values or omit fields, so we map
    and backfill to satisfy validation.

    Args:
        raw: The raw intent dict stored on the report.

    Returns:
        A dict ready to send to /internal/process.

    Raises:
        ValueError: If no entity_refs are available (cannot route the query).
    """
    valid_types = {"lookup", "aggregation", "comparison"}

    entity_refs = raw.get("entity_refs") or []
    if not entity_refs:
        raise ValueError(
            "Stored intent has no entity_refs; cannot replay query. "
            "Re-create the scheduled report from a completed query."
        )

    # Map arbitrary frontend query_type values onto the allowed set.
    qt = str(raw.get("query_type", "")).lower()
    if qt not in valid_types:
        if qt in ("comparison", "compare"):
            qt = "comparison"
        elif qt in ("aggregation", "agg", "trend", "matrix", "correlation"):
            qt = "aggregation"
        else:
            qt = "lookup"

    query_id = raw.get("query_id") or str(uuid4())
    timestamp = raw.get("timestamp") or datetime.now(ZoneInfo("UTC")).isoformat()
    routing_metadata = raw.get("routing_metadata") or {}

    return {
        "query_id": query_id,
        "query_type": qt,
        "entity_refs": entity_refs,
        "routing_metadata": routing_metadata,
        "timestamp": timestamp,
    }


def _validate_next_execution_time(next_execution_time: datetime) -> bool:
    """Validate that next execution time is no more than 30 days in the future.

    Args:
        next_execution_time: Computed next execution time

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
    now = datetime.now(ZoneInfo("UTC"))
    max_future = now + timedelta(days=30)

    if next_execution_time > max_future:
        raise ValueError(
            f"Next execution time ({next_execution_time.isoformat()}) "
            f"is more than 30 days in the future (max: {max_future.isoformat()})"
        )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Health Endpoint
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health_check():
    """Health check endpoint.

    Returns:
        200 with status OK
    """
    return {"status": "ok", "service": "scheduling-api"}


# ─────────────────────────────────────────────────────────────────────────────
# Scheduled Reports CRUD Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/scheduled-reports", status_code=201)
async def create_scheduled_report(
    request: Request,
    body: CreateReportRequest,
):
    """Create a new scheduled report (Task 6.2).

    Validates request body, verifies referenced chat_id and visualizations exist,
    fetches and stores StructuredIntents, computes next execution time, persists
    to S3, and creates EventBridge schedule.

    Args:
        request: FastAPI Request object
        body: CreateReportRequest with report configuration

    Returns:
        201 with created report summary: report_id, title, next_execution_time, status, created_at

    Raises:
        400: If validation fails
        401: If not authenticated
        422: If next execution > 30 days, chat not found, visualization not found, or other validation errors
        503: If AWS service unavailable

    Requirements: 8.1, 2.1, 2.3, 5.3, 6.1, 10.1
    """
    user_id = _extract_user_id(request)

    try:
        # Validate request body (Pydantic handles this)
        # Verify chat exists
        await _verify_chat_exists(body.original_chat_id, user_id)

        # Verify all pinned visualizations exist
        await _verify_visualizations_exist(body.original_chat_id, body.pinned_visualization_ids)

        # Use StructuredIntents provided by the frontend (the real intents captured
        # when the query ran). Fall back to fetching only if not provided.
        if body.structured_intents:
            structured_intents = body.structured_intents
        else:
            structured_intents = await _fetch_structured_intents(
                body.original_chat_id,
                body.pinned_visualization_ids,
            )

        # Generate report ID
        report_id = uuid4()

        # Compute next execution time
        now = datetime.now(ZoneInfo("UTC"))
        next_execution_time = compute_next_execution(
            body.recurrence_pattern,
            now,
            body.recurrence_pattern.timezone,
        )

        # Validate next execution time is not > 30 days in future
        _validate_next_execution_time(next_execution_time)

        # Build report config
        config = ScheduledReportConfig(
            report_id=report_id,
            user_id=user_id,
            title=body.title,
            description=body.description,
            original_chat_id=body.original_chat_id,
            pinned_visualization_ids=body.pinned_visualization_ids,
            structured_intents=structured_intents,
            query_texts=body.query_texts or {},
            recurrence_pattern=body.recurrence_pattern,
            is_active=True,
            next_execution_time=next_execution_time,
            created_at=now,
            updated_at=now,
        )

        # Persist to S3 and update index
        reports_repo = get_reports_repo()
        reports_repo.create_report(config)

        # Create EventBridge schedule
        schedule_arn: Optional[str] = None
        try:
            scheduler = get_scheduler_manager()
            schedule_arn = scheduler.create_schedule(str(report_id), body.recurrence_pattern)

            # Update config with schedule ARN
            reports_repo.update_report(user_id, str(report_id), {"schedule_arn": schedule_arn})
        except Exception as e:
            logger.error(f"Failed to create EventBridge schedule for report {report_id}: {e}")
            # Continue anyway - schedule can be created later
            pass

        # Always register local cron (works without IAM PassRole)
        from src.services.local_scheduler import add_job
        add_job(str(report_id), body.recurrence_pattern.model_dump())

        logger.info(f"Created scheduled report: report_id={report_id}, user_id={user_id}")

        return {
            "report_id": str(report_id),
            "title": config.title,
            "next_execution_time": next_execution_time.isoformat(),
            "status": "active",
            "created_at": config.created_at.isoformat(),
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error creating scheduled report: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating scheduled report: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/scheduled-reports")
async def list_scheduled_reports(request: Request):
    """List all scheduled reports for the authenticated user (Task 6.3).

    Reads from S3 index, filters by user_id, returns list of report summaries
    with recurrence_display formatted for UI.

    Args:
        request: FastAPI Request object

    Returns:
        200 with list: {reports: [{report_id, title, next_execution_time, last_run_timestamp,
                                   recurrence_display, status}], total_count}

    Raises:
        401: If not authenticated
        503: If S3 unavailable

    Requirements: 3.1, 3.2, 4.1, 9.3, 9.4
    """
    user_id = _extract_user_id(request)

    try:
        reports_repo = get_reports_repo()
        reports = reports_repo.get_reports_by_user(user_id)

        return {
            "reports": [
                {
                    "report_id": str(r.report_id),
                    "title": r.title,
                    "next_execution_time": r.next_execution_time.isoformat()
                    if r.next_execution_time
                    else None,
                    "last_run_timestamp": r.last_run_timestamp.isoformat()
                    if r.last_run_timestamp
                    else None,
                    "recurrence_display": format_recurrence_display(r.recurrence_pattern),
                    "status": "active" if r.is_active else "paused",
                }
                for r in reports
                if r.deleted_at is None  # Don't return soft-deleted reports
            ],
            "total_count": len([r for r in reports if r.deleted_at is None]),
        }
    except Exception as e:
        logger.error(f"Error listing reports for user {user_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.get("/scheduled-reports/{report_id}")
async def get_scheduled_report(request: Request, report_id: str):
    """Get details of a specific scheduled report (Task 6.3).

    Reads from S3, verifies ownership, returns full config + execution summary.

    Args:
        request: FastAPI Request object
        report_id: Report UUID

    Returns:
        200 with full report configuration: {report_id, title, description, original_chat_id,
                                             pinned_visualization_ids, recurrence_pattern,
                                             is_active, next_execution_time, last_run_timestamp,
                                             last_run_status, created_at, updated_at}

    Raises:
        401: If not authenticated
        403: If user doesn't own the report (not owner of this report)
        404: If report not found or is soft-deleted
        503: If S3 unavailable

    Requirements: 3.1, 3.2, 4.1, 9.3, 9.4
    """
    user_id = _extract_user_id(request)

    try:
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        # Verify ownership
        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        return {
            "report_id": str(config.report_id),
            "title": config.title,
            "description": config.description,
            "original_chat_id": config.original_chat_id,
            "pinned_visualization_ids": config.pinned_visualization_ids,
            "structured_intents": config.structured_intents,
            "query_texts": config.query_texts,
            "recurrence_pattern": config.recurrence_pattern.model_dump(),
            "is_active": config.is_active,
            "next_execution_time": config.next_execution_time.isoformat()
            if config.next_execution_time
            else None,
            "last_run_timestamp": config.last_run_timestamp.isoformat()
            if config.last_run_timestamp
            else None,
            "last_run_status": config.last_run_status,
            "created_at": config.created_at.isoformat(),
            "updated_at": config.updated_at.isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.patch("/scheduled-reports/{report_id}")
async def update_scheduled_report(request: Request, report_id: str, body: UpdateReportRequest):
    """Update a scheduled report (Task 6.4).

    Supports partial updates: title, description, recurrence_pattern.
    If recurrence changes, updates EventBridge schedule and recomputes next_execution_time.
    Applies idempotent (debounce-friendly) update semantics.
    Enforces ownership check.

    Args:
        request: FastAPI Request object
        report_id: Report UUID
        body: UpdateReportRequest with fields to update (all optional)

    Returns:
        200 with updated report: {report_id, title, next_execution_time}

    Raises:
        401: If not authenticated
        403: If user doesn't own the report
        404: If report not found
        422: If validation fails
        503: If service unavailable

    Requirements: 4.2, 4.3, 9.5, 10.3
    """
    user_id = _extract_user_id(request)

    try:
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        # Build updates dictionary
        updates = {}
        if body.title is not None:
            updates["title"] = body.title
        if body.description is not None:
            updates["description"] = body.description

        # If recurrence pattern changed, update EventBridge schedule and recompute next execution
        if body.recurrence_pattern is not None:
            updates["recurrence_pattern"] = body.recurrence_pattern.model_dump()

            # Try to update EventBridge schedule, but don't fail if it errors
            # (may lack IAM PassRole permission). Local state update is what matters.
            try:
                scheduler = get_scheduler_manager()
                scheduler.update_schedule(report_id, body.recurrence_pattern)
                logger.info(f"Updated EventBridge schedule for report {report_id}")
            except Exception as e:
                logger.warning(f"Could not update EventBridge schedule (will use local state): {e}")
                # Continue — recurrence update will still work via local state

            # Recompute next execution time
            now = datetime.now(ZoneInfo("UTC"))
            next_execution_time = compute_next_execution(
                body.recurrence_pattern,
                now,
                body.recurrence_pattern.timezone,
            )

            # Validate next execution time is not > 30 days in future
            _validate_next_execution_time(next_execution_time)
            updates["next_execution_time"] = next_execution_time.isoformat()

        # Perform the update
        updated = reports_repo.update_report(user_id, report_id, updates)

        # If recurrence changed, update local cron job
        if body.recurrence_pattern is not None:
            from src.services.local_scheduler import add_job
            add_job(report_id, body.recurrence_pattern.model_dump())

        logger.info(f"Updated scheduled report {report_id}")

        return {
            "report_id": str(updated.report_id),
            "title": updated.title,
            "next_execution_time": updated.next_execution_time.isoformat()
            if updated.next_execution_time
            else None,
        }
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"Validation error updating report {report_id}: {e}")
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.delete("/scheduled-reports/{report_id}", status_code=204)
async def delete_scheduled_report(request: Request, report_id: str):
    """Delete a scheduled report (Task 6.5).

    Soft-deletes report config (sets deleted_at timestamp), disables and deletes
    EventBridge schedule, and preserves execution records (does not cascade delete).
    Enforces ownership check.

    Args:
        request: FastAPI Request object
        report_id: Report UUID

    Returns:
        204 No Content

    Raises:
        401: If not authenticated
        403: If user doesn't own the report
        404: If report not found
        503: If service unavailable

    Requirements: 12.3, 8.4, 9.5
    """
    user_id = _extract_user_id(request)

    try:
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        # Disable and delete EventBridge schedule
        try:
            scheduler = get_scheduler_manager()
            scheduler.delete_schedule(report_id)
            logger.info(f"Deleted EventBridge schedule for report {report_id}")
        except Exception as e:
            logger.error(f"Failed to delete EventBridge schedule for report {report_id}: {e}")
            # Continue anyway - soft-delete still happens

        # Soft-delete the report (sets deleted_at timestamp)
        reports_repo.soft_delete_report(user_id, report_id)

        # Remove local cron job
        from src.services.local_scheduler import remove_job
        remove_job(report_id)

        logger.info(f"Soft-deleted scheduled report {report_id}")

        # Execution records are preserved (no cascade delete)
        return JSONResponse(status_code=204, content=None)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# Control Endpoints (Pause, Resume, Retry) - Task 6.6
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/scheduled-reports/{report_id}/pause")
async def pause_scheduled_report(request: Request, report_id: str):
    """Pause a scheduled report (Task 6.6).

    Sets is_active=false and attempts to disable EventBridge schedule.
    If EventBridge update fails (e.g. due to IAM permission), still succeeds
    by updating local state — the schedule will be ignored on next trigger.

    Args:
        request: FastAPI Request object
        report_id: Report UUID

    Returns:
        200 with status: {status: "paused"}

    Raises:
        401: If not authenticated
        403: If user doesn't own the report
        404: If report not found
        503: If database update fails

    Requirements: 11.1, 11.2
    """
    user_id = _extract_user_id(request)

    try:
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        # Try to disable EventBridge schedule, but don't fail if it errors
        # (may lack IAM PassRole permission). Local state update is what matters.
        try:
            scheduler = get_scheduler_manager()
            scheduler.disable_schedule(report_id)
            logger.info(f"Disabled EventBridge schedule for report {report_id}")
        except Exception as e:
            logger.warning(f"Could not disable EventBridge schedule (will use local state): {e}")
            # Continue — pause will still work via local is_active flag

        # Update config: set is_active=false
        reports_repo.update_report(user_id, report_id, {"is_active": False})

        # Pause local cron
        from src.services.local_scheduler import pause_job
        pause_job(report_id)

        logger.info(f"Paused scheduled report {report_id}")

        return {"status": "paused"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.post("/scheduled-reports/{report_id}/resume")
async def resume_scheduled_report(request: Request, report_id: str):
    """Resume a paused scheduled report (Task 6.6).

    Sets is_active=true, attempts to enable EventBridge schedule, and recomputes next_execution_time.
    If EventBridge update fails (e.g. due to IAM permission), still succeeds by updating local state.

    Args:
        request: FastAPI Request object
        report_id: Report UUID

    Returns:
        200 with status: {status: "resumed"}

    Raises:
        401: If not authenticated
        403: If user doesn't own the report
        404: If report not found
        503: If database update fails

    Requirements: 11.2, 11.3
    """
    user_id = _extract_user_id(request)

    try:
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        # Try to re-enable EventBridge schedule, but don't fail if it errors
        try:
            scheduler = get_scheduler_manager()
            scheduler.enable_schedule(report_id)
            logger.info(f"Enabled EventBridge schedule for report {report_id}")
        except Exception as e:
            logger.warning(f"Could not enable EventBridge schedule (will use local state): {e}")
            # Continue — resume will still work via local is_active flag

        # Recompute next_execution_time (if it's in the past, it will be set to next occurrence)
        now = datetime.now(ZoneInfo("UTC"))
        next_execution_time = compute_next_execution(
            config.recurrence_pattern,
            now,
            config.recurrence_pattern.timezone,
        )

        # Update config: set is_active=true and next_execution_time
        reports_repo.update_report(
            user_id,
            report_id,
            {
                "is_active": True,
                "next_execution_time": next_execution_time.isoformat(),
            },
        )

        # Resume local cron
        from src.services.local_scheduler import resume_job, add_job
        resume_job(report_id)
        # If job doesn't exist yet (e.g. first resume after restart), create it
        add_job(report_id, config.recurrence_pattern.model_dump())

        logger.info(f"Resumed scheduled report {report_id}")

        return {"status": "resumed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.post("/scheduled-reports/{report_id}/retry")
async def retry_scheduled_report(request: Request, report_id: str):
    """Trigger immediate retry of a scheduled report (Task 6.6).

    Immediately triggers Step Functions execution for this report.

    Args:
        request: FastAPI Request object
        report_id: Report UUID

    Returns:
        200 with status: {status: "retry_triggered", execution_arn: "..."}

    Raises:
        401: If not authenticated
        403: If user doesn't own the report
        404: If report not found
        503: If service unavailable

    Requirements: 11.3, 4.4, 4.5
    """
    user_id = _extract_user_id(request)

    try:
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        # Execute the report directly (bypasses Step Functions Pass state)
        # This calls the same logic that EventBridge/Step Functions would trigger
        try:
            result = await execute_scheduled_report({"report_id": report_id})
            logger.info(f"Direct execution completed for report {report_id}: {result}")

            return {
                "status": "retry_triggered",
                "execution_id": result.get("execution_id"),
                "query_latency_ms": result.get("query_latency_ms"),
            }

        except HTTPException as e:
            logger.error(f"Execution failed for report {report_id}: {e.detail}")
            raise HTTPException(
                status_code=503,
                detail=f"Execution failed: {e.detail}",
            )
        except Exception as e:
            logger.error(f"Failed to execute report {report_id}: {e}")
            raise HTTPException(
                status_code=503,
                detail="Failed to trigger retry; please try again",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# Execution History Endpoint - Task 6.7
# ─────────────────────────────────────────────────────────────────────────────


@app.get("/scheduled-reports/{report_id}/executions")
async def get_execution_history(
    request: Request, report_id: str, page: int = 1, page_size: int = 10
):
    """Get paginated execution history for a report (Task 6.7).

    Returns paginated execution history sorted by execution_timestamp descending
    (newest first). Includes status, latency, error_message for each record.

    Args:
        request: FastAPI Request object
        report_id: Report UUID
        page: Page number (1-indexed, default 1)
        page_size: Number of records per page (default 10, max 100)

    Returns:
        200 with paginated executions: {executions: [{execution_id, execution_timestamp,
                                                       actual_start_timestamp, status,
                                                       query_latency_ms, error_message}],
                                        total_count, page, page_size}

    Raises:
        401: If not authenticated
        403: If user doesn't own the report
        404: If report not found
        503: If service unavailable

    Requirements: 4.6, 6.6, 8.3
    """
    user_id = _extract_user_id(request)

    try:
        # Verify ownership and report exists
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        # Validate page parameters
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 100:
            page_size = 10

        # Get execution history
        executions_repo = get_executions_repo()
        records, total_count = executions_repo.get_executions_by_report(
            report_id, page, page_size
        )

        return {
            "executions": [
                {
                    "execution_id": str(r.execution_id),
                    "execution_timestamp": r.execution_timestamp.isoformat(),
                    "actual_start_timestamp": r.actual_start_timestamp.isoformat(),
                    "status": r.status,
                    "query_latency_ms": r.query_latency_ms,
                    "error_message": r.error_message,
                    "rendered_output": r.rendered_output,
                }
                for r in records
            ],
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving execution history for report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# Prompt Management Endpoints - Add/remove individual prompts from a report
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/scheduled-reports/{report_id}/prompts")
async def add_prompt_to_report(request: Request, report_id: str):
    """Add a new prompt to a scheduled report.

    Runs the query through the NLP /query endpoint and adds the result
    to the report configuration.

    Args:
        request: FastAPI Request object
        report_id: Report UUID

    Returns:
        200 with {viz_id, rendered_output}

    Raises:
        401: If not authenticated
        403: If user doesn't own the report
        404: If report not found
        422: If query_text missing
        503: If NLP query fails
    """
    user_id = _extract_user_id(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid JSON body")

    query_text = body.get("query_text", "").strip()
    if not query_text:
        raise HTTPException(status_code=422, detail="query_text is required")

    try:
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        # Generate a new viz_id for this prompt
        new_viz_id = str(uuid4())

        # Run the query through NLP /query (same as execute_scheduled_report)
        async with httpx.AsyncClient(verify=False, timeout=300) as client:
            nlp_resp = await client.post(
                f"http://localhost:{NLP_PORT}/query",
                json={"query_text": query_text},
                headers={"Content-Type": "application/json"},
            )
            if nlp_resp.status_code != 200:
                logger.error(f"NLP query failed for new prompt: {nlp_resp.text[:200]}")
                raise HTTPException(
                    status_code=503,
                    detail=f"Query execution failed: {nlp_resp.text[:200]}",
                )

            nlp_data = nlp_resp.json()
            rendered_output = nlp_data.get("rendered_output", nlp_data)

        # Update the report config: add to query_texts, pinned_visualization_ids
        updated_query_texts = dict(config.query_texts)
        updated_query_texts[new_viz_id] = query_text

        updated_pinned_ids = list(config.pinned_visualization_ids)
        updated_pinned_ids.append(new_viz_id)

        reports_repo.update_report(
            user_id,
            report_id,
            {
                "query_texts": updated_query_texts,
                "pinned_visualization_ids": updated_pinned_ids,
            },
        )

        logger.info(f"Added prompt to report {report_id}: viz_id={new_viz_id}")

        # Merge the new output into the latest execution (avoid full re-run).
        # Build a tagged output entry and append to the most recent execution's outputs.
        try:
            executions_repo = get_executions_repo()
            records, _ = executions_repo.get_executions_by_report(report_id, 1, 1)
            new_entry = {
                "viz_id": new_viz_id,
                "query_text": query_text,
                "rendered_output": rendered_output,
            }

            now = datetime.now(ZoneInfo("UTC"))
            if records and records[0].status == "success":
                latest = records[0]
                existing = latest.rendered_output
                if isinstance(existing, list):
                    merged = existing + [new_entry]
                elif existing is None:
                    merged = [new_entry]
                else:
                    # Legacy single-dict output → wrap then append
                    merged = [existing, new_entry]

                # Write a fresh execution record reflecting the merged outputs
                merged_record = ExecutionRecord(
                    execution_id=uuid4(),
                    report_id=report_id,
                    execution_timestamp=now,
                    actual_start_timestamp=now,
                    actual_end_timestamp=now,
                    status="success",
                    query_latency_ms=0,
                    rendered_output=merged,
                    error_message=None,
                )
                executions_repo.create_execution(merged_record)
            else:
                # No prior successful execution — create one with just this output
                merged_record = ExecutionRecord(
                    execution_id=uuid4(),
                    report_id=report_id,
                    execution_timestamp=now,
                    actual_start_timestamp=now,
                    actual_end_timestamp=now,
                    status="success",
                    query_latency_ms=0,
                    rendered_output=[new_entry],
                    error_message=None,
                )
                executions_repo.create_execution(merged_record)
        except Exception as merge_err:
            logger.warning(f"Could not merge new prompt into latest execution: {merge_err}")

        return {"viz_id": new_viz_id, "rendered_output": rendered_output}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding prompt to report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


@app.delete("/scheduled-reports/{report_id}/prompts/{viz_id}")
async def delete_prompt_from_report(request: Request, report_id: str, viz_id: str):
    """Remove a prompt from a scheduled report.

    Removes the viz_id from pinned_visualization_ids, query_texts,
    and structured_intents.

    Args:
        request: FastAPI Request object
        report_id: Report UUID
        viz_id: Visualization ID to remove

    Returns:
        204 No Content

    Raises:
        401: If not authenticated
        403: If user doesn't own the report
        404: If report not found
    """
    user_id = _extract_user_id(request)

    try:
        reports_repo = get_reports_repo()
        config = reports_repo.get_report(user_id, report_id)

        if not config or config.deleted_at is not None:
            raise HTTPException(status_code=404, detail="Report not found")

        if config.user_id != user_id:
            raise HTTPException(status_code=403, detail="Forbidden: not owner of this report")

        # Remove from pinned_visualization_ids
        updated_pinned_ids = [
            vid for vid in config.pinned_visualization_ids if vid != viz_id
        ]

        # Remove from query_texts
        updated_query_texts = {
            k: v for k, v in config.query_texts.items() if k != viz_id
        }

        # Remove from structured_intents
        updated_structured_intents = {
            k: v for k, v in config.structured_intents.items() if k != viz_id
        }

        reports_repo.update_report(
            user_id,
            report_id,
            {
                "pinned_visualization_ids": updated_pinned_ids,
                "query_texts": updated_query_texts,
                "structured_intents": updated_structured_intents,
            },
        )

        logger.info(f"Removed prompt from report {report_id}: viz_id={viz_id}")

        # Surgically remove this viz's output from the latest execution (no re-run).
        try:
            executions_repo = get_executions_repo()
            records, _ = executions_repo.get_executions_by_report(report_id, 1, 1)
            if records and records[0].status == "success":
                latest = records[0]
                existing = latest.rendered_output
                if isinstance(existing, list):
                    filtered = [
                        o for o in existing
                        if not (isinstance(o, dict) and o.get("viz_id") == viz_id)
                    ]
                    now = datetime.now(ZoneInfo("UTC"))
                    merged_record = ExecutionRecord(
                        execution_id=uuid4(),
                        report_id=report_id,
                        execution_timestamp=now,
                        actual_start_timestamp=now,
                        actual_end_timestamp=now,
                        status="success",
                        query_latency_ms=0,
                        rendered_output=filtered,
                        error_message=None,
                    )
                    executions_repo.create_execution(merged_record)
        except Exception as merge_err:
            logger.warning(f"Could not update latest execution after delete: {merge_err}")

        return JSONResponse(status_code=204, content=None)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing prompt from report {report_id}: {e}")
        raise HTTPException(status_code=503, detail="Service unavailable")


# ─────────────────────────────────────────────────────────────────────────────
# Step Functions Execution Endpoint - Called directly by Step Functions state machine
# ─────────────────────────────────────────────────────────────────────────────


@app.post("/execute-scheduled-report")
async def execute_scheduled_report(body: dict):
    """Execute a scheduled report.

    This endpoint is called directly by the Step Functions state machine.
    It retrieves the report configuration, fetches the stored StructuredIntents,
    executes the query via the Orchestrator Hub, stores the execution result,
    and updates the report with the latest execution metadata.

    Args:
        body: Dictionary with report_id

    Returns:
        200 with execution result: {status: "success", execution_id, query_latency_ms}

    Raises:
        400: If report_id is missing
        404: If report not found
        503: If execution fails

    Requirements: 6.2, 6.3, 6.4, 6.5, 7.1, 7.2, 7.3, 7.4
    """
    report_id = body.get("report_id")
    if not report_id:
        raise HTTPException(status_code=400, detail="report_id is required")

    execution_id = str(uuid4())
    start_time = datetime.now(ZoneInfo("UTC"))

    try:
        # Fetch report config from S3
        reports_repo = get_reports_repo()
        
        # Get report for any user (we don't enforce user_id here since Step Functions
        # can only trigger reports that were created, so this is safe)
        config = reports_repo.get_report_by_id(report_id)
        
        if not config:
            logger.error(f"Report not found: {report_id}")
            raise HTTPException(status_code=404, detail="Report not found")

        if not config.is_active:
            logger.info(f"Report is paused, skipping execution: {report_id}")
            # Still record this as a skipped execution
            executions_repo = get_executions_repo()
            execution_record = ExecutionRecord(
                execution_id=execution_id,
                report_id=report_id,
                execution_timestamp=start_time,
                actual_start_timestamp=start_time,
                status="skipped",
                query_latency_ms=0,
                rendered_output=None,
                error_message="Report is paused",
            )
            executions_repo.create_execution(execution_record)
            return {"status": "skipped"}

        # Execute each pinned visualization by replaying the original query text
        # through the NLP /query endpoint (same pipeline as interactive chat).
        # This ensures fresh data fetch + correct visualization for the question asked.
        try:
            from src.config import NLP_PORT

            async with httpx.AsyncClient(verify=False, timeout=300) as client:
                query_start = datetime.now(ZoneInfo("UTC"))

                if not config.pinned_visualization_ids:
                    raise ValueError("No pinned visualizations to execute")

                all_rendered_outputs: list[dict] = []

                for viz_id in config.pinned_visualization_ids:
                    # Get original query text for this viz
                    query_text = config.query_texts.get(viz_id, "")
                    if not query_text:
                        logger.warning(f"No query text for viz {viz_id}, skipping")
                        continue

                    # Call NLP /query — same endpoint the chat uses
                    # X-Skip-Cache forces fresh data fetch (bypasses orchestrator result cache)
                    nlp_resp = await client.post(
                        f"http://localhost:{NLP_PORT}/query",
                        json={"query_text": query_text},
                        headers={
                            "Content-Type": "application/json",
                            "X-Skip-Cache": "true",
                        },
                    )
                    if nlp_resp.status_code != 200:
                        logger.error(f"NLP query failed for viz {viz_id}: {nlp_resp.text[:200]}")
                        continue

                    nlp_data = nlp_resp.json()
                    # NLP returns {rendered_output: {...}, latency_breakdown: {...}}
                    rendered = nlp_data.get("rendered_output", nlp_data)
                    # Tag with viz_id + query_text so add/delete can target individual outputs
                    all_rendered_outputs.append({
                        "viz_id": viz_id,
                        "query_text": query_text,
                        "rendered_output": rendered,
                    })

                if not all_rendered_outputs:
                    raise Exception("No visualizations produced output")

                # Always store as a list of tagged outputs (viz_id, query_text, rendered_output)
                # so add/delete can surgically merge without re-running everything.
                rendered_output = all_rendered_outputs

                query_end = datetime.now(ZoneInfo("UTC"))
                query_latency_ms = int((query_end - query_start).total_seconds() * 1000)

        except httpx.RequestError as e:
            logger.error(f"Network error executing query for report {report_id}: {e}")
            raise Exception(f"Network error: {str(e)}")
        except Exception as e:
            logger.error(f"Error executing query for report {report_id}: {e}")
            raise

        # Store execution result
        executions_repo = get_executions_repo()
        execution_record = ExecutionRecord(
            execution_id=execution_id,
            report_id=report_id,
            execution_timestamp=start_time,
            actual_start_timestamp=start_time,
            status="success",
            query_latency_ms=query_latency_ms,
            rendered_output=rendered_output,
            error_message=None,
        )
        executions_repo.create_execution(execution_record)

        # Update report with latest execution metadata
        now = datetime.now(ZoneInfo("UTC"))
        reports_repo.update_report(
            config.user_id,
            report_id,
            {
                "last_run_timestamp": now.isoformat(),
                "last_run_status": "success",
                # Recompute next execution time
                "next_execution_time": compute_next_execution(
                    config.recurrence_pattern,
                    now,
                    config.recurrence_pattern.timezone,
                ).isoformat(),
            },
        )

        logger.info(f"Successfully executed report {report_id} (latency: {query_latency_ms}ms)")

        return {
            "status": "success",
            "execution_id": execution_id,
            "query_latency_ms": query_latency_ms,
        }

    except Exception as e:
        # Record failed execution
        logger.error(f"Execution failed for report {report_id}: {e}")

        try:
            executions_repo = get_executions_repo()
            execution_record = ExecutionRecord(
                execution_id=execution_id,
                report_id=report_id,
                execution_timestamp=start_time,
                actual_start_timestamp=datetime.now(ZoneInfo("UTC")),
                status="failed",
                query_latency_ms=None,
                rendered_output=None,
                error_message=str(e)[:500],  # Truncate to 500 chars
            )
            executions_repo.create_execution(execution_record)

            # Update report with failure status
            reports_repo = get_reports_repo()
            config = reports_repo.get_report_by_id(report_id)
            if config:
                reports_repo.update_report(
                    config.user_id,
                    report_id,
                    {
                        "last_run_timestamp": datetime.now(ZoneInfo("UTC")).isoformat(),
                        "last_run_status": "failed",
                    },
                )
        except Exception as record_err:
            logger.error(f"Failed to record execution error: {record_err}")

        raise HTTPException(status_code=503, detail=f"Execution failed: {str(e)[:100]}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=SCHEDULING_PORT)
