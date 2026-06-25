"""S3-backed repository for scheduled reports configuration.

Provides CRUD operations for scheduled report configurations stored in S3.
Maintains an index file for fast user-based lookups.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from src.config import S3_BUCKET, get_s3_client
from src.models.scheduled_reports import ScheduledReportConfig

logger = logging.getLogger(__name__)

# S3 key patterns
S3_SCHEDULED_REPORTS_PREFIX = "scheduled-reports/"
S3_REPORTS_INDEX_KEY = f"{S3_SCHEDULED_REPORTS_PREFIX}index.json"
S3_REPORT_CONFIG_TEMPLATE = f"{S3_SCHEDULED_REPORTS_PREFIX}{{user_id}}/{{report_id}}.json"


class ScheduledReportsRepository:
    """Repository for managing scheduled report configurations in S3."""

    def __init__(self, bucket: str = S3_BUCKET):
        """Initialize the repository.

        Args:
            bucket: S3 bucket name (defaults to configured bucket)
        """
        self.bucket = bucket
        self.s3_client = get_s3_client()

    def create_report(self, config: ScheduledReportConfig) -> None:
        """Create a new scheduled report configuration.

        Args:
            config: ScheduledReportConfig object to persist

        Raises:
            Exception: If S3 write fails
        """
        # Serialize config to JSON
        config_dict = config.model_dump(mode="json")
        config_json = json.dumps(config_dict, indent=2)

        # Store config in S3
        config_key = S3_REPORT_CONFIG_TEMPLATE.format(
            user_id=config.user_id,
            report_id=str(config.report_id),
        )
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=config_key,
            Body=config_json,
            ContentType="application/json",
        )
        logger.info(f"Created scheduled report: user={config.user_id}, report={config.report_id}")

        # Update index
        self._add_to_index(config.user_id, str(config.report_id))

    def get_report(self, user_id: str, report_id: str) -> Optional[ScheduledReportConfig]:
        """Retrieve a scheduled report by ID (with user_id for access control).

        Args:
            user_id: User ID (for access control)
            report_id: Report UUID

        Returns:
            ScheduledReportConfig if found, None otherwise
        """
        config_key = S3_REPORT_CONFIG_TEMPLATE.format(user_id=user_id, report_id=report_id)

        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=config_key)
            config_json = response["Body"].read().decode("utf-8")
            config_dict = json.loads(config_json)
            return ScheduledReportConfig(**config_dict)
        except self.s3_client.exceptions.NoSuchKey:
            logger.debug(f"Report not found: user={user_id}, report={report_id}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving report: {e}")
            raise

    def get_report_by_id(self, report_id: str) -> Optional[ScheduledReportConfig]:
        """Retrieve a scheduled report by ID only (internal use, no user_id check).

        This method is used internally by Step Functions execution to fetch reports.
        It searches all users' report directories.

        Args:
            report_id: Report UUID

        Returns:
            ScheduledReportConfig if found, None otherwise
        """
        index = self._load_index()

        # Search all users for this report
        for user_id, report_ids in index.items():
            if report_id in report_ids:
                return self.get_report(user_id, report_id)

        logger.debug(f"Report not found: report_id={report_id}")
        return None

    def get_reports_by_user(self, user_id: str) -> list[ScheduledReportConfig]:
        """Retrieve all scheduled reports for a user.

        Args:
            user_id: User ID

        Returns:
            List of ScheduledReportConfig objects for the user
        """
        index = self._load_index()
        report_ids = index.get(user_id, [])

        reports = []
        for report_id in report_ids:
            config = self.get_report(user_id, report_id)
            if config and config.deleted_at is None:  # Skip soft-deleted reports
                reports.append(config)

        return reports

    def update_report(self, user_id: str, report_id: str, updates: dict) -> ScheduledReportConfig:
        """Update a scheduled report configuration.

        Args:
            user_id: User ID (for access control)
            report_id: Report UUID
            updates: Dictionary of fields to update

        Returns:
            Updated ScheduledReportConfig

        Raises:
            ValueError: If report not found
            Exception: If S3 write fails
        """
        # Get current config
        current_config = self.get_report(user_id, report_id)
        if not current_config:
            raise ValueError(f"Report not found: {report_id}")

        # Apply updates
        config_dict = current_config.model_dump(mode="json")
        config_dict.update(updates)
        config_dict["updated_at"] = datetime.utcnow().isoformat()

        updated_config = ScheduledReportConfig(**config_dict)

        # Persist updated config
        config_json = json.dumps(updated_config.model_dump(mode="json"), indent=2)
        config_key = S3_REPORT_CONFIG_TEMPLATE.format(user_id=user_id, report_id=report_id)
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=config_key,
            Body=config_json,
            ContentType="application/json",
        )
        logger.info(f"Updated scheduled report: user={user_id}, report={report_id}")

        return updated_config

    def soft_delete_report(self, user_id: str, report_id: str) -> None:
        """Soft-delete a scheduled report (mark with deleted_at timestamp).

        Args:
            user_id: User ID (for access control)
            report_id: Report UUID

        Raises:
            ValueError: If report not found
        """
        config = self.get_report(user_id, report_id)
        if not config:
            raise ValueError(f"Report not found: {report_id}")

        # Set deleted_at timestamp
        self.update_report(user_id, report_id, {"deleted_at": datetime.utcnow().isoformat()})
        logger.info(f"Soft-deleted scheduled report: user={user_id}, report={report_id}")

    def _load_index(self) -> dict[str, list[str]]:
        """Load the user → report mappings index from S3.

        Returns:
            Dictionary mapping user_id to list of report IDs
        """
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=S3_REPORTS_INDEX_KEY)
            index_json = response["Body"].read().decode("utf-8")
            return json.loads(index_json)
        except self.s3_client.exceptions.NoSuchKey:
            # Index doesn't exist yet, return empty
            return {}
        except Exception as e:
            logger.error(f"Error loading index: {e}")
            return {}

    def _save_index(self, index: dict[str, list[str]]) -> None:
        """Save the user → report mappings index to S3.

        Args:
            index: Dictionary mapping user_id to list of report IDs
        """
        try:
            index_json = json.dumps(index, indent=2)
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=S3_REPORTS_INDEX_KEY,
                Body=index_json,
                ContentType="application/json",
            )
        except Exception as e:
            logger.error(f"Error saving index: {e}")
            raise

    def _add_to_index(self, user_id: str, report_id: str) -> None:
        """Add a report to the user index.

        Args:
            user_id: User ID
            report_id: Report UUID
        """
        index = self._load_index()
        if user_id not in index:
            index[user_id] = []
        if report_id not in index[user_id]:
            index[user_id].append(report_id)
        self._save_index(index)

    def _remove_from_index(self, user_id: str, report_id: str) -> None:
        """Remove a report from the user index.

        Args:
            user_id: User ID
            report_id: Report UUID
        """
        index = self._load_index()
        if user_id in index and report_id in index[user_id]:
            index[user_id].remove(report_id)
            if not index[user_id]:  # Remove user if no more reports
                del index[user_id]
            self._save_index(index)
