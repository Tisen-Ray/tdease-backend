"""Run Command Module -- the only constructor of lifecycle ``run.*`` events.

BACKEND-RUN-SERVICE.md §2.2. Landed scope: ``submit``/``queue`` (§2.3/§2.4)
and the execution-lease slice (§2.5): ``begin_execution`` appends run.started
and takes the lease as one step, ``finish`` is the only terminalizer (it
re-folds inside the lock, so a terminal is appended at most once per range),
and ``reconcile`` is the single recovery pass run by the API lifespan and the
worker loop. The adapter keeps job/task/graph events only.

Every command holds a per-run command lock across the whole decide-and-append
critical section. The storage event lock wraps exactly one JSONL append and
cannot be re-acquired by the same process (its O_EXCL file is still held), so
this lock -- same pattern, one scope wider -- is what makes fold-decide-append
atomic between API and worker processes.
"""

from __future__ import annotations

import logging
import os
import platform
from dataclasses import dataclass
from typing import Any, Optional

from src.execution_runtime.events import EventEmitter
from src.execution_runtime.run_projector import (
    LifecycleState,
    RUN_QUEUE_REQUESTED,
    RUN_SUBMITTED,
    project_run,
)
from src.execution_runtime.storage import (
    StorageLayout,
    _exclusive_lock,
    get_storage,
    process_identity,
    process_identity_alive,
)

logger = logging.getLogger(__name__)

# Stage boundaries the worker refreshes the lease at (§2.5). Observability
# only: the stage names where execution is, never whether it is alive.
LEASE_STAGES = (
    "startup",
    "queue-request",
    "materialize",
    "engine",
    "verify-inputs",
    "manifest",
)


def _fold(events: list[dict[str, Any]]) -> LifecycleState:
    """The one interpreter, kept live: the decision below needs the pending
    queue request's revision identity, which the frozen RunProjection
    snapshot deliberately does not carry."""
    state = LifecycleState()
    for event in events:
        state.apply(event)
    return state


@dataclass(frozen=True)
class SubmitOutcome:
    run_id: str
    revision_id: str
    queue_ticket: Optional[int]
    idempotent: bool


@dataclass(frozen=True)
class Lease:
    """The worker's handle on the execution it owns (§2.5)."""

    run_id: str
    worker_identity: str
    queue_seq: Optional[int]
    revision_id: Optional[str]
    stage: str


def _has_submission(events: list[dict[str, Any]], revision_id: str) -> bool:
    return any(
        event.get("type") == RUN_SUBMITTED
        and isinstance(event.get("data"), dict)
        and event["data"].get("revision_id") == revision_id
        for event in events
    )


def _queue_ticket_at(
    storage: StorageLayout, run_id: str, queue_seq: int
) -> Optional[int]:
    """The ticket carried by the queue event at ``queue_seq``, if any."""
    for event in storage.read_events(run_id):
        if int(event.get("seq") or 0) != queue_seq:
            continue
        if event.get("type") != RUN_QUEUE_REQUESTED:
            return None
        data = event.get("data")
        ticket = data.get("queue_ticket") if isinstance(data, dict) else None
        return ticket if isinstance(ticket, int) else None
    return None


def write_status_cache(index, storage: StorageLayout, run_id: str) -> None:
    """Cache the ONE journal fold's status into the Run index (§2.1).

    The write lives in the command module -- the component that appends
    lifecycle events -- and every repair path (index catch-up, reconcile)
    converges through this same function, so the cached value can never
    disagree with ``project_run``.
    """
    projection = project_run(storage.read_events(run_id))
    index.update_status(run_id, projection.status)


def _command_lock(storage: StorageLayout, run_id: str):
    """The per-run decide-and-append critical section (§2.2)."""
    return _exclusive_lock(
        storage.resolve(run_id, ".runtime", "commands.lock"),
        purpose=f"run commands ({run_id})",
    )


def _cache_status_best_effort(storage: StorageLayout, run_id: str) -> None:
    """Converge the SQLite status cache after a command appended an event.

    The index is a rebuildable cache: a missing or unmigrated database must
    never fail the journal write it shadows.
    """
    try:
        from src.services.run_index import get_run_index

        write_status_cache(get_run_index(), storage, run_id)
    except Exception:
        # Failure scenario (audit P0-1): a SQLITE_BUSY/locked database here was
        # swallowed with only a debug log, so the cache kept saying QUEUED for a
        # Run whose journal had already moved on. The worker's dequeue kept
        # picking that stale ticket, execute_run kept rejecting it, and the
        # poisoned earliest-ticket Run starved the whole queue at 1 Hz. Any
        # failed cache write MUST leave the index dirty so the next dequeue
        # reconciles it from filesystem truth instead of trusting the lie.
        logger.warning(
            "Run status cache write failed for %s; marking index dirty",
            run_id,
            exc_info=True,
        )
        try:
            from src.services.run_index import get_run_index

            get_run_index().mark_dirty()
        except Exception:
            logger.exception(
                "Run index could not even be marked dirty for %s", run_id
            )


class RunCommands:
    """Stateless: every decision folds the journal; all state is on disk."""

    def submit(
        self,
        definition: dict[str, Any],
        *,
        actor: str,
        mode: str = "execute",
        rerun_mode: str = "resume",
    ) -> SubmitOutcome:
        """Commit one frozen definition as a durable, queueable Run revision.

        Durable order (§2.3): content-addressed definition snapshot first;
        then, under the command lock, lifecycle events (idempotent per
        (run_id, definition_revision_id) against the journal fold), the
        run.json pointer LAST -- it is derivable from the snapshot and is
        never the commit record -- and the index catch-up that writes the
        status cache. Any crash window converges on the first same-content
        retry: existing events are skipped, a missing pointer is rewritten,
        and no branch can observe "run.json exists, journal empty".
        """
        storage = get_storage()
        run_id = str(definition["run_id"])
        revision_id = str(definition["definition_revision_id"])
        storage.allocate_run(run_id)
        storage.write_definition_snapshot(run_id, definition)
        from src.services.run_index import get_run_index

        index = get_run_index()
        with _command_lock(storage, run_id):
            # Baseline row before the events publish: the async event
            # projector reacts to each append immediately and must be able to
            # identify the Run the events belong to.
            index.upsert_run(definition, storage.recover_seq(run_id))
            events = storage.read_events(run_id)
            fresh_submission = not _has_submission(events, revision_id)
            if fresh_submission:
                EventEmitter(run_id).run_submitted(
                    revision_id,
                    idempotency_key=str(definition.get("idempotency_key", "")),
                    workspace_tree_hash=str(definition.get("workspace_tree_hash", "")),
                    user_id=str(definition.get("user_id", "")),
                    cores=definition.get("cores", 4),
                    workflow_steps=0,
                    actor=actor,
                )
            fresh_queue, ticket = self._queue_locked(
                storage,
                run_id,
                revision_id,
                mode=mode,
                rerun_mode=rerun_mode,
                actor=actor,
            )
            storage.atomic_write_json(
                storage.resolve(run_id, "run.json"), definition
            )
            index.catch_up_run(storage, run_id)
        self._clear_staging_markers(storage, definition)
        return SubmitOutcome(
            run_id=run_id,
            revision_id=revision_id,
            queue_ticket=ticket,
            idempotent=not (fresh_submission or fresh_queue),
        )

    def queue(
        self,
        run_id: str,
        revision_id: str,
        mode: str,
        *,
        rerun_mode: str = "resume",
        actor: str,
        run_data: Optional[dict[str, Any]] = None,
    ) -> int:
        """Mint and append one queue request for an existing definition revision.

        Returns the ticket: a fresh mint, or the one already carried by a
        pending/in-flight request for this revision (idempotent re-request).
        """
        storage = get_storage()
        from src.services.run_index import get_run_index

        index = get_run_index()
        with _command_lock(storage, run_id):
            _fresh, ticket = self._queue_locked(
                storage,
                run_id,
                revision_id,
                mode=mode,
                rerun_mode=rerun_mode,
                actor=actor,
            )
            data = run_data or storage.read_json(
                storage.resolve(run_id, "run.json")
            )
            if data is None:
                raise ValueError(f"cannot queue {run_id}: no run.json to index")
            index.upsert_run(data, storage.recover_seq(run_id))
            index.catch_up_run(storage, run_id)
        self._clear_staging_markers(storage, data)
        return ticket

    def begin_execution(self, run_id: str) -> Optional[Lease]:
        """Append ``run.started`` and take the execution lease as one step (§2.5).

        The fold under the command lock is the dispatch authority: it decides
        which pending queue request this execution consumes, so the event and
        the lease that names the same execution can never disagree. Returns
        None when the window closed first (a cancel or terminal landed after
        the worker's own pre-checks) -- there is nothing to start.
        """
        storage = get_storage()
        with _command_lock(storage, run_id):
            try:
                state = _fold(storage.read_events(run_id))
            except Exception:
                logger.exception("begin_execution could not fold %s", run_id)
                raise
            if state.status != "QUEUED" or state.pending_queue is None:
                return None
            queue_seq, revision_id, mode = state.pending_queue
            identity = process_identity(os.getpid())
            existing = storage.read_lease(run_id)
            foreign = str(
                existing.get("worker_identity", "") if isinstance(existing, dict) else ""
            )
            if (
                foreign
                and foreign != identity
                and process_identity_alive(foreign)
            ):
                raise RuntimeError(
                    f"run {run_id} is leased by a live worker {foreign}; "
                    "refusing to start a second execution"
                )
            EventEmitter(run_id).run_started(
                revision_id=revision_id,
                mode=mode,
                pid=os.getpid(),
                worker_id=platform.node(),
            )
            record = storage.write_lease(
                run_id,
                worker_identity=identity,
                queue_seq=queue_seq,
                revision_id=revision_id,
                stage="queue-request",
            )
        _cache_status_best_effort(storage, run_id)
        return Lease(
            run_id=run_id,
            worker_identity=identity,
            queue_seq=queue_seq,
            revision_id=revision_id,
            stage=str(record["stage"]),
        )

    def heartbeat_stage(self, lease: Lease, stage: str) -> None:
        """Refresh the lease's stage at the worker's stage boundaries.

        Observability only (§2.5): the lease's liveness fact is the recorded
        process identity, never this heartbeat.
        """
        if stage not in LEASE_STAGES:
            raise ValueError(f"unknown lease stage: {stage!r}")
        get_storage().refresh_lease(lease.run_id, lease.worker_identity, stage)

    def cancel(self, run_id: str, queue_ticket: Optional[int] = None) -> bool:
        """Terminalize a still-QUEUED cancellation (§2.2). Returns whether
        the terminal landed.

        The fold-decide-append must share begin_execution's command lock:
        appending run.cancelled on the event lock alone could interleave with
        the worker's fold as [fold=QUEUED] → run.cancelled → run.started,
        which folds as "run.started is invalid from status CANCELLED" and
        permanently poisons the journal. A RUNNING run is not terminalized
        here -- the cancel marker plus the engine's own cancelled result
        close it. ``queue_ticket``, when given, must name the pending
        arrival: a cancel aimed at an arrival that already executed is
        stale and lands nothing.
        """
        storage = get_storage()
        with _command_lock(storage, run_id):
            try:
                state = _fold(storage.read_events(run_id))
            except Exception:
                logger.exception("cancel could not fold %s", run_id)
                return False
            if state.status != "QUEUED" or state.pending_queue is None:
                return False
            if queue_ticket is not None:
                pending_ticket = _queue_ticket_at(
                    storage, run_id, state.pending_queue[0]
                )
                if pending_ticket != queue_ticket:
                    return False
            appended = self._finish_locked(
                storage,
                run_id,
                "cancelled",
                run_time_seconds=0.0,
                exit_code=None,
                error_message="",
                total_tasks=0,
            )
        if appended:
            _cache_status_best_effort(storage, run_id)
        return appended

    def finish(
        self,
        run_id: str,
        outcome: str,
        *,
        run_time_seconds: float = 0.0,
        exit_code: Optional[int] = None,
        error_message: str = "",
        total_tasks: int = 0,
    ) -> bool:
        """The only terminalizer. Returns whether a terminal was appended.

        Re-folds inside the command lock and appends only for an execution
        that is still live in the fold -- an open range, or the pending queue
        request this worker was dispatched for (a death before run.started
        closes that request instead of leaving it crash-looping). A journal
        already terminalized by anyone (cancel API, reconcile rescue) yields
        no second terminal. ``outcome="rescue"`` applies the manifest rule:
        a manifest whose journal_seq covers the open range means the engine
        finished and only the worker died -- run.succeeded; else
        run.failed "orphaned". ``outcome="cancelled"`` is the API-cancel
        terminal for a run that never started.
        """
        storage = get_storage()
        with _command_lock(storage, run_id):
            appended = self._finish_locked(
                storage,
                run_id,
                outcome,
                run_time_seconds=run_time_seconds,
                exit_code=exit_code,
                error_message=error_message,
                total_tasks=total_tasks,
            )
        if appended:
            _cache_status_best_effort(storage, run_id)
        return appended

    def _finish_locked(
        self,
        storage: StorageLayout,
        run_id: str,
        outcome: str,
        *,
        run_time_seconds: float,
        exit_code: Optional[int],
        error_message: str,
        total_tasks: int,
    ) -> bool:
        """Decide and append one terminal; caller holds the command lock."""
        try:
            state = _fold(storage.read_events(run_id))
        except Exception:
            logger.exception("finish could not fold %s; no terminal appended", run_id)
            return False
        open_range = (
            state.ranges[state.open_range_index]
            if state.open_range_index is not None
            else None
        )
        if open_range is None and state.pending_queue is None:
            return False
        if outcome == "rescue":
            manifest = (
                storage.read_json(storage.resolve(run_id, "results.manifest.json"))
                or {}
            )
            if open_range is not None and (
                manifest.get("definition_revision_id") == open_range.revision_id
                and int(manifest.get("journal_seq", 0)) >= open_range.start_seq
            ):
                outcome, run_time_seconds = "succeeded", 0.0
            else:
                outcome = "failed"
                exit_code = None
                error_message = (
                    "orphaned: worker process not found (backend restarted)"
                )
        revision_id = (
            open_range.revision_id if open_range is not None else state.pending_queue[1]
        )
        if outcome == "succeeded":
            EventEmitter(run_id).run_succeeded(
                revision_id=revision_id,
                run_time_seconds=run_time_seconds,
                total_tasks=total_tasks,
            )
        elif outcome == "failed":
            EventEmitter(run_id).run_failed(
                revision_id=revision_id,
                exit_code=exit_code,
                run_time_seconds=run_time_seconds,
                error_message=error_message,
            )
        elif outcome == "cancelled":
            EventEmitter(run_id).run_cancelled(
                revision_id=revision_id,
                run_time_seconds=run_time_seconds,
            )
        else:
            raise ValueError(f"unknown finish outcome: {outcome!r}")
        return True

    def reconcile(self) -> list[str]:
        """The single recovery pass (§2.5), serialized by a global lock.

        Run by the API lifespan and the worker loop. Ownership is judged by
        the execution lease, never by engine liveness: a run whose lease
        names a live worker is untouched even with a dead engine (engine
        exit precedes manifest publication -- finalization's normal state).
        """
        storage = get_storage()
        runs = storage.data / "runs"
        if not runs.is_dir():
            return []
        with _exclusive_lock(
            storage.data / ".runtime" / "reconcile.lock",
            purpose="global reconcile",
        ):
            recovered: list[str] = []
            for directory in sorted(runs.iterdir()):
                if not directory.is_dir():
                    continue
                run_id = directory.name
                try:
                    storage.resolve(run_id, ".runtime")
                except ValueError:
                    continue
                try:
                    with _command_lock(storage, run_id):
                        recovered.extend(self._reconcile_run(storage, run_id))
                except Exception:
                    logger.exception(
                        "Run could not be projected during reconciliation: %s",
                        run_id,
                    )
            return recovered

    def _reconcile_run(self, storage: StorageLayout, run_id: str) -> list[str]:
        """Recover one Run; caller holds the global and per-run locks."""
        storage.repair_events_file(run_id)
        # Legacy bare `claimed` without a lease is a dead owner by definition:
        # the flag carried no identity, so nothing about it can be alive. The
        # migration is one pass -- after it the file no longer exists.
        legacy_claimed = storage.is_claimed(run_id)
        if legacy_claimed:
            storage.release_claim(run_id)
        try:
            state = _fold(storage.read_events(run_id))
        except Exception:
            logger.exception(
                "Run journal could not be projected during reconciliation: run_id=%s path=%s",
                run_id,
                storage.events_path(run_id),
            )
            return []
        self._complete_commit_pointer(storage, run_id, state)

        lease = storage.read_lease(run_id)
        lease_alive = (
            isinstance(lease, dict)
            and bool(lease.get("worker_identity"))
            and process_identity_alive(str(lease["worker_identity"]))
        )
        open_range = (
            state.ranges[state.open_range_index]
            if state.open_range_index is not None
            else None
        )
        if open_range is not None:
            if lease_alive:
                # The live worker owns the outcome through finalization. No
                # kill, no claim release, no terminal -- reconciling here is
                # what produced false run.failed over a publishing worker.
                return []
            storage.kill_engine_tree(run_id)
            self._finish_locked(
                storage,
                run_id,
                "rescue",
                run_time_seconds=0.0,
                exit_code=None,
                error_message="",
                total_tasks=0,
            )
            storage.release_lease(run_id)
            _cache_status_best_effort(storage, run_id)
            return [run_id]
        if state.status == "QUEUED" and (
            (lease is not None and not lease_alive) or legacy_claimed
        ):
            # The worker took the run but died before run.started; a dead
            # lease is reclaimed, and the run simply returns to the queue.
            # A LIVE lease here is a dispatched worker still inside its
            # dequeue-to-begin_execution window -- untouched, like above.
            storage.release_lease(run_id)
            EventEmitter(run_id).run_action("orphan_reclaimed", "system")
            return [run_id]
        return []

    @staticmethod
    def _complete_commit_pointer(
        storage: StorageLayout, run_id: str, state: LifecycleState
    ) -> None:
        """§2.3 close-out: a durable journal whose run.json pointer never
        landed (crash between events and pointer) is completed from the
        definition snapshot. The pointer is derived state, never the commit
        record."""
        latest_submission = next(
            (
                event
                for event in reversed(storage.read_events(run_id))
                if event.get("type") == RUN_SUBMITTED
            ),
            None,
        )
        if latest_submission is None:
            return
        raw_data = latest_submission.get("data")
        revision_id = (
            raw_data.get("revision_id") if isinstance(raw_data, dict) else None
        )
        if not isinstance(revision_id, str) or not revision_id:
            return
        try:
            pointer = storage.read_json(storage.resolve(run_id, "run.json"))
        except Exception:
            pointer = None
        if isinstance(pointer, dict) and pointer.get("definition_revision_id") == revision_id:
            return
        snapshot = storage.read_definition_snapshot(run_id, revision_id)
        if snapshot is None:
            return
        storage.atomic_write_json(storage.resolve(run_id, "run.json"), snapshot)

    def _queue_locked(
        self,
        storage: StorageLayout,
        run_id: str,
        revision_id: str,
        *,
        mode: str,
        rerun_mode: str,
        actor: str,
    ) -> tuple[bool, int]:
        """Decide and append one queue request; caller holds the command lock.

        A pending or in-flight request that already names this revision keeps
        its ticket; anything else mints one and appends ``run.queue_requested``
        carrying it. The decision folds the same journal the append extends,
        so a same-revision retry in any crash window converges to exactly one
        live queue request.
        """
        state = _fold(storage.read_events(run_id))
        authorizing_seq: Optional[int] = None
        if state.pending_queue is not None and state.pending_queue[1] == revision_id:
            authorizing_seq = state.pending_queue[0]
        else:
            open_range = next(
                (r for r in reversed(state.ranges) if r.is_open), None
            )
            if open_range is not None and open_range.revision_id == revision_id:
                # An execution of this exact revision is in flight; its
                # authorizing request already fixed this revision's arrival.
                authorizing_seq = open_range.queue_seq
        if authorizing_seq is not None:
            ticket = _queue_ticket_at(storage, run_id, authorizing_seq)
            if ticket is not None:
                return False, ticket
            # A pre-ticket journal (queued before §2.4 landed) names this
            # revision but carries no arrival order. queue_requested is legal
            # from QUEUED/RUNNING, so re-request with a minted ticket instead
            # of leaving this arrival unorderable.
        ticket = storage.mint_queue_ticket(run_id, revision_id)
        EventEmitter(run_id).run_queue_requested(
            revision_id,
            mode,
            rerun_mode=rerun_mode,
            actor=actor,
            queue_ticket=ticket,
        )
        return True, ticket

    @staticmethod
    def _clear_staging_markers(
        storage: StorageLayout, definition: dict[str, Any]
    ) -> None:
        """§2.7: the queue event is durable, so every digest this definition
        references is reachable from runs/<id>/definitions -- its staging
        marker has finished holding off the GC."""
        raw_entries = definition.get("workspace_files")
        for entry in raw_entries if isinstance(raw_entries, list) else []:
            digest = entry.get("blob_hash") if isinstance(entry, dict) else None
            if not isinstance(digest, str):
                continue
            try:
                storage.staging_marker_path(digest).unlink(missing_ok=True)
            except (OSError, ValueError):
                continue


def get_run_commands() -> RunCommands:
    """Process-wide entry point; the module is stateless by construction."""
    return RunCommands()
