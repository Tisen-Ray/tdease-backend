"""High-cohesion boundary between TDEase and the Snakemake process.

The adapter owns request materialization, command construction, process-tree
supervision, log draining, cancellation, resource enforcement, job-event
translation, and the engine exit result.  The child entrypoint remains in
``engine_runner.py`` because Snakemake must run outside the Worker process.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

from src.contracts import EventType
from src.execution_runtime.engine_contract import WorkflowEngineRequest
from src.execution_runtime.events import EventEmitter
from src.execution_runtime.execution import (
    backend_child_env,
    _isolate_engine_descendants,
    _isolate_engine_process,
    _kill_process_group,
)
from src.execution_runtime.storage import StorageLayout, read_complete_lines_from


@dataclass(frozen=True)
class SnakemakeExecutionResult:
    success: bool
    exit_code: int
    duration_seconds: float
    stderr_tail: str
    cancelled: bool = False


class SnakemakeAdapter:
    """Supervise one Snakemake invocation for one Backend Run."""

    TASK_ID = "engine"
    STEP_LABEL = "Workflow engine"
    DISPLAY_COMMAND = "TDEase Workflow Engine"
    REQUEST_PATH = Path(".tdease") / "engine-request.json"
    JOB_EVENT_PATH = Path(".tdease") / "job-events.jsonl"
    PROCESS_RECORD_PATH = Path(".runtime") / "process.json"

    def __init__(
        self,
        run_id: str,
        run_root: Path,
        storage: StorageLayout,
        emitter: EventEmitter,
    ) -> None:
        self.run_id = run_id
        self.run_root = run_root
        self.storage = storage
        self.emitter = emitter

    def execute(
        self,
        request: WorkflowEngineRequest,
        *,
        revision_id: str,
        execution_mode: str,
        timeout_seconds: int,
    ) -> SnakemakeExecutionResult:
        inspection_start = time.perf_counter()
        # The engine attempt's journal identity is the OPEN execution range:
        # run_commands.begin_execution() appended run.started before this
        # call, so a range that is missing or names another revision/mode
        # means this attempt was never authorized (or was already superseded).
        projection, _snapshot = self.storage.project_run_snapshot(self.run_id)
        open_range = next(
            (r for r in reversed(projection.ranges) if r.is_open), None
        )
        if (
            open_range is None
            or open_range.revision_id != revision_id
            or open_range.mode != execution_mode
        ):
            return SnakemakeExecutionResult(
                success=False,
                exit_code=-1,
                duration_seconds=time.perf_counter() - inspection_start,
                stderr_tail="workflow engine attempt does not match the open Journal execution range",
            )
        queue_seq = open_range.queue_seq
        try:
            self.storage.begin_task_log_attempt(self.run_id, self.TASK_ID, queue_seq)
        except OSError as exc:
            return SnakemakeExecutionResult(
                success=False,
                exit_code=-1,
                duration_seconds=time.perf_counter() - inspection_start,
                stderr_tail=f"workflow engine log attempt could not be initialized: {exc}",
            )
        try:
            recover_stale_locks = (
                execution_mode == "continue"
                and request.rerun_mode == "resume"
                and self._has_engine_locks()
            )
        except RuntimeError as exc:
            return self._failed(inspection_start, -1, str(exc))
        if recover_stale_locks:
            safety_error = self._stale_lock_recovery_error()
            if safety_error is not None:
                return self._failed(inspection_start, -1, safety_error)
            request = request.model_copy(update={"unlock_before_execute": True})
            self.emitter.runtime_message(
                "warning",
                "Recovering stale workflow-engine locks through the official unlock flow",
                self.TASK_ID,
            )
        self.storage.atomic_write_json(
            self.run_root / self.REQUEST_PATH,
            request.model_dump(),
        )
        job_event_path = self.run_root / self.JOB_EVENT_PATH
        job_event_path.unlink(missing_ok=True)

        start = time.perf_counter()
        stderr_lines: list[str] = []
        command = [sys.executable, "-m", "src.execution_runtime.engine_runner"]
        try:
            proc = subprocess.Popen(
                command,
                cwd=str(self.run_root),
                env=backend_child_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                if os.name == "nt"
                else 0,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            return self._failed(start, -1, f"workflow engine could not start: {exc}")

        _isolate_engine_process(self.run_id, self.TASK_ID, proc.pid)
        threading.Thread(
            target=_isolate_engine_descendants,
            args=(proc.pid,),
            daemon=True,
        ).start()
        self._record_engine_pid(proc.pid)
        # run.started is NOT emitted here: begin_execution() appended it (and
        # took the execution lease) before the engine spawned -- §2.5. The
        # adapter keeps job/task/graph events only.
        self.emitter.task_started(
            self.TASK_ID,
            self.STEP_LABEL,
            self.DISPLAY_COMMAND,
        )

        def drain(stream, stream_name: str) -> None:
            if stream is None:
                return
            for line in iter(stream.readline, ""):
                try:
                    # Verbatim engine output is the debugging evidence; no renaming.
                    self.storage.append_task_output(
                        self.run_id,
                        self.TASK_ID,
                        stream_name,
                        line,
                    )
                except OSError:
                    # Disk full while persisting output. Keep READING the pipe
                    # and discard: if this thread died instead, the engine's
                    # 64KB stdout buffer would fill, the engine would block on
                    # print() forever, and the global execution slot would be
                    # held until the multi-day deadline.
                    continue
                if stream_name == "stderr":
                    stderr_lines.append(line)
                    if len(stderr_lines) > 200:
                        del stderr_lines[:-100]

        readers = [
            threading.Thread(target=drain, args=(proc.stdout, "stdout"), daemon=True),
            threading.Thread(target=drain, args=(proc.stderr, "stderr"), daemon=True),
        ]
        for reader in readers:
            reader.start()

        event_stop = threading.Event()
        event_reader = threading.Thread(
            target=self._relay_job_events,
            args=(job_event_path, event_stop),
            daemon=True,
        )
        event_reader.start()

        deadline = start + timeout_seconds
        failure: str | None = None
        was_cancelled = False
        try:
            while proc.poll() is None:
                if self.storage.check_cancelled(self.run_id):
                    failure = "cancelled"
                    was_cancelled = True
                    _kill_process_group(proc)
                    break
                now = time.perf_counter()
                if now > deadline:
                    failure = f"workflow engine timed out after {timeout_seconds}s"
                    _kill_process_group(proc)
                    break
                time.sleep(0.05)
        except Exception as exc:
            failure = f"execution error: {exc}"
            _kill_process_group(proc)
            self.storage.append_runtime_record(
                self.run_id, "error", failure, self.TASK_ID
            )
        finally:
            for reader in readers:
                reader.join(timeout=2)
            event_stop.set()
            event_reader.join(timeout=2)
            (self.run_root / self.PROCESS_RECORD_PATH).unlink(missing_ok=True)

        exit_code = proc.returncode if proc.returncode is not None else -1
        if failure is not None:
            self.storage.append_task_output(
                self.run_id, self.TASK_ID, "stderr", failure
            )
            elapsed = time.perf_counter() - start
            self.emitter.task_failed(self.TASK_ID, exit_code, elapsed, failure)
            return SnakemakeExecutionResult(
                success=False,
                exit_code=exit_code,
                duration_seconds=elapsed,
                stderr_tail=failure,
                cancelled=was_cancelled,
            )

        elapsed = time.perf_counter() - start
        stderr_tail = "".join(stderr_lines[-50:])[-500:]
        if exit_code == 0:
            self.emitter.task_succeeded(self.TASK_ID, elapsed)
        else:
            self.emitter.task_failed(self.TASK_ID, exit_code, elapsed, stderr_tail)
        return SnakemakeExecutionResult(
            success=exit_code == 0,
            exit_code=exit_code,
            duration_seconds=elapsed,
            stderr_tail=stderr_tail,
        )

    def _failed(
        self, start: float, exit_code: int, message: str
    ) -> SnakemakeExecutionResult:
        elapsed = time.perf_counter() - start
        self.storage.append_task_output(self.run_id, self.TASK_ID, "stderr", message)
        self.emitter.task_failed(self.TASK_ID, exit_code, elapsed, message)
        return SnakemakeExecutionResult(False, exit_code, elapsed, message)

    def _relay_job_events(self, path: Path, stop: threading.Event) -> None:
        """Forward engine job-event frames from the JSONL side channel.

        The cursor only ever moves past complete lines (the
        ``read_complete_lines_from`` discipline): the engine appends frames
        byte-wise, so acknowledging a half-written line would skip that event
        forever once the writer completed it.  ``stop`` is set after the
        engine exited; the final pass then drains every complete line left in
        the file.
        """
        offset = 0
        while True:
            if path.exists():
                lines, offset = read_complete_lines_from(path, offset)
                for raw_line in lines:
                    self._relay_job_event_frame(raw_line)
            if stop.is_set():
                return
            stop.wait(0.1)

    def _relay_job_event_frame(self, raw_line: bytes) -> None:
        """Translate one complete frame to emitter calls.

        Only parsing/validation is guarded; emission is not: a malformed
        frame is reported loudly (never silently skipped) without blocking
        the frames behind it, and a real emitter failure still surfaces as
        such.
        """
        try:
            payload = json.loads(raw_line)
            if not isinstance(payload, dict):
                raise ValueError("frame is not a JSON object")
            event_type = payload["type"]
            if event_type == "workflow.graph":
                graph: dict | None = {
                    "nodes": payload.get("nodes", []),
                    "edges": payload.get("edges", []),
                }
                job = None
            else:
                graph = None
                job = (
                    EventType(event_type),
                    int(payload["job_id"]),
                    str(payload["rule"]),
                    payload.get("wildcards"),
                )
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            snippet = raw_line.decode("utf-8", errors="replace").strip()
            message = f"malformed job-event frame: {exc}: {snippet[:200]}"
            self.storage.append_runtime_record(
                self.run_id, "error", message, self.TASK_ID
            )
            self.emitter.runtime_message("warning", message, self.TASK_ID)
            return
        if job is not None:
            self.emitter.job_event(*job)
        else:
            self.emitter.workflow_graph(graph)

    def _record_engine_pid(self, pid: int) -> None:
        """Persist disposable process identity for cancellation/reconciliation.

        The creation time travels with the pid: a recycled pid must never make a
        dead engine look alive (or point a kill at an unrelated process).
        """
        try:
            import psutil

            try:
                created = psutil.Process(pid).create_time()
            except Exception:
                created = None
            self.storage.atomic_write_json(
                self.run_root / self.PROCESS_RECORD_PATH,
                {
                    "schema_version": 1,
                    "role": "snakemake-engine",
                    "engine_pid": pid,
                    "engine_create_time": created,
                    "started_at_unix": time.time(),
                },
            )
        except Exception as exc:
            # Reconciliation metadata is best-effort and cannot stop execution,
            # but an invisible failure here blinds kill_engine_tree (it reads
            # this record to find the engine pid) — surface it.
            logger.warning("engine process record could not be written: %s", exc)

    def _has_engine_locks(self) -> bool:
        lock_dir = self.run_root / ".tdease" / "engine" / "locks"
        try:
            return lock_dir.is_dir() and any(lock_dir.iterdir())
        except OSError as exc:
            raise RuntimeError(
                f"workflow-engine lock state could not be inspected: {exc}"
            ) from exc

    def _stale_lock_recovery_error(self) -> str | None:
        from src.execution_runtime.storage import process_identity_alive

        claim = self.storage.data / ".runtime" / "execution.claim"
        try:
            owner = claim.read_text(encoding="ascii").strip()
        except (FileNotFoundError, OSError):
            return "stale workflow-engine lock recovery requires the global execution lease"
        if owner.split(":", 1)[0] != str(os.getpid()):
            return (
                "stale workflow-engine lock recovery lease belongs to another process"
            )

        process = self.storage.read_json(self.run_root / self.PROCESS_RECORD_PATH) or {}
        engine_pid = process.get("engine_pid")
        if engine_pid:
            created = process.get("engine_create_time")
            if process_identity_alive(f"{engine_pid}:{created if created else ''}"):
                return "stale workflow-engine lock recovery refused: engine process is still active"
        return None
