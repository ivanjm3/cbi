"""Pydantic data models for the Scheduled Reports feature.

These models define the core data structures for scheduled report configurations,
recurrence patterns, and execution records.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RecurrencePattern(BaseModel):
    """Recurrence schedule specification for a scheduled report.
    
    Supports predefined patterns (daily, weekday, weekly, monthly) and custom intervals.
    """
    type: Literal["daily", "weekday", "weekly", "monthly", "custom"]
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    time_hour: int = Field(default=9, ge=0, le=23)
    time_minute: int = Field(default=0, ge=0, le=59)
    timezone: str = Field(default="UTC")
    custom_interval: int | None = Field(default=None, ge=1, le=365)
    custom_unit: Literal["days", "weeks", "months"] | None = None

    @field_validator("day_of_week")
    @classmethod
    def validate_day_of_week(cls, v: int | None) -> int | None:
        """Validate day_of_week is in range 0-6 (Sunday=0, Saturday=6)."""
        if v is not None and (v < 0 or v > 6):
            raise ValueError("day_of_week must be between 0 and 6 (0=Sunday, 6=Saturday)")
        return v

    @field_validator("day_of_month")
    @classmethod
    def validate_day_of_month(cls, v: int | None) -> int | None:
        """Validate day_of_month is in range 1-31."""
        if v is not None and (v < 1 or v > 31):
            raise ValueError("day_of_month must be between 1 and 31")
        return v

    @field_validator("time_hour")
    @classmethod
    def validate_time_hour(cls, v: int) -> int:
        """Validate time_hour is in range 0-23 (24-hour format)."""
        if v < 0 or v > 23:
            raise ValueError("time_hour must be between 0 and 23")
        return v

    @field_validator("time_minute")
    @classmethod
    def validate_time_minute(cls, v: int) -> int:
        """Validate time_minute is in range 0-59."""
        if v < 0 or v > 59:
            raise ValueError("time_minute must be between 0 and 59")
        return v


class ScheduledReportConfig(BaseModel):
    """Full scheduled report configuration stored in DynamoDB.
    
    Represents a user's scheduled report with all metadata, recurrence settings,
    and execution tracking.
    """
    report_id: UUID
    user_id: str
    title: str = Field(max_length=255, min_length=1)
    description: str = Field(default="", max_length=1000)
    original_chat_id: str
    pinned_visualization_ids: list[str] = Field(min_length=1)
    structured_intents: dict[str, dict]  # viz_id -> StructuredIntent as dict
    query_texts: dict[str, str] = {}  # viz_id -> original query text for replay
    recurrence_pattern: RecurrencePattern
    is_active: bool = Field(default=True)
    schedule_arn: str | None = None
    next_execution_time: datetime | None = None
    last_run_timestamp: datetime | None = None
    last_run_status: Literal["success", "failed", "retrying", "active", "paused"] | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty and not too long."""
        if not v or not v.strip():
            raise ValueError("title cannot be empty")
        if len(v) > 255:
            raise ValueError("title cannot exceed 255 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Validate description doesn't exceed maximum length."""
        if len(v) > 1000:
            raise ValueError("description cannot exceed 1000 characters")
        return v


class CreateReportRequest(BaseModel):
    """Request body for creating a new scheduled report.
    
    Captured from the user when they initiate report scheduling.
    """
    title: str = Field(max_length=255, min_length=1)
    description: str = Field(default="", max_length=1000)
    original_chat_id: str
    pinned_visualization_ids: list[str] = Field(min_length=1)
    recurrence_pattern: RecurrencePattern
    structured_intents: dict[str, dict] | None = None  # viz_id -> real StructuredIntent from frontend
    query_texts: dict[str, str] | None = None  # viz_id -> original query text for replay

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate title is not empty and not too long."""
        if not v or not v.strip():
            raise ValueError("title cannot be empty")
        if len(v) > 255:
            raise ValueError("title cannot exceed 255 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str) -> str:
        """Validate description doesn't exceed maximum length."""
        if len(v) > 1000:
            raise ValueError("description cannot exceed 1000 characters")
        return v


class UpdateReportRequest(BaseModel):
    """Request body for updating an existing scheduled report.
    
    All fields are optional to support partial updates.
    """
    title: str | None = Field(default=None, max_length=255, min_length=1)
    description: str | None = Field(default=None, max_length=1000)
    recurrence_pattern: RecurrencePattern | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        """Validate title if provided."""
        if v is not None:
            if not v or not v.strip():
                raise ValueError("title cannot be empty")
            if len(v) > 255:
                raise ValueError("title cannot exceed 255 characters")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: str | None) -> str | None:
        """Validate description if provided."""
        if v is not None and len(v) > 1000:
            raise ValueError("description cannot exceed 1000 characters")
        return v


class ExecutionRecord(BaseModel):
    """A single execution record for a scheduled report.
    
    Represents one run of a scheduled report, tracking status, timing, and results.
    """
    execution_id: UUID
    report_id: UUID
    execution_timestamp: datetime
    actual_start_timestamp: datetime
    actual_end_timestamp: datetime | None = None
    status: Literal["success", "failed", "retrying", "skipped"]
    query_latency_ms: int | None = None
    rendered_output: dict | list | None = None  # Full RenderedOutput JSON (single dict or array of dicts)
    rendered_output_s3_key: str | None = None
    error_message: str | None = None
    retry_count: int = Field(default=0, ge=0)
    step_functions_execution_arn: str | None = None
