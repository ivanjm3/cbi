"""S3-backed repository for scheduled report execution records.

Provides operations for storing and retrieving execution records (history) for
scheduled reports. Records are stored as JSON files in S3 with timestamp-based
naming for natural sorting.
"""

import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from src.config import S3_BUCKET, get_s3_client
from src.models.scheduled_reports import ExecutionRecord

logger = logging.getLogger(__name__)

# S3 key patterns
S3_EXECUTIONS_PREFIX = "scheduled-reports/executions/"
S3_EXECUTION_RECORD_TEMPLATE = f"{S3_EXECUTIONS_PREFIX}{{report_id}}/{{execution_timestamp}}.json"


class ExecutionRecordsRepository:
    """Repository for managing scheduled report execution records in S3."""

    def __init__(self, bucket: str = S3_BUCKET):
        """Initialize the repository.

        Args:
            bucket: S3 bucket name (defaults to configured bucket)
        """
        self.bucket = bucket
        self.s3_client = get_s3_client()

    def create_execution(self, record: ExecutionRecord) -> None:
        """Create a new execution record.

        Args:
            record: ExecutionRecord object to persist

        Raises:
            Exception: If S3 write fails
        """
        # Serialize record to JSON
        record_dict = record.model_dump(mode="json")
        record_json = json.dumps(record_dict, indent=2)

        # Store record in S3 with ISO8601 timestamp as key for sorting
        execution_key = S3_EXECUTION_RECORD_TEMPLATE.format(
            report_id=str(record.report_id),
            execution_timestamp=record.execution_timestamp.isoformat(),
        )
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=execution_key,
            Body=record_json,
            ContentType="application/json",
        )
        logger.info(
            f"Created execution record: report={record.report_id}, "
            f"execution_timestamp={record.execution_timestamp}"
        )

    def get_execution_by_id(
        self, report_id: str, execution_timestamp: str
    ) -> Optional[ExecutionRecord]:
        """Retrieve a specific execution record by report ID and timestamp.

        Args:
            report_id: Report UUID
            execution_timestamp: ISO8601 timestamp string

        Returns:
            ExecutionRecord if found, None otherwise
        """
        execution_key = S3_EXECUTION_RECORD_TEMPLATE.format(
            report_id=report_id,
            execution_timestamp=execution_timestamp,
        )

        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=execution_key)
            record_json = response["Body"].read().decode("utf-8")
            record_dict = json.loads(record_json)
            return ExecutionRecord(**record_dict)
        except self.s3_client.exceptions.NoSuchKey:
            logger.debug(f"Execution record not found: {execution_key}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving execution record: {e}")
            raise

    def get_executions_by_report(
        self, report_id: str, page: int = 1, page_size: int = 10
    ) -> tuple[list[ExecutionRecord], int]:
        """Retrieve paginated execution history for a report.

        Records are sorted by execution_timestamp in descending order (newest first).

        Args:
            report_id: Report UUID
            page: Page number (1-indexed)
            page_size: Number of records per page

        Returns:
            Tuple of (list of ExecutionRecords, total count)
        """
        try:
            # List all execution record objects for this report
            prefix = f"{S3_EXECUTIONS_PREFIX}{report_id}/"
            response = self.s3_client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)

            if "Contents" not in response:
                # No executions for this report
                return [], 0

            # Extract S3 keys and sort by timestamp descending (newest first)
            keys = [obj["Key"] for obj in response["Contents"]]
            keys.sort(reverse=True)  # ISO8601 timestamps sort correctly as strings

            total_count = len(keys)

            # Apply pagination
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_keys = keys[start_idx:end_idx]

            # Retrieve records for this page
            records = []
            for key in page_keys:
                try:
                    response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                    record_json = response["Body"].read().decode("utf-8")
                    record_dict = json.loads(record_json)
                    record = ExecutionRecord(**record_dict)
                    records.append(record)
                except Exception as e:
                    logger.error(f"Error retrieving execution record from {key}: {e}")
                    continue

            return records, total_count

        except Exception as e:
            logger.error(f"Error listing execution records for report {report_id}: {e}")
            raise

    def get_all_executions_by_report(self, report_id: str) -> list[ExecutionRecord]:
        """Retrieve all execution records for a report (unpagin ated).

        Use with caution for reports with large execution histories.

        Args:
            report_id: Report UUID

        Returns:
            List of all ExecutionRecords for the report, sorted by timestamp descending
        """
        try:
            # List all execution record objects for this report
            prefix = f"{S3_EXECUTIONS_PREFIX}{report_id}/"
            response = self.s3_client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)

            if "Contents" not in response:
                # No executions for this report
                return []

            # Extract S3 keys and sort by timestamp descending
            keys = [obj["Key"] for obj in response["Contents"]]
            keys.sort(reverse=True)

            # Retrieve all records
            records = []
            for key in keys:
                try:
                    response = self.s3_client.get_object(Bucket=self.bucket, Key=key)
                    record_json = response["Body"].read().decode("utf-8")
                    record_dict = json.loads(record_json)
                    record = ExecutionRecord(**record_dict)
                    records.append(record)
                except Exception as e:
                    logger.error(f"Error retrieving execution record from {key}: {e}")
                    continue

            return records

        except Exception as e:
            logger.error(f"Error listing execution records for report {report_id}: {e}")
            raise
