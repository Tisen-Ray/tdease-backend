"""Pure lifecycle projection from the canonical Run journal.

The transition vocabulary lives in ``src/contracts/run_lifecycle.json``.
Both Backend and Client load that declaration, so lifecycle ownership does
not drift into two hand-maintained state machines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

from src.contracts.lifecycle_declaration import LIFECYCLE_DECLARATION

_RULES = LIFECYCLE_DECLARATION
STATUS_BY_EVENT: dict[str, str] = dict(_RULES["statuses"])
TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(_RULES["terminal_events"])
EXECUTION_MODES: frozenset[str] = frozenset(_RULES["execution_modes"])
REQUIRED_DATA: dict[str, tuple[str, ...]] = {
    event_type: tuple(fields) for event_type, fields in _RULES["required_data"].items()
}
ALLOWED_FROM: dict[str, tuple[Optional[str], ...]] = {
    event_type: tuple(statuses)
    for event_type, statuses in _RULES["allowed_from"].items()
}

RUN_SUBMITTED = "run.submitted"
RUN_QUEUE_REQUESTED = "run.queue_requested"
RUN_STARTED = "run.started"
LEGACY_REVISION_ID = "legacy-schema-v1"


def _normalize_lifecycle_event(event: Mapping[str, Any]) -> Mapping[str, Any]:
    """Translate persisted pre-contract lifecycle events at the replay boundary."""
    if event.get("type") != "run.queued" or int(event.get("schema_version") or 1) != 1:
        return event

    legacy_data = event.get("data")
    data = dict(legacy_data) if isinstance(legacy_data, Mapping) else {}
    data["revision_id"] = LEGACY_REVISION_ID
    data["mode"] = "continue" if data.get("rerun_mode") == "resume" else "execute"
    return {**event, "type": RUN_QUEUE_REQUESTED, "data": data}


@dataclass(frozen=True)
class ExecutionRange:
    """One process execution and the queue request that authorized it."""

    start_seq: int
    queue_seq: int
    revision_id: str
    mode: str
    terminal_seq: Optional[int] = None
    terminal_type: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.terminal_seq is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "queue_seq": self.queue_seq,
            "start_seq": self.start_seq,
            "revision_id": self.revision_id,
            "mode": self.mode,
            "terminal_seq": self.terminal_seq,
            "terminal_type": self.terminal_type,
        }


@dataclass(frozen=True)
class RunProjection:
    status: Optional[str]
    projected_at_seq: int = 0
    current_revision_id: Optional[str] = None
    queued_mode: Optional[str] = None
    queued_at_seq: Optional[int] = None
    ranges: tuple[ExecutionRange, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "projected_at_seq": self.projected_at_seq,
            "current_revision_id": self.current_revision_id,
            "queued_mode": self.queued_mode,
            "queued_at_seq": self.queued_at_seq,
            "ranges": [execution_range.to_dict() for execution_range in self.ranges],
        }


def _lifecycle_data(event: Mapping[str, Any]) -> Mapping[str, Any]:
    event_type = event.get("type")
    required = REQUIRED_DATA.get(str(event_type))
    if required is None:
        return {}
    data = event.get("data")
    if not isinstance(data, Mapping):
        raise ValueError(f"{event_type} requires object data")
    missing = [field_name for field_name in required if not data.get(field_name)]
    if missing:
        # Backward compatibility: `revision_id` and `mode` on run.started /
        # run.queue_requested became required in a later schema revision than
        # some persisted journals were written under. Rejecting those legacy
        # events crashes Backend startup (reconcile_orphaned_runs replays every
        # Run journal at lifespan entry). These two fields are reconstructable
        # from surrounding events, so tolerate their absence here and let
        # project_run backfill from tracked state. Other missing fields remain
        # hard errors — they are not derivable and a gap would corrupt the fold.
        reconstructable = {"revision_id", "mode"}
        hard_missing = [name for name in missing if name not in reconstructable]
        if hard_missing:
            raise ValueError(
                f"{event_type} missing required data: {', '.join(hard_missing)}"
            )
    mode = data.get("mode")
    if mode is not None and mode not in EXECUTION_MODES:
        raise ValueError(f"{event_type} has invalid execution mode: {mode}")
    return data


def project_run(events: Iterable[Mapping[str, Any]]) -> RunProjection:
    """Fold a journal prefix without consulting mutable Run metadata."""

    status: Optional[str] = None
    projected_at_seq = 0
    current_revision_id: Optional[str] = None
    queued_mode: Optional[str] = None
    queued_at_seq: Optional[int] = None
    pending_queue: Optional[tuple[int, str, str]] = None
    ranges: list[ExecutionRange] = []
    open_range_index: Optional[int] = None

    for persisted_event in events:
        event = _normalize_lifecycle_event(persisted_event)
        seq = int(event.get("seq") or 0)
        if seq <= projected_at_seq:
            continue
        projected_at_seq = seq
        event_type = str(event.get("type") or "")
        data = _lifecycle_data(event)
        allowed_from = ALLOWED_FROM.get(event_type)
        if allowed_from is not None and status not in allowed_from:
            raise ValueError(f"{event_type} is invalid from status {status}")

        if event_type == RUN_SUBMITTED:
            current_revision_id = str(data["revision_id"])
            continue

        next_status = STATUS_BY_EVENT.get(event_type)
        if next_status is None:
            continue

        # revision_id / mode are reconstructable for legacy journals written
        # before they became required (see _lifecycle_data). For run.queue_requested
        # the revision can only be backfilled if a run.submitted established it
        # earlier in the same fold — otherwise the identity is genuinely unknowable
        # and must stay a hard error. run.started backfills from its pending queue.
        if data.get("revision_id"):
            revision_id = str(data["revision_id"])
        elif event_type == RUN_STARTED and pending_queue is not None:
            revision_id = pending_queue[1]
        elif current_revision_id is not None:
            revision_id = current_revision_id
        else:
            raise ValueError(f"{event_type} missing required data: revision_id")
        if event_type == RUN_QUEUE_REQUESTED:
            mode = str(data["mode"]) if data.get("mode") else (queued_mode or "execute")
            current_revision_id = revision_id
            queued_mode = mode
            queued_at_seq = seq
            pending_queue = (seq, revision_id, mode)
            if open_range_index is None:
                # No execution in flight: the Run is queued now. Otherwise the
                # request is pending and the projected status stays RUNNING
                # until the open range terminates.
                status = next_status
            continue

        if event_type == RUN_STARTED:
            if pending_queue is None:
                raise ValueError("run.started requires a preceding run.queue_requested")
            queue_seq, queued_revision_id, queued_execution_mode = pending_queue
            # revision_id was resolved above (from data, else the pending queue);
            # backfill legacy run.started that omitted mode from the matching
            # queue request, then validate consistency as usual.
            mode = str(data["mode"]) if data.get("mode") else queued_execution_mode
            if (revision_id, mode) != (queued_revision_id, queued_execution_mode):
                raise ValueError("run.started does not match its queue request")
            if open_range_index is not None:
                raise ValueError("run.started cannot overlap an open execution range")
            ranges.append(ExecutionRange(seq, queue_seq, revision_id, mode))
            open_range_index = len(ranges) - 1
            pending_queue = None
            status = next_status
            current_revision_id = revision_id
            queued_mode = None
            queued_at_seq = None
            continue

        # A terminal event belongs to the execution range that is open (or, for a
        # journal without ranges, to the active revision). A newer definition
        # submitted while that range ran must not invalidate its terminal event.
        had_open_range = open_range_index is not None
        active_revision = (
            ranges[open_range_index].revision_id
            if had_open_range
            else current_revision_id
        )
        if active_revision is not None and revision_id != active_revision:
            raise ValueError(
                f"{event_type} revision does not match the active revision"
            )
        if had_open_range:
            active = ranges[open_range_index]
            ranges[open_range_index] = ExecutionRange(
                start_seq=active.start_seq,
                queue_seq=active.queue_seq,
                revision_id=active.revision_id,
                mode=active.mode,
                terminal_seq=seq,
                terminal_type=event_type,
            )
            open_range_index = None
        if had_open_range and pending_queue is not None:
            # A definition was queued while this execution ran: the Run is queued
            # for it, not terminal. The finished execution's own result stays in
            # the journal and its results manifest. A queue request with no
            # execution in flight (pre-launch validation) keeps the ordinary
            # terminal projection below.
            status = STATUS_BY_EVENT[RUN_QUEUE_REQUESTED]
            continue
        status = next_status
        queued_mode = None
        queued_at_seq = None
        pending_queue = None

    return RunProjection(
        status=status,
        projected_at_seq=projected_at_seq,
        current_revision_id=current_revision_id,
        queued_mode=queued_mode,
        queued_at_seq=queued_at_seq,
        ranges=tuple(ranges),
    )
