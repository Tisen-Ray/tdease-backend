"""
TDEase Event Emitter — 从 Execution Runtime 内部直接发出 typed event。

Seq 由 Storage Layout 的 append_event 原子分配（单写者，monotonic）。
EventEmitter 初始化时从 events.jsonl 恢复起始序号。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.contracts import EventType
from src.execution_runtime.storage import get_storage


class EventEmitter:
    """执行引擎的事件发射器。seq 由 storage 原子分配。"""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._storage = get_storage()
        # Recover from persisted seq (API may have written run.queued already)
        self._last_seq = self._storage.recover_seq(run_id)

    @property
    def last_seq(self) -> int:
        return self._last_seq

    # ── Run events ──

    def run_queued(self, **data: Any) -> int:
        return self._emit(EventType.RUN_QUEUED, "Run queued", "info", data)

    def run_started(self, pid: int, worker_id: str) -> int:
        return self._emit(EventType.RUN_STARTED,
            f"Worker {worker_id} started (pid={pid})", "info",
            {"pid": pid, "worker_id": worker_id})

    def run_succeeded(self, run_time_seconds: float, total_tasks: int = 0) -> int:
        return self._emit(EventType.RUN_SUCCEEDED,
            f"Run succeeded in {run_time_seconds:.1f}s", "info",
            {"run_time_seconds": run_time_seconds, "total_tasks": total_tasks})

    def run_failed(self, exit_code: int | None, run_time_seconds: float,
                    error_message: str = "") -> int:
        return self._emit(EventType.RUN_FAILED,
            error_message or f"Run failed (exit {exit_code})", "error",
            {"exit_code": exit_code, "run_time_seconds": run_time_seconds,
             "error_message": error_message})

    def run_cancelled(self, run_time_seconds: float = 0.0) -> int:
        return self._emit(EventType.RUN_CANCELLED, "Run cancelled", "info",
            {"run_time_seconds": run_time_seconds})

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
            "schema_version": 1,
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
        return self._last_seq
