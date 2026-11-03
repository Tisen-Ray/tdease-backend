"""Non-blocking event-log to SQLite projection.

The durable event line is always written and fsynced before enqueue. SQLite is
only a rebuildable read model, so queue pressure or lock contention must never
propagate back into the Worker or subprocess pipe readers.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.execution_runtime.storage import StorageLayout
from src.services.run_index import ProjectionGapError, RunIndex, get_run_index


logger = logging.getLogger(__name__)
_QUEUE: queue.Queue[tuple[Path, str, dict[str, Any]]] = queue.Queue(maxsize=4096)
_START_LOCK = threading.Lock()
_THREAD: threading.Thread | None = None
_READY_DATABASES: set[Path] = set()


def register_projection_database(database: Path) -> None:
    """Declare that schema migration committed for this process/database."""
    _READY_DATABASES.add(Path(database).resolve())


def enqueue_event_projection(run_id: str, event: dict[str, Any]) -> None:
    """Queue a fsynced event without ever waiting for SQLite or queue space."""
    index = get_run_index()
    if index.database.resolve() not in _READY_DATABASES:
        index.mark_dirty()
        return
    _ensure_started()
    try:
        _QUEUE.put_nowait((index.database, run_id, dict(event)))
    except queue.Full:
        index.mark_dirty()
        logger.warning("Run event projection queue full; marked index dirty")


def _ensure_started() -> None:
    global _THREAD
    if _THREAD is not None and _THREAD.is_alive():
        return
    with _START_LOCK:
        if _THREAD is not None and _THREAD.is_alive():
            return
        _THREAD = threading.Thread(
            target=_project_loop,
            name="run-event-projector",
            daemon=True,
        )
        _THREAD.start()


def _project_loop() -> None:
    while True:
        first = _QUEUE.get()
        batch = [first]
        for _ in range(49):
            try:
                batch.append(_QUEUE.get_nowait())
            except queue.Empty:
                break
        grouped: dict[tuple[Path, str], list[dict[str, Any]]] = defaultdict(list)
        for database, run_id, event in batch:
            grouped[(database, run_id)].append(event)
        for (database, run_id), events in grouped.items():
            index = RunIndex(database)
            try:
                events.sort(key=lambda item: int(item.get("seq", 0)))
                index.project_events(run_id, events)
            except ProjectionGapError:
                try:
                    storage = StorageLayout(database.parent.parent)
                    index.catch_up_run(storage, run_id)
                except Exception:
                    index.mark_dirty()
                    _retry_later(database, run_id, events[-1])
                    logger.exception("Run event projection gap repair deferred")
            except Exception:
                index.mark_dirty()
                _retry_later(database, run_id, events[-1])
                logger.exception(
                    "Run event projection deferred; filesystem truth is intact"
                )
        for _ in batch:
            _QUEUE.task_done()


def _retry_later(database: Path, run_id: str, event: dict[str, Any]) -> None:
    """Retry on the projector thread; producers remain strictly non-blocking."""
    time.sleep(0.1)
    try:
        _QUEUE.put_nowait((database, run_id, event))
    except queue.Full:
        RunIndex(database).mark_dirty()
