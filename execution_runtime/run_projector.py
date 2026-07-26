"""
Run projection — the one rule table, implemented once.

CORE-ARCHITECTURE.md §1.2-§1.3: `events.jsonl` is the only truth for a Run's
lifecycle. This module derives status and execution ranges from an event
prefix with **no I/O** — it is a pure function of a list of event dicts —
which is what makes it shareable between the Backend (this file) and the
Client (a TypeScript port of the same rule table) against one fixture
corpus: `tests/fixtures/run-projection/`.

Rule table (applied to the event prefix in sequence order — a lookup over
the whole prefix, not a state machine where the last event always wins):

| Condition                                         | Projected status |
|----------------------------------------------------|------------------|
| A terminal event follows the last `run.started`     | that terminal status |
| A `run.started` has no terminal event after it      | RUNNING          |
| A `run.queued` has no `run.started` after it        | QUEUED           |
| No events                                           | not a Run (None) |

Terminal events are `run.succeeded`, `run.failed`, `run.cancelled`. There is
no other lifecycle axis. Non-lifecycle events (`task.*`, `runtime.message`,
`run.action`) never change `status` — this is what makes cancellation and
diagnostic noise safe: a late-arriving job event after `run.cancelled` does
not resurrect the Run, and it does not queue-flip a completed Run either.

Because rows 1-2 are keyed off "the last `run.started`", once a
`run.started` has ever appeared only a terminal event *after that same
`run.started`* can change status again. A bare `run.queued` appended later
(an audit event, or a mis-issued requeue with no accompanying
`run.started`) does not flip a terminal Run back to QUEUED and does not
resurrect a cancelled or completed Run — reopening execution always means a
new `run.started`, i.e. a new execution range (Continue).

Execution ranges (§1.3): the half-open interval from a `run.started` event
to its terminal event. A range with no terminal yet is open. There is
deliberately no Invocation entity — "which process produced this job event"
is answered by "which range contains its sequence number", which is what
lets Continue and Recompute work without an attempt counter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional

RUN_QUEUED = "run.queued"
RUN_STARTED = "run.started"
RUN_SUCCEEDED = "run.succeeded"
RUN_FAILED = "run.failed"
RUN_CANCELLED = "run.cancelled"

TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {RUN_SUCCEEDED, RUN_FAILED, RUN_CANCELLED}
)

_TERMINAL_STATUS_BY_EVENT: dict[str, str] = {
    RUN_SUCCEEDED: "SUCCEEDED",
    RUN_FAILED: "FAILED",
    RUN_CANCELLED: "CANCELLED",
}


@dataclass(frozen=True)
class ExecutionRange:
    """The half-open interval [start_seq, terminal_seq) for one execution attempt.

    `terminal_seq` and `terminal_type` are `None` while the range is open
    (a live process). At most one range may be open per Run — that
    invariant is enforced by the writers (one claim, one worker), not by
    this pure function, which only reports what the log says happened.
    """

    start_seq: int
    terminal_seq: Optional[int] = None
    terminal_type: Optional[str] = None

    @property
    def is_open(self) -> bool:
        return self.terminal_seq is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_seq": self.start_seq,
            "terminal_seq": self.terminal_seq,
            "terminal_type": self.terminal_type,
        }


@dataclass(frozen=True)
class RunProjection:
    """The pure projection of a Run's event prefix.

    `status` is `None` only when there are no events at all ("not a Run" in
    the rule table — nothing has been written for this run_id yet).
    `projected_at_seq` is the highest sequence number folded into this
    projection; a caller comparing it against the tail of `events.jsonl`
    can tell, by inspection, whether a cached projection is stale
    (CORE-ARCHITECTURE.md §1.4).
    """

    status: Optional[str]
    projected_at_seq: int = 0
    ranges: tuple[ExecutionRange, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "projected_at_seq": self.projected_at_seq,
            "ranges": [r.to_dict() for r in self.ranges],
        }


def project_run(events: Iterable[Mapping[str, Any]]) -> RunProjection:
    """Derive a Run's status and execution ranges from its event prefix.

    Pure, no I/O, no clock. Safe to call with the full contents of
    `events.jsonl` on every read; cheap to recompute, disposable, never a
    second truth (CORE-ARCHITECTURE.md §1.1 invariant 2).
    """
    projected_at_seq = 0
    ranges: list[ExecutionRange] = []
    open_range: Optional[ExecutionRange] = None

    last_started_seq: Optional[int] = None
    terminal_since_last_started: Optional[str] = None
    last_terminal_type: Optional[str] = None
    saw_queued = False

    for event in events:
        event_type = event.get("type")
        seq = event.get("seq") or 0
        if seq > projected_at_seq:
            projected_at_seq = seq

        if event_type == RUN_QUEUED:
            saw_queued = True
        elif event_type == RUN_STARTED:
            last_started_seq = seq
            terminal_since_last_started = None
            open_range = ExecutionRange(start_seq=seq)
            ranges.append(open_range)
        elif event_type in TERMINAL_EVENT_TYPES:
            last_terminal_type = event_type
            if last_started_seq is not None:
                terminal_since_last_started = event_type
            if open_range is not None:
                ranges[-1] = ExecutionRange(
                    start_seq=open_range.start_seq,
                    terminal_seq=seq,
                    terminal_type=event_type,
                )
                open_range = None
            # A terminal event with no open range (no run.started preceded
            # it, or the range it would close was already closed by an
            # earlier terminal) still updates the status tracking above —
            # the log recorded a fact — but contributes no range: a range
            # is defined only as run.started -> terminal.
        # Everything else (task.*, runtime.message, run.action, ...) is
        # diagnostic or auxiliary and never changes `status`.

    if last_started_seq is not None:
        status = (
            _TERMINAL_STATUS_BY_EVENT[terminal_since_last_started]
            if terminal_since_last_started is not None
            else "RUNNING"
        )
    elif last_terminal_type is not None:
        # No run.started was ever recorded, yet a terminal event exists —
        # not a case the table names explicitly (it presumes execution
        # began), but the most defensible reading of "the log recorded a
        # fact": the terminal outcome, not a bare run.queued, governs.
        status = _TERMINAL_STATUS_BY_EVENT[last_terminal_type]
    elif saw_queued:
        status = "QUEUED"
    else:
        status = None

    return RunProjection(
        status=status,
        projected_at_seq=projected_at_seq,
        ranges=tuple(ranges),
    )
