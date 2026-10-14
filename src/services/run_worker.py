"""
Run Worker -- global SQLite queue -> TDEase Execution Runtime -> events.jsonl.

Design constraints:
- ~50 lines of business logic. Daemonizing/restart/cgroups belong to systemd.
- Atomic claim (O_CREAT | O_EXCL claim file).
- Calls Execution Runtime execute().
- events.jsonl is the lifecycle truth. SQLite is a rebuildable queue/read
  projection and definitions/<revision>.json remains an immutable execution
  definition; run.json points at the latest one for management views.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from threading import Event

from src.contracts import RunCommit, RunStatus
from src.contracts.errors import ErrorCode, TDEaseError
from src.execution_runtime import execute, get_storage
from src.execution_runtime.events import EventEmitter
from src.execution_runtime.storage import (
    StorageLayout,
    process_identity,
    process_identity_alive,
)
from src.services.run_commands import Lease, get_run_commands

logger = logging.getLogger(__name__)


def _materialize_run(commit: RunCommit, storage: StorageLayout) -> None:
    """Expose the committed definition in the run directory, immediately before execution.

    Submission validates and writes nothing; this is the one place a Run's
    working files are created. It therefore always reflects the revision being
    started -- an edit made while a previous execution was still running cannot
    leak into it, and a re-submitted definition is picked up by the next
    execution. Inputs are hardlinked from immutable CAS blobs; a link that the
    platform refuses fails the Run instead of silently copying per-Run bytes.
    Node packages are NOT materialized here: tools stay in the Backend catalog
    and the engine reaches them through config["nodes"] absolute paths.
    """
    if commit.materialization_strategy == "local_workspace_hardlink":
        # New submissions seal local inputs during POST /runs, so the worker
        # does not depend on a mutable Workspace or a second root-capability
        # lookup. Keep the source-backed path for legacy queued definitions
        # created before input sealing was introduced.
        if all(
            storage.blob_exists(
                entry.blob_hash if hasattr(entry, "blob_hash") else entry["blob_hash"]
            )
            for entry in commit.workspace_files
        ):
            storage.materialize_run_files(commit.run_id, commit.workspace_files)
        else:
            from src.services.workspace_roots import get_workspace_root_registry

            workspace = get_workspace_root_registry().resolve(
                commit.user_id, commit.local_root_id, commit.local_run_path or "."
            )
            if workspace is None:
                raise ValueError(
                    "Workspace root capability is missing, revoked, or the Run path escapes it"
                )
            storage.materialize_local_run_files(
                storage.allocate_run(commit.run_id),
                workspace,
                commit.workspace_files,
                user_id=commit.user_id,
            )
    else:
        storage.materialize_run_files(commit.run_id, commit.workspace_files)


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
    from src.services.workspace_roots import configure_workspace_root_runtime

    db_path = storage.data / "database" / "db.sqlite3"
    migrate_database(str(db_path))
    configure_workspace_root_runtime(db_path)
    # Rejected submissions and purged Runs can leave unreferenced shared bytes.
    # Cleanup is reachability-based and grace-period protected, so worker
    # startup is a safe low-frequency management boundary without another
    # scheduler or a per-Run cleanup task.
    storage.gc_unreferenced_blobs()
    from src.services.run_index import get_run_index

    get_run_index().reconcile(storage)


def _dequeue() -> dict | None:
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
            if get_storage().acquire_lease(run_id):
                return data
        return None
    except Exception:
        logger.exception("Run queue index unavailable; scanning filesystem truth")

    # One ordering with the index path (BACKEND-RUN-SERVICE §2.4): the global
    # queue ticket minted at arrival. Each Run's local journal seq is an
    # execution-attempt identity, not an arrival order -- ordering by it let a
    # newly submitted Run (local seq 2) jump a resubmitted older Run (local
    # seq 200). A Run absent from the mint log (pre-ticket journal) orders
    # after ticketed arrivals by created_at, mirroring the index's NULL-
    # queued_ticket sort.
    tickets = get_storage().latest_queue_tickets()
    candidates: list[tuple[int, int, float, str, dict]] = []
    for rd in runs_dir.iterdir():
        if not rd.is_dir():
            continue
        rj = rd / "run.json"
        if not rj.exists():
            continue
        data = json.loads(rj.read_text(encoding="utf-8"))
        run_id = str(data.get("run_id", rd.name))
        projection, _snapshot = get_storage().project_run_snapshot(run_id)
        if projection.status != "QUEUED":
            continue

        ticket = tickets.get(run_id)
        if ticket is not None:
            candidates.append((0, ticket, 0.0, run_id, data))
        else:
            try:
                created_ts = datetime.fromisoformat(
                    str(data.get("created_at"))
                ).timestamp()
            except (TypeError, ValueError, OSError):
                created_ts = rj.stat().st_mtime
            candidates.append((1, 0, created_ts, run_id, data))

    for _flag, _ticket, _created, _run_id, data in sorted(
        candidates, key=lambda item: (item[0], item[1], item[2], item[3])
    ):
        try:
            if get_storage().acquire_lease(data["run_id"]):
                return data
            continue
        except (KeyError, ValueError):
            continue

    return None


def _has_queued_run() -> bool:
    """Return whether work is available without claiming the execution slot."""
    runs_dir = _data_root() / "runs"
    if not runs_dir.exists():
        return False

    try:
        from src.services.run_index import get_run_index

        index = get_run_index()
        if index.is_dirty():
            index.reconcile(get_storage())
        return bool(index.queued_run_ids(limit=1))
    except Exception:
        logger.exception("Run queue index unavailable; scanning filesystem truth")

    for rd in runs_dir.iterdir():
        if not rd.is_dir() or not (rd / "run.json").exists():
            continue
        projection, _snapshot = get_storage().project_run_snapshot(rd.name)
        if projection.status == RunStatus.QUEUED.value:
            return True
    return False


def execute_run(run_data: dict) -> None:
    """Execute one Run -- entirely through the Execution Runtime.

    Nothing may end silently. Every wrapper stage around the engine names
    itself in the worker log (`logs/tasks/worker.log`, part of the run-log
    surface), and a death BEFORE the engine still leaves a diagnostic event,
    a terminal via ``finish()`` when the journal still holds a live execution
    for this dispatch, and the traceback there. Letting an exception escape
    would bounce the lease back to QUEUED with no event and no log -- an
    invisible crash loop that, three times in a minute, takes the whole
    Backend down.
    """
    run_id = run_data["run_id"]
    storage = get_storage()
    storage.bootstrap()

    # Idempotent -- API already created the directory and queued via Journal.
    storage.allocate_run(run_id)

    def wlog(line: str) -> None:
        try:
            path = storage.resolve(run_id, "logs", "tasks", "worker.log")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(f"{line}\n")
        except OSError:
            logger.exception("Worker log append failed for %s", run_id)

    revision_id = str(run_data.get("definition_revision_id") or "")
    queue_tag = "q?"
    stage = "startup"
    lease: Lease | None = None
    commands = get_run_commands()
    try:
        projection, _snapshot = storage.project_run_snapshot(run_id)
        if projection.status == RunStatus.CANCELLED.value:
            # Cancel landed inside the claim window (after the lease acquire,
            # before this read): the journal already holds the terminal fact.
            # Falling through to the failure handler below would append
            # run.failed from CANCELLED -- an illegal lifecycle transition
            # that poisons every future projection of this Run. There is
            # nothing to execute.
            wlog(
                f"[q?] {run_id} was cancelled inside the claim window; nothing to execute"
            )
            return
        if (
            projection.status != RunStatus.QUEUED.value
            or not projection.current_revision_id
        ):
            raise RuntimeError(
                f"Run {run_id} is not backed by a queued Journal revision "
                f"(projection says {projection.status})"
            )
        revision_id = projection.current_revision_id
        queue_tag = f"q{projection.queued_at_seq}"
        wlog(
            f"[{queue_tag}] claimed definition {revision_id} "
            f"(mode={projection.queued_mode or 'execute'})"
        )
        # A cancel flag left behind by an earlier execution must not self-cancel
        # this one: the flag names the queue_seq it targets, and a flag aimed at
        # any other (or unknown/legacy) execution is stale here and gets cleared.
        if (
            storage.check_cancelled(run_id)
            and storage.cancelled_queue_seq(run_id) != projection.queued_at_seq
        ):
            storage.clear_cancelled(run_id)
            wlog(f"[{queue_tag}] cleared a stale cancel flag from another execution")
        # run.json is only the latest pointer. The queue event identifies the
        # definition that this execution must use, even when a newer edit arrived
        # after the old execution was queued.
        queued_definition = (
            storage.read_definition_snapshot(run_id, revision_id) or run_data
        )

        commit = RunCommit(
            run_id=run_id,
            idempotency_key=queued_definition.get("idempotency_key", ""),
            workspace_id=queued_definition.get("workspace_id", ""),
            workspace_tree_hash=queued_definition.get("workspace_tree_hash", "0" * 64),
            workspace_files=queued_definition.get("workspace_files", []),
            local_root_id=queued_definition.get("local_root_id"),
            local_run_path=queued_definition.get("local_run_path"),
            workspace_run_path=queued_definition.get("workspace_run_path"),
            snakefile=queued_definition.get("snakefile", ""),
            config=queued_definition.get("config", {}),
            cores=queued_definition.get("cores", 4),
            user_id=queued_definition.get("user_id", "worker"),
            materialization_strategy=queued_definition.get("materialization_strategy"),
            nodes=queued_definition.get("nodes", []),
            targets=queued_definition.get("targets", []),
            memory_mb=queued_definition.get("memory_mb"),
            labels=queued_definition.get("labels", {}),
            result_specs=queued_definition.get("result_specs", []),
        )

        # The queue request that made THIS execution queued is the one at
        # projection.queued_at_seq. Reading "the latest queue event" instead would
        # race a definition submitted between the projection read and this read:
        # revision A's files with revision B's rerun_mode.
        stage = "queue-request"
        lease = commands.begin_execution(run_id)
        if lease is None:
            # The dispatch window closed under the command lock (cancel or a
            # terminal landed first): the journal already says so.
            wlog(
                f"[{queue_tag}] dispatch window closed for {revision_id}; nothing to execute"
            )
            return
        queue_event = next(
            (
                event
                for event in storage.read_events(run_id)
                if event.get("type") == "run.queue_requested"
                and projection.queued_at_seq is not None
                and int(event.get("seq") or 0) == projection.queued_at_seq
            ),
            None,
        )
        if queue_event is None:
            raise RuntimeError(
                f"Run {run_id} has no queue event at seq {projection.queued_at_seq}"
            )
        raw_queue_data = queue_event.get("data")
        queue_data: dict = raw_queue_data if isinstance(raw_queue_data, dict) else {}
        execution_mode = projection.queued_mode or "execute"
        rerun_mode = str(queue_data.get("rerun_mode", "resume"))
        _index_run(run_data, storage)

        def beat(new_stage: str) -> str:
            # Lease observability at the stage boundary; no liveness role.
            commands.heartbeat_stage(lease, new_stage)
            return new_stage

        try:
            stage = beat("materialize")
            wlog(
                f"[{queue_tag}] materializing {revision_id} "
                f"({commit.materialization_strategy}, {len(commit.workspace_files)} input(s), "
                f"{len(commit.nodes)} node binding(s))"
            )
            _materialize_run(commit, storage)
            stage = beat("engine")
            wlog(
                f"[{queue_tag}] engine starting (mode={execution_mode}, rerun={rerun_mode})"
            )
            result = execute(
                commit,
                revision_id=revision_id,
                execution_mode=execution_mode,
                rerun_mode=rerun_mode,
            )
            wlog(
                f"[{queue_tag}] engine finished success={result.success} "
                f"in {result.run_time_seconds:.1f}s"
            )
            if commit.materialization_strategy == "local_workspace_hardlink":
                stage = beat("verify-inputs")
                storage.verify_local_inputs(run_id)
                wlog(f"[{queue_tag}] shared inputs verified unchanged")
        except TDEaseError as exc:
            from src.execution_runtime.runtime import ExecutionResult

            commands.finish(
                run_id,
                "failed",
                exit_code=-1,
                run_time_seconds=0.0,
                error_message=f"[{stage}] {exc}",
            )
            wlog(f"[{queue_tag}] FAILED at {stage}: {exc}")
            EventEmitter(run_id).runtime_message("error", str(exc))
            result = ExecutionResult(success=False, exit_code=-1, error=exc)
        except Exception as exc:
            from src.execution_runtime.runtime import ExecutionResult

            commands.finish(
                run_id,
                "failed",
                exit_code=-1,
                run_time_seconds=0.0,
                error_message=f"[{stage}] {exc}",
            )
            wlog(f"[{queue_tag}] FAILED at {stage}: {type(exc).__name__}: {exc}")
            import traceback

            try:
                with storage.resolve(run_id, "logs", "tasks", "worker.log").open(
                    "a", encoding="utf-8"
                ) as stream:
                    traceback.print_exc(file=stream)
            except OSError:
                logger.exception("Worker traceback write failed for %s", run_id)
            error = TDEaseError(
                code=ErrorCode.ENGINE_RUNTIME_INTERNAL,
                message=f"[{stage}] {exc}",
                remedy="Read the run log (the worker section names the failing stage "
                "and ends with the traceback), then retry or repair the Run.",
                retryable=False,
            )
            EventEmitter(run_id).runtime_message("error", str(error))
            result = ExecutionResult(success=False, exit_code=-1, error=error)
            # execute() raises only from inside its own try/except, which
            # always appends a terminal event first -- but the local-input
            # verification calls above are outside execute() and can raise
            # with no terminal event on record at all. finish() re-folded the
            # journal and appended one only if this execution was still live.

        manifest_path = None
        if result.success:
            stage = beat("manifest")
            try:
                manifest_path = storage.write_results_manifest(run_id, revision_id)
                commands.finish(
                    run_id,
                    "succeeded",
                    run_time_seconds=result.run_time_seconds,
                    total_tasks=result.total_tasks,
                )
                wlog(f"[{queue_tag}] manifest published for {revision_id}")
            except Exception as exc:
                commands.finish(
                    run_id,
                    "failed",
                    exit_code=-1,
                    run_time_seconds=0.0,
                    error_message=f"result manifest finalization failed: {exc}",
                )
                wlog(f"[{queue_tag}] FAILED at manifest finalization: {exc}")
    except Exception as exc:
        # Death outside the staged block (journal/projection/queue-request
        # reading, or anything after a terminal event). It must still be
        # visible: traceback to the worker log, a runtime error event, and a
        # terminal via finish() when the journal still has a live execution
        # for this dispatch. Never re-raise -- that would crash-loop the
        # claim invisibly.
        wlog(f"[{queue_tag}] FATAL at {stage}: {type(exc).__name__}: {exc}")
        import traceback

        try:
            with storage.resolve(run_id, "logs", "tasks", "worker.log").open(
                "a", encoding="utf-8"
            ) as stream:
                traceback.print_exc(file=stream)
        except OSError:
            logger.exception("Worker traceback write failed for %s", run_id)
        try:
            EventEmitter(run_id).runtime_message(
                "error",
                f"worker aborted at {stage}: {type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception("Worker diagnostic event failed for %s", run_id)
        try:
            commands.finish(
                run_id,
                "failed",
                exit_code=-1,
                run_time_seconds=0.0,
                error_message=f"worker aborted at {stage}: {type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception("Worker terminal event failed for %s", run_id)
        logger.exception("Worker execute_run failed for %s", run_id)
        return

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

    # Cleanup: the lease is released only after finish() -- while it names a
    # live process, reconcile treats this execution as owned (§2.5).
    storage.release_lease(run_id)


def run_loop(
    poll_interval: float = 1.0,
    once: bool = False,
    stop_event: Event | None = None,
    parent_pid: int | None = None,
) -> None:
    """Worker main loop.

    `parent_pid` is the supervising `serve` process. When it is given and the
    parent is gone, the loop returns: a hard-killed Client must not leave a
    worker polling the same data root forever (the orphan would keep competing
    for the execution slot and holding stale claims).
    """
    storage = get_storage()
    storage.bootstrap()
    _prepare_worker(storage)
    get_run_commands().reconcile()
    parent_identity = process_identity(parent_pid) if parent_pid else None

    while True:
        if stop_event and stop_event.is_set():
            return
        if parent_identity and not process_identity_alive(parent_identity):
            logger.warning(
                "Worker parent process is gone; exiting to avoid an orphan poller"
            )
            return
        try:
            # An idle worker must not monopolize the Backend-wide execution
            # slot: dry-runs share it with queued Run execution.
            if not _has_queued_run():
                if once:
                    break
                if stop_event:
                    stop_event.wait(poll_interval)
                else:
                    time.sleep(poll_interval)
                continue
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
                        storage.release_lease(run_data["run_id"])
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
