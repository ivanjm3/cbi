"""Local cron scheduler using APScheduler.

Replaces EventBridge Scheduler for environments where IAM PassRole
is unavailable. Reads scheduled report configs from S3, creates
APScheduler CronTrigger jobs that call execute_scheduled_report directly.

Starts automatically when scheduling_api boots. Syncs jobs on report
create/update/pause/resume/delete.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the singleton APScheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


def start_scheduler() -> None:
    """Start the local scheduler (call once at app startup)."""
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Local APScheduler started")


def stop_scheduler() -> None:
    """Shut down the local scheduler gracefully."""
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Local APScheduler stopped")


def _build_cron_trigger(recurrence_pattern: dict) -> CronTrigger:
    """Convert a RecurrencePattern dict to an APScheduler CronTrigger.

    Args:
        recurrence_pattern: Dict with type, time_hour, time_minute, timezone,
                           day_of_week, day_of_month, custom_interval, custom_unit.

    Returns:
        CronTrigger configured for the recurrence.
    """
    pat_type = recurrence_pattern.get("type", "daily")
    hour = recurrence_pattern.get("time_hour", 9)
    minute = recurrence_pattern.get("time_minute", 0)
    tz = recurrence_pattern.get("timezone", "UTC")

    if pat_type == "daily":
        return CronTrigger(hour=hour, minute=minute, timezone=tz)
    elif pat_type == "weekday":
        return CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone=tz)
    elif pat_type == "weekly":
        dow = recurrence_pattern.get("day_of_week", 1)  # 0=Sun..6=Sat
        # APScheduler: 0=Mon..6=Sun. Convert from JS convention (0=Sun).
        ap_dow = (dow - 1) % 7 if dow > 0 else 6
        return CronTrigger(day_of_week=ap_dow, hour=hour, minute=minute, timezone=tz)
    elif pat_type == "monthly":
        dom = recurrence_pattern.get("day_of_month", 1)
        return CronTrigger(day=dom, hour=hour, minute=minute, timezone=tz)
    else:
        # Custom / fallback → daily
        return CronTrigger(hour=hour, minute=minute, timezone=tz)


async def _execute_report_job(report_id: str) -> None:
    """APScheduler job: executes a scheduled report.

    Calls the execute_scheduled_report endpoint handler directly (in-process).
    """
    logger.info(f"Local cron firing for report {report_id}")
    try:
        # Import here to avoid circular imports
        from src.services.scheduling_api import execute_scheduled_report

        result = await execute_scheduled_report({"report_id": report_id})
        logger.info(f"Local cron completed for report {report_id}: {result.get('status')}")
    except Exception as e:
        logger.error(f"Local cron failed for report {report_id}: {e}")


def add_job(report_id: str, recurrence_pattern: dict) -> None:
    """Add or replace a cron job for a report.

    Args:
        report_id: Report UUID string.
        recurrence_pattern: RecurrencePattern as dict.
    """
    scheduler = get_scheduler()
    job_id = f"report-{report_id}"

    # Remove existing job if any
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    trigger = _build_cron_trigger(recurrence_pattern)
    scheduler.add_job(
        _execute_report_job,
        trigger=trigger,
        id=job_id,
        args=[report_id],
        replace_existing=True,
        misfire_grace_time=300,  # 5 min grace
    )
    logger.info(f"Scheduled local cron job: {job_id} → {trigger}")


def remove_job(report_id: str) -> None:
    """Remove a cron job for a report (pause/delete)."""
    scheduler = get_scheduler()
    job_id = f"report-{report_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)
        logger.info(f"Removed local cron job: {job_id}")


def pause_job(report_id: str) -> None:
    """Pause a cron job."""
    scheduler = get_scheduler()
    job_id = f"report-{report_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.pause_job(job_id)
        logger.info(f"Paused local cron job: {job_id}")


def resume_job(report_id: str) -> None:
    """Resume a paused cron job."""
    scheduler = get_scheduler()
    job_id = f"report-{report_id}"
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.resume_job(job_id)
        logger.info(f"Resumed local cron job: {job_id}")


async def sync_all_jobs() -> None:
    """Load all active reports from S3, create cron jobs for each.

    Call once at startup to reconstruct schedule from persisted configs.
    """
    try:
        from src.services.scheduled_reports_repository import ScheduledReportsRepository

        repo = ScheduledReportsRepository()
        # Load index to get all reports
        from src.config import S3_BUCKET, get_s3_client
        import json

        s3 = get_s3_client()
        try:
            resp = s3.get_object(
                Bucket=S3_BUCKET,
                Key="scheduled-reports-index.json",
            )
            index = json.loads(resp["Body"].read().decode("utf-8"))
        except Exception:
            logger.info("No scheduled-reports-index.json found, skipping sync")
            return

        count = 0
        for user_id, report_ids in index.items():
            for rid in report_ids:
                try:
                    config = repo.get_report(user_id, rid)
                    if config and config.is_active and not config.deleted_at:
                        add_job(str(config.report_id), config.recurrence_pattern.model_dump())
                        count += 1
                except Exception as e:
                    logger.warning(f"Could not load report {rid}: {e}")

        logger.info(f"Local scheduler synced {count} active jobs")
    except Exception as e:
        logger.error(f"Failed to sync scheduler jobs: {e}")
