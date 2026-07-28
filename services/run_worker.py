"""
Run Worker -- file-scan queue -> TDEase Execution Runtime -> events.jsonl.

Design constraints:
- ~50 lines of business logic. Daemonizing/restart/cgroups belong to systemd.
- Atomic claim (O_CREAT | O_EXCL claim file).
- Calls Execution Runtime execute().
- All status writes go through Storage Layout's sync_run_projection --
  CORE-ARCHITECTURE.md Sec 1.4: "status" is a projection of events.jsonl,
  never written independently here. The two former independent writers
  (this file computing a SUCCEEDED/FAILED/CANCELLED ternary itself, and
  storage.py's reconcile rewriting "status" by hand) are both gone; both
  now call the same single projection path.
"""

from __future__ import annotations

import json
import os
import sys
import time
from threading import Event
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.contracts import RunCommit, RunStatus
from src.execution_runtime import execute, get_storage
from src.execution_runtime.events import EventEmitter
from src.execution_runtime.errors import runtime_internal
from src.execution_runtime.storage import StorageLayout


def _data_root() -> Path:
    # Single entry point get_storage() -- keeps runtime-root resolution centralized.
    return get_storage().data


def _dequeue() -> Optional[dict]:
    """Scan runs/, atomically claim the first QUEUED run (O_CREAT|O_EXCL claim file)."""
    runs_dir = _data_root() / "runs"
    if not runs_dir.exists():
        return None

    for rd in sorted(runs_dir.iterdir()):
        if not rd.is_dir():
            continue
        rj = rd / "run.json"
        if not rj.exists():
            continue
        data = json.loads(rj.read_text(encoding="utf-8"))
        if data.get("status") != "QUEUED":
            continue

        try:
            if get_storage().claim_run(data["run_id"]):
                return data
            continue
        except (FileExistsError, KeyError, ValueError):
            continue

    return None


def execute_run(run_data: dict) -> None:
    """Execute one Run -- entirely through the Execution Runtime."""
    run_id = run_data["run_id"]
    storage = get_storage()
    storage.bootstrap()

    # Idempotent -- API already created dir and wrote run.queued event
    storage.allocate_run(run_id)

    commit = RunCommit(
        run_id=run_id,
        idempotency_key=run_data.get("idempotency_key", ""),
        workspace_id=run_data.get("workspace_id", ""),
        workspace_tree_hash=run_data.get("workspace_tree_hash", "0" * 64),
        workspace_files=run_data.get("workspace_files", []),
        local_root_id=run_data.get("local_root_id"),
        local_run_path=run_data.get("local_run_path"),
        workspace_run_path=run_data.get("workspace_run_path"),
        snakefile=run_data.get("snakefile", ""),
        config=run_data.get("config", {}),
        cores=run_data.get("cores", 4),
        user_id=run_data.get("user_id", "worker"),
        mode=run_data.get("mode", "local"),
        packages=run_data.get("packages", []),
        nodes=run_data.get("nodes", []),
        targets=run_data.get("targets", []),
        memory_mb=run_data.get("memory_mb"),
        labels=run_data.get("labels", {}),
    )

    # Record process bookkeeping (pid, started_at) only. Not "status" --
    # that is derived from events by sync_run_projection below, the single
    # writer of that field (CORE-ARCHITECTURE.md Sec 1.4).
    run_json = _data_root() / "runs" / run_id / "run.json"
    current = json.loads(run_json.read_text(encoding="utf-8")) if run_json.exists() else dict(run_data)
    storage.atomic_write_json(
        run_json,
        {**current, "pid": os.getpid(), "started_at": datetime.now(timezone.utc).isoformat()},
    )
    try:
        if commit.mode == "local":
            storage.verify_local_inputs(run_id)
        result = execute(commit, rerun_mode=run_data.get("rerun_mode", "resume"))
        if commit.mode == "local":
            storage.verify_local_inputs(run_id)
    except Exception as exc:
        from src.execution_runtime.runtime import ExecutionResult
        error = runtime_internal(str(exc))
        result = ExecutionResult(success=False, exit_code=-1, error=error)
        # execute() raises only from inside its own try/except, which
        # always appends a terminal event first -- but the local-input
        # verification calls above are outside execute() and can raise
        # with no terminal event on record at all. Append one now so the
        # projection (and sync_run_projection just below) has a terminal
        # fact to converge to instead of being stuck RUNNING/QUEUED
        # forever with only a run.json rewrite to show for it.
        EventEmitter(run_id).run_failed(
            exit_code=-1, run_time_seconds=0.0, error_message=str(error)
        )

    projection = storage.sync_run_projection(run_id)

    if projection.status == RunStatus.SUCCEEDED.value:
        storage.write_results_manifest(run_id)

    # Cleanup claim
    storage.release_claim(run_id)


def run_loop(
    poll_interval: float = 1.0,
    once: bool = False,
    stop_event: Event | None = None,
) -> None:
    """Worker main loop."""
    storage = get_storage()
    storage.bootstrap()
    storage.reconcile_orphaned_runs()

    while True:
        if stop_event and stop_event.is_set():
            return
        try:
            if not storage.claim_execution_slot():
                if once:
                    break
                if stop_event:
                    stop_event.wait(poll_interval)
                else:
                    time.sleep(poll_interval)
                continue
            try:
                run_data = _dequeue()
                if run_data:
                    execute_run(run_data)
                elif once:
                    break
                else:
                    if stop_event:
                        stop_event.wait(poll_interval)
                    else:
                        time.sleep(poll_interval)
            finally:
                storage.release_execution_slot()
        except KeyboardInterrupt:
            break
        except Exception:
            import traceback
            traceback.print_exc()
            time.sleep(poll_interval)


if __name__ == "__main__":
    once = "--once" in sys.argv
    run_loop(once=once)
