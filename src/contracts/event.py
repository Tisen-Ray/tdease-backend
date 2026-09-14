"""
Event Stream — an immutable, append-only event log.

Source of truth: events.jsonl (one JSON object per line, append-only).
SQLite state can be rebuilt from this file. SSE streams directly from its tail.

Every event contains:
  schema_version, seq, timestamp, run_id, type, level, message,
  runtime_ref, data

seq increases monotonically; an event is published over SSE only after
append + fsync.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from .enums import EventType, RunExecutionMode
from .lifecycle_declaration import LIFECYCLE_SCHEMA_VERSION


class RuntimeRef(BaseModel):
    """Execution context reference — for diagnostic correlation, not a persistent entity."""

    task_id: Optional[str] = Field(default=None, description="Task identifier")
    step_label: Optional[str] = Field(
        default=None, description="Human-readable step name"
    )


class Event(BaseModel):
    """
    One line of events.jsonl. All events share this structure.

    fields:
      schema_version: event contract version
      seq: monotonically increasing sequence number (per run)
      timestamp: UTC occurrence time
      run_id: owning Run
      type: EventType enum value
      level: info | warn | error
      message: human-readable summary
      runtime_ref: execution context (task/step)
      data: payload varying by type
    """

    schema_version: int = Field(
        default=LIFECYCLE_SCHEMA_VERSION,
        ge=LIFECYCLE_SCHEMA_VERSION,
        le=LIFECYCLE_SCHEMA_VERSION,
        description="Event schema version",
    )
    run_id: str = Field(description="Owning Run")
    seq: int = Field(
        description="Event sequence number, starting at 1, monotonically increasing",
        ge=1,
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC occurrence time",
    )
    type: EventType = Field(description="Event type")
    level: str = Field(default="info", description="info | warn | error")
    message: str = Field(default="", description="Human-readable summary")
    runtime_ref: Optional[RuntimeRef] = Field(
        default=None, description="Execution context reference"
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="Payload varying by type"
    )


class EventBatch(BaseModel):
    """One batch of events pushed over SSE."""

    events: list[Event] = Field(description="Ascending by seq")
    run_id: str
    last_seq: int = Field(description="Max seq in this batch → Last-Event-ID")


# --- Per-product event data schemas ---


class RunSubmittedData(BaseModel):
    """Records the creation of a Run identity and its initial revision."""

    revision_id: str
    idempotency_key: str
    workspace_tree_hash: str
    user_id: str
    cores: int
    workflow_steps: int = Field(default=0)


class RunQueueRequestedData(BaseModel):
    """Requests one serialized execution of an immutable revision."""

    revision_id: str
    mode: RunExecutionMode


class RunStartedData(BaseModel):
    revision_id: str
    mode: RunExecutionMode
    pid: int
    worker_id: str


class TaskStartedData(BaseModel):
    task_id: str
    step: str = Field(description="Human-readable step name")
    command: str = Field(default="", description="Redacted command")


class TaskProgressData(BaseModel):
    task_id: str
    done: int
    total: int
    percent: float = Field(ge=0.0, le=100.0)


class TaskSucceededData(BaseModel):
    task_id: str
    duration_seconds: float
    output_files: list[str] = Field(default_factory=list)


class TaskFailedData(BaseModel):
    task_id: str
    exit_code: int
    duration_seconds: float
    error_message: str = Field(default="")


class RunTerminatedData(BaseModel):
    revision_id: str
    exit_code: Optional[int] = Field(default=None)
    run_time_seconds: float
    total_tasks: int = Field(default=0)
    succeeded_tasks: int = Field(default=0)
    failed_tasks: int = Field(default=0)


class RuntimeMessageData(BaseModel):
    """Diagnostic information that cannot be structured."""

    level: str = Field(default="debug", description="debug | info | warn | error")
    message: str
    runtime_ref: Optional[RuntimeRef] = Field(default=None)
