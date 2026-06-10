"""Pydantic models for Execution Plan generation and execution.

Defines the structure for sub-tasks, merge strategies, and complete
execution plans produced by the Query_Planner_Agent. These models
support JSON serialization round-trip consistency for logging, debugging,
and replay purposes.

Requirements: 5.1, 5.6
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SubTask(BaseModel):
    """A single data retrieval sub-task within an execution plan.

    Represents one query against a specific data source connector,
    with optional dependencies on other sub-tasks for sequential execution.
    """

    task_id: str
    source_id: str
    connector_type: Literal["sql", "dynamodb", "csv", "logs", "s3_json"]
    query_params: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)


class MergeStrategy(BaseModel):
    """How to combine results from multiple sub-tasks.

    Defines the method used by the Result_Assembler to merge connector
    results into a single unified response.
    """

    method: Literal["union", "join", "aggregate", "single"]
    join_key: str | None = None
    aggregate_columns: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    """Complete plan for a multi-source query.

    Produced by the Query_Planner_Agent after reasoning about the ontology
    and source registry. Contains the full set of sub-tasks to execute,
    their dependencies, and the strategy for merging results.
    """

    plan_id: str
    query_text: str
    sub_tasks: list[SubTask] = Field(min_length=1)
    merge_strategy: MergeStrategy
    created_at: datetime
    reasoning: str = ""
