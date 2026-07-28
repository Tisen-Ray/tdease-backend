"""
Run Worker -- global SQLite queue -> TDEase Execution Runtime -> events.jsonl.

Design constraints:
- ~50 lines of business logic. Daemonizing/restart/cgroups belong to systemd.
- Atomic claim (O_CREAT | O_EXCL claim file).
- Calls Execution Runtime execute().
- events.jsonl is the lifecycle truth. SQLite is a rebuildable queue/read
  projection and run.json remains an immutable execution definition.
"""

from __future__ import annotations

import json
import logging
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


logger = logging.getLogger(__name__)


def _index_run(data: dict, storage: StorageLayout) -> None:
    index = None
    try:
        from src.services.run_index import get_run_index

        index = get_run_index()
        run_id = str(data.get("run_id", ""))
        index.upsert_run(data, storage.recover_seq(run_id))
        index.catch_up_run(storage, run_id)
    except Exception:
        if index is not None:
            index.mark_dirty()
        logger.exception("Worker Run index update failed for %s", data.get("run_id"))


def _data_root() -> Path:
    # Single entry point get_storage() -- keeps runtime-root resolution centralized.
    return get_storage().data


def _prepare_worker(storage: StorageLayout) -> None:
    """Prepare persistent queue state without depending on API startup."""
    from app.database.lifecycle import migrate_database

    migrate_database(str(storage.data / "database" / "db.sqlite3"))
    from src.services.run_index import get_run_index

    get_run_index().reconcile(storage)


def _dequeue() -> Optional[dict]:
    """Claim the oldest queued Run globally, independent of tenant identity."""
    runs_dir = _data_root() / "runs"
    if not runs_dir.exists():
        return None

    try:
        from src.services.run_index import get_run_index

        index = get_run_index()
        if index.is_dirty():
            index.reconcile(get_storage())
        for run_id in index.queued_run_ids():
            data = get_storage().read_json(runs_dir / run_id / "run.json")
            if not data:
                continue
            if get_storage().claim_run(run_id):
                return data
        return None
    except Exception:
        logger.exception("Run queue index unavailable; scanning filesystem truth")

    candidates: list[tuple[float, str, dict]] = []
    for rd in runs_dir.iterdir():
        if not rd.is_dir():
            continue
        rj = rd / "run.json"
        if not rj.exists():
            continue
        data = json.loads(rj.read_text(encoding="utf-8"))
        projection, _snapshot = get_storage().project_run_snapshot(str(data.get("run_id", rd.name)))
        if projection.status != "QUEUED":
            continue

        created_at = data.get("created_at")
        try:
            queued_at = datetime.fromisoformat(str(created_at)).timestamp()
        except (TypeError, ValueError, OSError):
            queued_at = rj.stat().st_mtime
        candidates.append((queued_at, str(data.get("run_id", rd.name)), data))

    for _queued_at, _run_id, data in sorted(candidates, key=lambda item: (item[0], item[1])):
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

    # Idempotent -- API already created the directory and queued via Journal.
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
        materialization_strategy=run_data.get("materialization_strategy"),
        packages=run_data.get("packages", []),
        nodes=run_data.get("nodes", []),
        targets=run_data.get("targets", []),
        memory_mb=run_data.get("memory_mb"),
        labels=run_data.get("labels", {}),
    )

    projection, _snapshot = storage.project_run_snapshot(run_id)
    if projection.status != RunStatus.QUEUED.value or not projection.current_revision_id:
        raise RuntimeError(f"Run {run_id} is not backed by a queued Journal revision")
    queue_event = next(
        event for event in reversed(storage.read_events(run_id))
        if event.get("type") == "run.queue_requested"
    )
    raw_queue_data = queue_event.get("data")
    queue_data: dict = raw_queue_data if isinstance(raw_queue_data, dict) else {}
    execution_mode = projection.queued_mode or "execute"
    rerun_mode = str(queue_data.get("rerun_mode", "resume"))
    revision_id = projection.current_revision_id
    _index_run(run_data, storage)
    try:
        if commit.materialization_strategy == "local_workspace_hardlink":
            storage.verify_local_inputs(run_id)
        result = execute(
            commit,
            revision_id=revision_id,
            execution_mode=execution_mode,
            rerun_mode=rerun_mode,
        )
        if commit.materialization_strategy == "local_workspace_hardlink":
            storage.verify_local_inputs(run_id)
    except Exception as exc:
        from src.execution_runtime.runtime import ExecutionResult
        error = runtime_internal(str(exc))
        result = ExecutionResult(success=False, exit_code=-1, error=error)
        # execute() raises only from inside its own try/except, which
        # always appends a terminal event first -- but the local-input
        # verification calls above are outside execute() and can raise
        # with no terminal event on record at all. Append one now so the
        # projection has a terminal fact instead of remaining RUNNING/QUEUED.
        EventEmitter(run_id).run_failed(
            revision_id=revision_id,
            exit_code=-1, run_time_seconds=0.0, error_message=str(error)
        )

    manifest_path = None
    if result.success:
        try:
            manifest_path = storage.write_results_manifest(run_id, revision_id)
            EventEmitter(run_id).run_succeeded(
                revision_id=revision_id,
                run_time_seconds=result.run_time_seconds,
                total_tasks=result.total_tasks,
            )
        except Exception as exc:
            EventEmitter(run_id).run_failed(
                revision_id=revision_id,
                exit_code=-1,
                run_time_seconds=0.0,
                error_message=f"result manifest finalization failed: {exc}",
            )

    projection, _snapshot = storage.project_run_snapshot(run_id)
    _index_run(run_data, storage)

    if projection.status == RunStatus.SUCCEEDED.value and manifest_path is not None:
        index = None
        try:
            from src.services.run_index import get_run_index

            index = get_run_index()
            manifest = storage.read_json(manifest_path)
            if isinstance(manifest, dict):
                index.replace_manifest(run_id, manifest)
        except Exception:
            if index is not None:
                index.mark_dirty()
            logger.exception("Worker Run file index update failed for %s", run_id)

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
    _prepare_worker(storage)
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
                    try:
                        execute_run(run_data)
                    finally:
                        storage.release_claim(run_data["run_id"])
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
