"""
TDEase-nexus status enums — the system's single lifecycle field and its
auxiliary types.

Design constraints (FIRST-PRINCIPLES-AUDIT.md §2):
- The whole system has exactly one lifecycle field: runs.status
- No sub-states, no state-transition diagram
- Transitions are driven by process lifecycle, not business code
"""

from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    """
    Run lifecycle — the system's only lifecycle axis.

    QUEUED    → submitted, waiting for a worker to claim it
    RUNNING   → claimed by a worker, executing in the Execution Runtime
    SUCCEEDED → normal exit
    FAILED    → abnormal exit or system error
    CANCELLED → actively cancelled by user/system

    Status is rebuildable: after deleting SQLite, scanning the final events in
    events.jsonl restores it.
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RunExecutionMode(str, Enum):
    """How one immutable Run revision is requested for execution."""

    EXECUTE = "execute"
    CONTINUE = "continue"


class EventType(str, Enum):
    """
    Event types — the type field of each line in events.jsonl.

    Events are append-only, monotonically increasing by seq. Clients resume
    via Last-Event-ID.

    Product events (stable schema, consumed by UI/SSE/Agent):
      run.submitted, run.queue_requested, run.started,
      run.succeeded, run.failed, run.cancelled
      task.started, task.progress, task.succeeded, task.failed

    Diagnostic events (human/tool debugging only, do not drive state):
      runtime.message
    """

    # Run-level product events
    RUN_SUBMITTED = "run.submitted"
    RUN_QUEUE_REQUESTED = "run.queue_requested"
    RUN_STARTED = "run.started"
    RUN_SUCCEEDED = "run.succeeded"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    RUN_ACTION = "run.action"

    # Task-level product events
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_SUCCEEDED = "task.succeeded"
    TASK_FAILED = "task.failed"
    JOB_STARTED = "job.started"
    JOB_SUCCEEDED = "job.succeeded"
    JOB_FAILED = "job.failed"
    WORKFLOW_GRAPH = "workflow.graph"

    # Diagnostic events (do not drive state)
    RUNTIME_MESSAGE = "runtime.message"


# Terminal statuses
TERMINAL_STATUSES: frozenset[RunStatus] = frozenset({
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
})

# Cancellable statuses
CANCELLABLE_STATUSES: frozenset[RunStatus] = frozenset({
    RunStatus.QUEUED,
    RunStatus.RUNNING,
})
