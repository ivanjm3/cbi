"""EventBridge Scheduler Manager for scheduled reports.

Manages AWS EventBridge Scheduler rules for triggering Step Functions executions.
Each scheduled report gets a scheduler rule that passes the report_id as input.
"""

import logging
from typing import Optional

import boto3

from src.config import get_boto3_session
from src.models.scheduled_reports import RecurrencePattern
from src.services.recurrence_calculator import serialize_recurrence

logger = logging.getLogger(__name__)

# Step Functions state machine ARN (will be provided at initialization)
_STATE_MACHINE_ARN: Optional[str] = None


class SchedulerManager:
    """Manages EventBridge Scheduler rules for scheduled reports."""

    def __init__(self, state_machine_arn: str):
        """Initialize the SchedulerManager.

        Args:
            state_machine_arn: ARN of the Step Functions state machine to invoke
        """
        self.state_machine_arn = state_machine_arn
        session = get_boto3_session()
        self.scheduler_client = session.client("scheduler", region_name="us-east-1", verify=False)

    def create_schedule(self, report_id: str, pattern: RecurrencePattern) -> str:
        """Create an EventBridge Scheduler rule for a report.

        Args:
            report_id: Unique report identifier
            pattern: RecurrencePattern specifying the schedule

        Returns:
            The ARN of the created schedule rule

        Raises:
            Exception: If schedule creation fails
        """
        schedule_name = self._get_schedule_name(report_id)
        schedule_expression = serialize_recurrence(pattern)

        try:
            response = self.scheduler_client.create_schedule(
                Name=schedule_name,
                ScheduleExpression=schedule_expression,
                FlexibleTimeWindow={"Mode": "OFF"},
                State="ENABLED",
                Target={
                    "Arn": self.state_machine_arn,
                    "RoleArn": self._get_scheduler_role_arn(),
                    "Input": self._build_step_functions_input(report_id),
                },
                Description=f"Scheduled report execution for {report_id}",
            )
            schedule_arn = response.get("ScheduleArn")
            logger.info(f"Created schedule: {schedule_name} → {schedule_arn}")
            return schedule_arn
        except Exception as e:
            logger.error(f"Failed to create schedule for {report_id}: {e}")
            raise

    def update_schedule(self, report_id: str, pattern: RecurrencePattern) -> None:
        """Update an existing EventBridge Scheduler rule.

        Args:
            report_id: Unique report identifier
            pattern: New RecurrencePattern

        Raises:
            Exception: If schedule update fails
        """
        schedule_name = self._get_schedule_name(report_id)
        schedule_expression = serialize_recurrence(pattern)

        try:
            self.scheduler_client.update_schedule(
                Name=schedule_name,
                ScheduleExpression=schedule_expression,
                FlexibleTimeWindow={"Mode": "OFF"},
                State="ENABLED",
                Target={
                    "Arn": self.state_machine_arn,
                    "RoleArn": self._get_scheduler_role_arn(),
                    "Input": self._build_step_functions_input(report_id),
                },
            )
            logger.info(f"Updated schedule: {schedule_name}")
        except Exception as e:
            logger.error(f"Failed to update schedule for {report_id}: {e}")
            raise

    def disable_schedule(self, report_id: str) -> None:
        """Disable (pause) an EventBridge Scheduler rule.

        The rule is not deleted, just disabled. Can be re-enabled later.

        Args:
            report_id: Unique report identifier

        Raises:
            Exception: If schedule disable fails
        """
        schedule_name = self._get_schedule_name(report_id)

        try:
            self.scheduler_client.update_schedule(
                Name=schedule_name,
                State="DISABLED",
                FlexibleTimeWindow={"Mode": "OFF"},
                ScheduleExpression="rate(1 day)",  # Placeholder; ignored when State=DISABLED
                Target={
                    "Arn": self.state_machine_arn,
                    "RoleArn": self._get_scheduler_role_arn(),
                },
            )
            logger.info(f"Disabled schedule: {schedule_name}")
        except Exception as e:
            logger.error(f"Failed to disable schedule for {report_id}: {e}")
            raise

    def enable_schedule(self, report_id: str) -> None:
        """Enable a previously disabled EventBridge Scheduler rule.

        Args:
            report_id: Unique report identifier

        Raises:
            Exception: If schedule enable fails
        """
        schedule_name = self._get_schedule_name(report_id)

        try:
            self.scheduler_client.update_schedule(
                Name=schedule_name,
                State="ENABLED",
                FlexibleTimeWindow={"Mode": "OFF"},
                ScheduleExpression="rate(1 day)",  # Placeholder; ignored for enable
                Target={
                    "Arn": self.state_machine_arn,
                    "RoleArn": self._get_scheduler_role_arn(),
                },
            )
            logger.info(f"Enabled schedule: {schedule_name}")
        except Exception as e:
            logger.error(f"Failed to enable schedule for {report_id}: {e}")
            raise

    def delete_schedule(self, report_id: str) -> None:
        """Permanently delete an EventBridge Scheduler rule.

        Args:
            report_id: Unique report identifier

        Raises:
            Exception: If schedule deletion fails
        """
        schedule_name = self._get_schedule_name(report_id)

        try:
            self.scheduler_client.delete_schedule(Name=schedule_name)
            logger.info(f"Deleted schedule: {schedule_name}")
        except self.scheduler_client.exceptions.ResourceNotFoundException:
            logger.warning(f"Schedule not found (may have been deleted): {schedule_name}")
        except Exception as e:
            logger.error(f"Failed to delete schedule for {report_id}: {e}")
            raise

    def _get_schedule_name(self, report_id: str) -> str:
        """Generate a consistent schedule name from report ID.

        Args:
            report_id: Unique report identifier

        Returns:
            Schedule name (alphanumeric, hyphens allowed)
        """
        # EventBridge Scheduler names must be alphanumeric, hyphens, underscores
        # Remove any invalid characters and prefix with 'report-'
        safe_id = "".join(c if c.isalnum() or c in "-_" else "-" for c in report_id)
        return f"scheduled-report-{safe_id}"

    def _build_step_functions_input(self, report_id: str) -> str:
        """Build the JSON input for Step Functions execution.

        Args:
            report_id: Unique report identifier

        Returns:
            JSON string to pass to Step Functions
        """
        import json

        input_dict = {
            "report_id": report_id,
        }
        return json.dumps(input_dict)

    def _get_scheduler_role_arn(self) -> str:
        """Get the IAM role ARN for EventBridge Scheduler.

        In production, this would be fetched from configuration or created
        if it doesn't exist. For MVP, we'll assume it exists.

        Returns:
            IAM role ARN for EventBridge Scheduler
        """
        # TODO: In production, fetch from configuration or create if missing
        # For now, use a placeholder that should be configured via environment
        import os

        arn = os.environ.get(
            "EVENTBRIDGE_SCHEDULER_ROLE_ARN",
            "arn:aws:iam::654654478821:role/eventbridge-scheduler-role",
        )
        return arn
