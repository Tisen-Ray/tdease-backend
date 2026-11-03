"""Regressions for the adversarial behavioral audit (P0/P1/P2 fixes).

Each test names the failure scenario it pins. These are storage/worker-level
unit tests over a throwaway data root; end-to-end behavior stays covered by
the root contract suite.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from src.execution_runtime.storage import StorageLayout, process_identity


def _run_dir(root: Path, run_id: str) -> Path:
    rd = root / "runs" / run_id
    rd.mkdir(parents=True, exist_ok=True)
    return rd


def test_repair_events_file_waits_for_event_write_lock(tmp_path: Path) -> None:
    """P1-1: repair must serialize with append_event's EVENT lock, so an
    in-flight append can no longer be truncated out of the file."""
    s = StorageLayout(tmp_path)
    rd = _run_dir(tmp_path, "r1")
    good = json.dumps({"seq": 1, "type": "run.submitted"}) + "\n"
    partial = '{"seq": 2, "type": "run.queue_re'
    (rd / "events.jsonl").write_text(good + partial, encoding="utf-8")

    done = threading.Event()

    def repair() -> None:
        s.repair_events_file("r1")
        done.set()

    with s._event_write_lock("r1"):
        thread = threading.Thread(target=repair)
        thread.start()
        # While the append-side lock is held (a concurrent API run_action
        # append mid-flight), repair must not touch the file.
        assert not done.wait(0.5), "repair ran without the event write lock"
    thread.join(timeout=5)
    assert done.is_set()
    assert (rd / "events.jsonl").read_text(encoding="utf-8") == good


def test_acquire_lease_does_not_unlink_a_fresh_lease(tmp_path: Path) -> None:
    """P1-5: after judging a lease dead, the unlink must not delete a FRESH
    lease another worker created in the steal window."""
    s = StorageLayout(tmp_path)
    rd = _run_dir(tmp_path, "r1")
    fresh = {
        "schema_version": 1,
        "worker_identity": process_identity(os.getpid()),
        "stage": "startup",
        "acquired_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    (rd / ".runtime").mkdir(exist_ok=True)
    (rd / ".runtime" / "lease.json").write_text(
        json.dumps(fresh), encoding="utf-8"
    )
    dead = dict(fresh, worker_identity="999999:123.456789")
    calls = {"n": 0}
    real_read_lease = s.read_lease

    def flaky_read_lease(run_id: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return dead  # the stale record the steal decision was made on
        return real_read_lease(run_id)  # the fresh live lease on disk now

    s.read_lease = flaky_read_lease  # type: ignore[method-assign]
    assert s.acquire_lease("r1") is False
    # The fresh live lease survived: its owner keeps the Run.
    assert json.loads(
        (rd / ".runtime" / "lease.json").read_text(encoding="utf-8")
    )["worker_identity"] == fresh["worker_identity"]


def test_release_execution_slot_requires_full_identity(tmp_path: Path) -> None:
    """P2-8: a recycled pid alone must never release another process's slot."""
    import os

    s = StorageLayout(tmp_path)
    claim = tmp_path / ".runtime" / "execution.claim"
    claim.parent.mkdir(parents=True, exist_ok=True)
    # Same pid, different create_time: a different process incarnation.
    claim.write_text(f"{os.getpid()}:1.000000\n", encoding="ascii")
    s.release_execution_slot()
    assert claim.exists(), "a foreign claim was released on pid alone"
    claim.write_text(process_identity(os.getpid()) + "\n", encoding="ascii")
    s.release_execution_slot()
    assert not claim.exists()


def test_cache_status_best_effort_marks_index_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P0-1: a failed status-cache write (e.g. SQLITE_BUSY) must leave the
    index dirty so dequeue reconciles instead of trusting a stale QUEUED."""
    from src.services import run_index as run_index_mod
    from src.services.run_commands import _cache_status_best_effort

    index = run_index_mod.RunIndex(tmp_path / "run-index.sqlite3")

    def broken_update_status(run_id: str, status: str | None) -> None:
        raise RuntimeError("database is locked")

    monkeypatch.setattr(index, "update_status", broken_update_status)
    monkeypatch.setattr(run_index_mod, "get_run_index", lambda: index)
    _cache_status_best_effort(StorageLayout(tmp_path), "r1")
    assert index.is_dirty(), "failed cache write left the index trusted"


def test_dequeue_and_scan_skip_corrupt_run_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P1-2: one unreadable run.json must skip itself, not stall the queue."""
    from src.services import run_index as run_index_mod
    from src.services import run_worker

    _run_dir(tmp_path, "corrupt").joinpath("run.json").write_text(
        "{not json", encoding="utf-8"
    )
    storage = StorageLayout(tmp_path)
    monkeypatch.setattr(run_worker, "get_storage", lambda: storage)

    def broken_index():
        raise RuntimeError("index unavailable; force filesystem fallback")

    monkeypatch.setattr(run_index_mod, "get_run_index", broken_index)
    assert run_worker._dequeue() is None
    assert run_worker._has_queued_run() is False
