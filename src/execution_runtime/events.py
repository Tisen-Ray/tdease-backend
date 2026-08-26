"""
TDEase Event Emitter — emits typed events directly from inside the Execution Runtime.

Seq values are allocated atomically by the Storage Layout append_event (single writer, monotonic).
On init the EventEmitter restores its starting sequence number from events.jsonl.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.contracts import EventType
from src.contracts.lifecycle_declaration import LIFECYCLE_SCHEMA_VERSION
from src.execution_runtime.storage import get_storage


class EventEmitter:
    """Event emitter for the execution engine. seq is allocated atomically by storage."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._storage = get_storage()
        # Recover from persisted seq (API writes submitted/queue events first).
        self._last_seq = self._storage.recover_seq(run_id)

    @property
    def last_seq(self) -> int:
        return self._last_seq

    # ── Run events ──

    def run_submitted(self, revision_id: str, **data: Any) -> int:
        return self._emit(
            EventType.RUN_SUBMITTED,
            "Run submitted",
            "info",
            {"revision_id": revision_id, **data},
        )

    def run_queue_requested(
        self,
        revision_id: str,
        mode: str,
        **data: Any,
    ) -> int:
        return self._emit(
            EventType.RUN_QUEUE_REQUESTED,
            "Run queued",
            "info",
            {"revision_id": revision_id, "mode": mode, **data},
        )

    def run_started(self, revision_id: str, mode: str, pid: int, worker_id: str) -> int:
        return self._emit(EventType.RUN_STARTED,
            f"Worker {worker_id} started (pid={pid})", "info",
            {"revision_id": revision_id, "mode": mode, "pid": pid, "worker_id": worker_id})

    def run_succeeded(
        self,
        revision_id: str,
        run_time_seconds: float,
        total_tasks: int = 0,
    ) -> int:
        return self._emit(EventType.RUN_SUCCEEDED,
            f"Run succeeded in {run_time_seconds:.1f}s", "info",
            {"revision_id": revision_id, "run_time_seconds": run_time_seconds,
             "total_tasks": total_tasks})

    def run_failed(self, revision_id: str, exit_code: int | None, run_time_seconds: float,
                    error_message: str = "") -> int:
        return self._emit(EventType.RUN_FAILED,
            error_message or f"Run failed (exit {exit_code})", "error",
            {"revision_id": revision_id, "exit_code": exit_code,
             "run_time_seconds": run_time_seconds,
             "error_message": error_message})

    def run_cancelled(self, revision_id: str, run_time_seconds: float = 0.0) -> int:
        return self._emit(EventType.RUN_CANCELLED, "Run cancelled", "info",
            {"revision_id": revision_id, "run_time_seconds": run_time_seconds})

    def run_action(self, action: str, actor: str, **data: Any) -> int:
        return self._emit(
            EventType.RUN_ACTION,
            f"Run action: {action}",
            "info",
            {"action": action, "actor": actor, **data},
        )

    # ── Task events ──

    def task_started(self, task_id: str, step: str, command: str = "") -> int:
        return self._emit(EventType.TASK_STARTED, f"Task started: {step}",
            "info", {"task_id": task_id, "step": step, "command": command})

    def task_progress(self, task_id: str, done: int, total: int) -> int:
        pct = round(done / max(total, 1) * 100, 1)
        return self._emit(EventType.TASK_PROGRESS,
            f"Task progress: {done}/{total}", "info",
            {"task_id": task_id, "done": done, "total": total, "percent": pct})

    def task_succeeded(self, task_id: str, duration_seconds: float,
                        output_files: list[str] | None = None) -> int:
        return self._emit(EventType.TASK_SUCCEEDED,
            f"Task succeeded: {task_id}", "info",
            {"task_id": task_id, "duration_seconds": duration_seconds,
             "output_files": output_files or []})

    def task_failed(self, task_id: str, exit_code: int, duration_seconds: float,
                     error_message: str = "") -> int:
        return self._emit(EventType.TASK_FAILED,
            f"Task failed: {task_id} (exit {exit_code})", "error",
            {"task_id": task_id, "exit_code": exit_code,
             "duration_seconds": duration_seconds, "error_message": error_message})

    def job_event(self, event_type: EventType, job_id: int, rule: str,
                  wildcards: dict[str, str] | None = None) -> int:
        return self._emit(event_type, f"Workflow job {event_type.value}: {rule}",
            "error" if event_type == EventType.JOB_FAILED else "info",
            {"job_id": job_id, "rule": rule, "wildcards": wildcards or {}})

    def workflow_graph(self, projection: dict[str, Any]) -> int:
        return self._emit(EventType.WORKFLOW_GRAPH, "Workflow graph resolved", "info", projection)

    # ── Diagnostic ──

    def runtime_message(self, level: str, message: str,
                         task_id: str | None = None) -> int:
        return self._emit(EventType.RUNTIME_MESSAGE, message, level,
            {"level": level, "message": message,
             "runtime_ref": {"task_id": task_id} if task_id else None})

    # ── Core emit — delegates seq allocation to storage ──

    def _emit(self, event_type: EventType, message: str, level: str,
              data: dict[str, Any]) -> int:
        event = {
            "schema_version": LIFECYCLE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "seq": 0,  # storage will overwrite with correct monotonic seq
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type.value,
            "level": level,
            "message": message,
            "runtime_ref": None,
            "data": data,
        }
        self._last_seq = self._storage.append_event(self.run_id, event)
        try:
            from src.services.run_event_projector import enqueue_event_projection

            enqueue_event_projection(self.run_id, event)
        except Exception:
            # events.jsonl is already durable. Projection failure is repaired
            # from its sequence checkpoint and must not fail the execution.
            try:
                from src.services.run_index import get_run_index

                get_run_index().mark_dirty()
            except Exception:
                pass
        return self._last_seq
