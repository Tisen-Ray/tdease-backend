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
    event_type: tuple(fields)
    for event_type, fields in _RULES["required_data"].items()
}
ALLOWED_FROM: dict[str, tuple[Optional[str], ...]] = {
    event_type: tuple(statuses)
    for event_type, statuses in _RULES["allowed_from"].items()
}

RUN_SUBMITTED = "run.submitted"
RUN_QUEUE_REQUESTED = "run.queue_requested"
RUN_STARTED = "run.started"


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
        raise ValueError(f"{event_type} missing required data: {', '.join(missing)}")
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

    for event in events:
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

        revision_id = str(data["revision_id"])
        if event_type == RUN_QUEUE_REQUESTED:
            mode = str(data["mode"])
            status = next_status
            current_revision_id = revision_id
            queued_mode = mode
            queued_at_seq = seq
            pending_queue = (seq, revision_id, mode)
            continue

        if event_type == RUN_STARTED:
            mode = str(data["mode"])
            if pending_queue is None:
                raise ValueError("run.started requires a preceding run.queue_requested")
            queue_seq, queued_revision_id, queued_execution_mode = pending_queue
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

        if current_revision_id is not None and revision_id != current_revision_id:
            raise ValueError(f"{event_type} revision does not match the active revision")
        status = next_status
        queued_mode = None
        queued_at_seq = None
        pending_queue = None
        if open_range_index is not None:
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

    return RunProjection(
        status=status,
        projected_at_seq=projected_at_seq,
        current_revision_id=current_revision_id,
        queued_mode=queued_mode,
        queued_at_seq=queued_at_seq,
        ranges=tuple(ranges),
    )
