"""
TDEase Storage Layout -- system-wide single file-write primitive.

Not an adapter, not an interceptor. This IS the file primitive.
No module may use raw open/write/mkdir directly.

Rules (CONVERGENCE-PLAN.md Sec 3.5):
- atomic_write: temp + fsync + rename + tmp cleanup + parent fsync
- append_event: JSONL, single-writer, internally-allocated monotonic seq
- blob: store/.incoming/<id> -> rename to digest key
- temp: TemporaryDirectory only
- logs: fixed names, size caps, rotation, deep write operations
- trash: move -> GC with retention

P1 fixes (code review):
- allocate_run: exist_ok=True (API + worker both call, must be idempotent)
- recover_seq: returns persisted last seq from events.jsonl
- check_cancelled / mark_cancelled: unified cancel signal
- resolve: validates run_id and containment

P2 fixes:
- atomic_write: tmp cleanup on write/fsync/replace failure; fsync parent
- append_event: allocates seq internally (only writer)
- append_runtime_record / append_task_output: deep log operations

CORE-ARCHITECTURE.md Sec 1.4:
- definitions/<definition_revision_id>.json is the frozen execution definition.
- run.json is the latest-definition pointer for list/status views.
- events.jsonl is the lifecycle truth and is projected in memory or into the
  rebuildable SQLite read model. Storage never writes lifecycle state back into
  a definition snapshot.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from src.execution_runtime.run_projector import RunProjection, project_run

logger = logging.getLogger(__name__)

RUN_ID_PATTERN = __import__("re").compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


def _normalize_run_relative_path(rel: str) -> Optional[str]:
    """Canonical slash form of a run-relative path, or None when unsafe.

    Traversal segments, absolute prefixes, and Windows drive letters are
    rejected: manifest paths are claims about files under one run root.
    """
    normalized = rel.replace("\\", "/").lstrip("/")
    parts = normalized.split("/")
    if not normalized or ".." in parts or (len(parts[0]) == 2 and parts[0][1] == ":"):
        return None
    return normalized


def _claimed_entries(raw: Any) -> list[dict[str, Any]]:
    """Well-formed claim entries from a manifest list; anything else is noise."""
    if not isinstance(raw, list):
        return []
    return [
        entry
        for entry in raw
        if isinstance(entry, dict)
        and isinstance(entry.get("path"), str)
        and isinstance(entry.get("sha256"), str)
    ]


def _is_reparse_point(path: Path) -> bool:
    """True for a Windows junction / mount point (and for POSIX symlinks).

    Python reports junctions through `st_reparse_tag`, not `S_ISLNK`, so a
    plain `os.path.islink` check would miss them and a recursive delete would
    follow the link into the node catalog.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_reparse_tag", 0))


_TERMINAL_EVENT_BY_STATUS = {
    "SUCCEEDED": "run.succeeded",
    "FAILED": "run.failed",
    "CANCELLED": "run.cancelled",
}


def _project_lifecycle_metadata(
    events: list[dict[str, Any]], status: object
) -> dict[str, Any]:
    """Project public lifecycle metadata from the same event prefix as status."""
    status_text = str(status) if status is not None else ""
    if status_text == "QUEUED":
        return {
            "started_at": None,
            "finished_at": None,
            "exit_code": None,
            "error": None,
        }

    started = next(
        (event for event in reversed(events) if event.get("type") == "run.started"),
        None,
    )
    projected = {
        "started_at": started.get("timestamp") if started else None,
        "finished_at": None,
        "exit_code": None,
        "error": None,
    }
    terminal_type = _TERMINAL_EVENT_BY_STATUS.get(status_text)
    if terminal_type is None:
        return projected

    terminal = next(
        (event for event in reversed(events) if event.get("type") == terminal_type),
        None,
    )
    if terminal is None:
        return projected
    raw_data = terminal.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    projected["finished_at"] = terminal.get("timestamp")
    if status_text == "SUCCEEDED":
        projected["exit_code"] = 0
    elif status_text == "FAILED":
        projected["exit_code"] = data.get("exit_code")
        projected["error"] = data.get("error_message") or terminal.get("message")
    return projected


def process_identity(pid: int) -> str:
    """`<pid>:<create_time>` -- a pid alone is not an identity on Windows.

    Windows recycles pids aggressively; a stale claim or engine record whose pid
    now belongs to an unrelated process must never be treated as alive.
    """
    import psutil

    try:
        return f"{pid}:{psutil.Process(pid).create_time():.6f}"
    except Exception:
        return f"{pid}:"


def process_identity_alive(identity: str) -> bool:
    """Whether the process recorded as `identity` is still the same process."""
    import psutil

    pid_text, _, created = identity.partition(":")
    try:
        pid = int(pid_text)
    except ValueError:
        return False
    try:
        process = psutil.Process(pid)
    except Exception:
        return False
    if not created:
        return True  # legacy record: pid liveness is all it captured
    try:
        return abs(process.create_time() - float(created)) < 1.0
    except Exception:
        return False


def read_complete_lines_from(path: Path, offset: int = 0) -> tuple[list[bytes], int]:
    """Read only the complete lines appended after a byte cursor.

    Binary read delimited by the last newline: the returned cursor stops
    before an incomplete trailing line, so a concurrent writer can finish
    that line and the next read will see it.
    """
    if not path.exists():
        return [], 0
    size = path.stat().st_size
    cursor = min(max(offset, 0), size)
    with open(path, "rb") as stream:
        stream.seek(cursor)
        payload = stream.read()
    if not payload:
        return [], cursor
    last_newline = payload.rfind(b"\n")
    if last_newline < 0:
        return [], cursor
    complete = payload[: last_newline + 1]
    return complete.splitlines(), cursor + len(complete)


@contextmanager
def _exclusive_lock(lock: Path, *, purpose: str, timeout: float = 5.0) -> Iterator[None]:
    """Cross-process mutual exclusion on one O_CREAT|O_EXCL lock file.

    The same pattern as the per-run event write lock, factored out for scopes
    beyond one journal append (the global ticket mint, the run command
    critical section): pid recorded for stale-owner detection, bounded wait,
    Windows-tolerant release.
    """
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, f"{os.getpid()}\n".encode("ascii"))
                os.fsync(fd)
            finally:
                os.close(fd)
            break
        except (FileExistsError, PermissionError):
            stale = False
            try:
                age = time.time() - lock.stat().st_mtime
                if age > 1.0:
                    owner = int(lock.read_text(encoding="ascii").strip())
                    import psutil

                    stale = not psutil.pid_exists(owner) or age > 30.0
            except FileNotFoundError:
                continue
            except (OSError, TypeError, ValueError):
                try:
                    stale = time.time() - lock.stat().st_mtime > 30.0
                except FileNotFoundError:
                    continue
            if stale:
                StorageLayout._unlink_event_lock(lock)
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out acquiring the {purpose} lock")
            time.sleep(0.005)
    try:
        yield
    finally:
        StorageLayout._unlink_event_lock(lock)


class StorageLayout:
    """TDEase single file primitive."""

    def __init__(
        self,
        data_root: str | Path,
        cache_root: str | Path | None = None,
        trash_root: str | Path | None = None,
    ):
        self.data = Path(data_root)
        self.cache = Path(cache_root) if cache_root else self.data / "cache"
        self.trash = Path(trash_root) if trash_root else self.data / "trash"

    # -- Bootstrap --

    def bootstrap(self) -> None:
        """One-time fixed directory layout creation.

        Aligned with electron/runtime_config.cjs ensureRuntimeDirectories.
        Does not create workspaces/ (legacy layout: ownership is a run.json
        field, not a directory). Does not create system/ (a release asset
        projection, not a runtime mkdir).
        """
        for d in [
            self.data / "database",
            self.data / "store",
            self.data / "runs",
            self.cache,
            self.trash,
            self.trash / "runs",
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # -- Run directory --

    def allocate_run(self, run_id: str) -> Path:
        """Idempotently create the run directory layout. Safe for both API and worker."""
        self._validate_run_id(run_id)
        run_dir = self.data / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        for sub in [
            "results",
            "logs",
            "logs/tasks",
            "config",
            ".runtime",
            ".runtime/task-records",
            ".runtime/incomplete",
            ".runtime/locks",
        ]:
            (run_dir / sub).mkdir(parents=True, exist_ok=True)
        return run_dir

    def _validate_run_id(self, run_id: str) -> None:
        if not RUN_ID_PATTERN.match(run_id):
            raise ValueError(f"Invalid run_id: {run_id!r}")
        resolved = os.path.normpath(str(self.data / "runs" / run_id))
        prefix = os.path.normpath(str(self.data / "runs")) + os.sep
        if not resolved.startswith(prefix):
            raise ValueError(f"run_id escapes data root: {run_id!r}")

    def resolve(self, run_id: str, *segments: str) -> Path:
        """Resolve a path inside a run directory. Validates run_id and containment."""
        self._validate_run_id(run_id)
        base = self.data / "runs" / run_id
        p = base
        for seg in segments:
            p = p / seg
        resolved = os.path.normpath(str(p))
        base_str = os.path.normpath(str(base)) + os.sep
        if not resolved.startswith(base_str) and resolved != os.path.normpath(
            str(base)
        ):
            raise ValueError(f"Path escapes run dir: {segments}")
        return p

    # -- Atomic write --

    def atomic_write(self, target: Path, content: str | bytes) -> None:
        """
        Atomically write a canonical file.

        Same-directory temp file -> fsync -> os.replace -> fsync parent -> cleanup.
        """
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(target.parent),
            prefix="." + target.name + ".",
        )
        try:
            payload = content.encode("utf-8") if isinstance(content, str) else content
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        try:
            # Windows refuses os.replace onto a read-only inode (a stale CAS
            # hardlink sitting at the target path); clear the flag first.
            if not os.lstat(target).st_mode & 0o222:
                os.chmod(target, self._WRITABLE_MODE)
        except FileNotFoundError:
            pass
        try:
            os.replace(tmp, target)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        # Fsync parent directory for durability (Unix only -- Windows rejects dir fsync)
        if os.name != "nt":
            dfd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)

    def atomic_write_json(self, target: Path, obj: dict | list) -> None:
        self.atomic_write(
            target, json.dumps(obj, indent=2, ensure_ascii=False, default=str)
        )

    def remove_tree(self, target: Path, *, ignore_errors: bool = False) -> None:
        """Remove a Backend-owned tree without following directory links.

        `shutil.rmtree` descends through a junction (the `.snakemake` engine
        alias), so deleting a Run would delete the state it points at. Unlink
        every reparse point top-down first, then remove what remains.
        """
        target = Path(target)
        if _is_reparse_point(target):
            # The tree itself is a link (a Run's `nodes/<id>`): drop the link,
            # never the package it points at.
            try:
                os.rmdir(target)
            except OSError:
                target.unlink(missing_ok=True)
            return
        if not target.exists():
            return
        for root, dirs, files in os.walk(target, topdown=True):
            for name in list(dirs):
                candidate = Path(root) / name
                if _is_reparse_point(candidate):
                    try:
                        os.rmdir(candidate)
                    except OSError:
                        candidate.unlink(missing_ok=True)
                    dirs.remove(name)
            for name in files:
                # Read-only inodes (CAS hardlinks linked into the tree) block
                # Windows unlink; make them removable before rmtree.
                candidate = Path(root) / name
                try:
                    if not candidate.lstat().st_mode & 0o222:
                        os.chmod(candidate, self._WRITABLE_MODE)
                except OSError:
                    pass
        shutil.rmtree(target, ignore_errors=ignore_errors)

    def read_json(self, path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def file_digest(self, path: Path, chunk_size: int = 1024 * 1024) -> str:
        """Hash large files without loading RAW/mzML/results into memory."""
        digest = hashlib.sha256()
        with open(path, "rb") as source:
            while chunk := source.read(chunk_size):
                digest.update(chunk)
        return digest.hexdigest()

    def claim_run(self, run_id: str) -> bool:
        """Atomically claim one queued run; claim storage is runtime-owned.

        Superseded as the worker's dequeue guard by the execution lease below;
        kept for surfaces that clear a leftover claim of a terminal Run
        (``rerun``) and for the legacy-claim migration in reconcile.
        """
        claim = self.resolve(run_id, ".runtime", "claimed")
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except FileExistsError:
            return False

    def release_claim(self, run_id: str) -> None:
        self.resolve(run_id, ".runtime", "claimed").unlink(missing_ok=True)

    def is_claimed(self, run_id: str) -> bool:
        return self.resolve(run_id, ".runtime", "claimed").exists()

    # -- Execution lease (BACKEND-RUN-SERVICE §2.5) --

    LEASE_SCHEMA_VERSION = 1

    def lease_path(self, run_id: str) -> Path:
        return self.resolve(run_id, ".runtime", "lease.json")

    def read_lease(self, run_id: str) -> Optional[dict[str, Any]]:
        """The parsed lease record, or None when absent or unreadable."""
        try:
            return self.read_json(self.lease_path(run_id))
        except (OSError, json.JSONDecodeError):
            return None

    def _lease_payload(
        self,
        *,
        worker_identity: str,
        queue_seq: Optional[int],
        revision_id: Optional[str],
        stage: str,
        acquired_at: Optional[str] = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "schema_version": self.LEASE_SCHEMA_VERSION,
            "worker_identity": worker_identity,
            "queue_seq": queue_seq,
            "revision_id": revision_id,
            "stage": stage,
            "acquired_at": acquired_at or now,
            "updated_at": now,
        }

    def acquire_lease(self, run_id: str, *, stage: str = "startup") -> bool:
        """Take one Run's execution lease at dequeue (O_CREAT|O_EXCL).

        The lease names the owning worker process (pid + creation time), so a
        lease whose owner died -- including a Windows pid recycle -- is stolen
        on sight instead of wedging the Run behind a lock nobody holds. A live
        owner is authoritative: the acquirer backs off and the Run is skipped.
        """
        target = self.lease_path(run_id)
        identity = process_identity(os.getpid())
        payload = json.dumps(
            self._lease_payload(
                worker_identity=identity,
                queue_seq=None,
                revision_id=None,
                stage=stage,
            ),
            ensure_ascii=False,
        )
        for _attempt in range(3):
            try:
                fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                lease = self.read_lease(run_id)
                if (
                    isinstance(lease, dict)
                    and lease.get("worker_identity")
                    and process_identity_alive(str(lease["worker_identity"]))
                ):
                    return False
                try:
                    target.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            return True
        return False

    def write_lease(
        self,
        run_id: str,
        *,
        worker_identity: str,
        queue_seq: Optional[int],
        revision_id: Optional[str],
        stage: str,
    ) -> dict[str, Any]:
        """Rewrite the lease under the run command lock (begin_execution).

        ``acquired_at`` survives the rewrite so the record keeps naming when
        this execution was taken, not when its stage last advanced.
        """
        previous = self.read_lease(run_id)
        acquired_at = (
            previous.get("acquired_at") if isinstance(previous, dict) else None
        )
        record = self._lease_payload(
            worker_identity=worker_identity,
            queue_seq=queue_seq,
            revision_id=revision_id,
            stage=stage,
            acquired_at=acquired_at if isinstance(acquired_at, str) else None,
        )
        self.atomic_write_json(self.lease_path(run_id), record)
        return record

    def refresh_lease(self, run_id: str, worker_identity: str, stage: str) -> None:
        """Advance the owning worker's lease stage (observability only)."""
        lease = self.read_lease(run_id)
        if not isinstance(lease, dict) or lease.get("worker_identity") != worker_identity:
            return
        lease["stage"] = stage
        lease["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.atomic_write_json(self.lease_path(run_id), lease)

    def release_lease(self, run_id: str) -> None:
        self.lease_path(run_id).unlink(missing_ok=True)

    def claim_execution_slot(self) -> bool:
        """Acquire the Backend-wide execution slot.

        Run claims prevent duplicate execution of one Run. This second lock
        prevents different workers or Backend processes from executing two
        Runs concurrently on the same deployment. The claim records the owner's
        process identity (pid + creation time), so a pid recycled by Windows
        cannot make a dead owner look alive and wedge the queue forever.
        """
        claim = self.data / ".runtime" / "execution.claim"
        claim.parent.mkdir(parents=True, exist_ok=True)
        payload = f"{process_identity(os.getpid())}\n".encode("ascii")
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if process_identity_alive(claim.read_text(encoding="ascii").strip()):
                    return False
                claim.unlink(missing_ok=True)
                fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except (FileNotFoundError, FileExistsError, OSError):
                return False
        try:
            os.write(fd, payload)
            os.fsync(fd)
        finally:
            os.close(fd)
        return True

    def release_execution_slot(self) -> None:
        """Release this process's Backend-wide execution slot."""
        claim = self.data / ".runtime" / "execution.claim"
        try:
            owner = claim.read_text(encoding="ascii").strip()
        except (FileNotFoundError, OSError):
            return
        if owner.split(":", 1)[0] == str(os.getpid()):
            claim.unlink(missing_ok=True)

    # -- Global queue tickets (BACKEND-RUN-SERVICE §2.4) --

    def queue_tickets_path(self) -> Path:
        return self.data / ".runtime" / "queue.tickets.jsonl"

    def mint_queue_ticket(self, run_id: str, revision_id: str) -> int:
        """Append one line to the global mint log and return its ticket number.

        Queue arrival order is a deployment-global monotonic integer: minted
        once per queue request under a global lock, carried by the
        run.queue_requested journal event, and cached in the Run index. The
        mint log exists only to mint -- arrival truth rebuilds from the
        journals alone -- so a crash between a mint and the journal append
        that carries it merely wastes the number.
        """
        path = self.queue_tickets_path()
        with _exclusive_lock(path.with_suffix(".lock"), purpose="queue ticket mint"):
            ticket = 0
            for line in reversed(self.tail_text_lines(path, 8)):
                try:
                    ticket = int(json.loads(line).get("ticket", 0))
                    break
                except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                    continue
            ticket += 1
            record = (
                json.dumps(
                    {
                        "ticket": ticket,
                        "run_id": run_id,
                        "revision_id": revision_id,
                        "ts": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            # A crash mid-append can leave a partial trailing line; start the
            # new record on a fresh line so the two never glue together.
            if path.exists():
                with open(path, "rb+") as stream:
                    stream.seek(0, os.SEEK_END)
                    if stream.tell():
                        stream.seek(-1, os.SEEK_CUR)
                        if stream.read(1) != b"\n":
                            stream.write(b"\n")
                    stream.write(record.encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
            else:
                with open(path, "wb") as stream:
                    stream.write(record.encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
        return ticket

    def latest_queue_tickets(self) -> dict[str, int]:
        """Each Run's most recently minted ticket.

        The dequeue filesystem fallback sorts by this map so it agrees with
        the index path (§2.4: one ordering everywhere). Runs absent from the
        log -- journals written before tickets existed -- carry no ticket and
        order after ticketed arrivals.
        """
        path = self.queue_tickets_path()
        tickets: dict[str, int] = {}
        if not path.exists():
            return tickets
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and isinstance(record.get("ticket"), int):
                run_id = record.get("run_id")
                if isinstance(run_id, str):
                    tickets[run_id] = record["ticket"]
        return tickets

    # -- Events (JSONL append, single-writer) --

    def events_path(self, run_id: str) -> Path:
        return self.resolve(run_id, "events.jsonl")

    def recover_seq(self, run_id: str) -> int:
        """Return the last persisted seq without scanning the whole event log."""
        p = self.events_path(run_id)
        if not p.exists():
            return 0
        with open(p, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            end = stream.tell()
            pending = b""
            while end > 0:
                size = min(64 * 1024, end)
                end -= size
                stream.seek(end)
                pending = stream.read(size) + pending
                lines = pending.splitlines()
                if end > 0 and lines:
                    pending = lines.pop(0)
                else:
                    pending = b""
                for line in reversed(lines):
                    if not line.strip():
                        continue
                    try:
                        return int(json.loads(line).get("seq", 0))
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
            if pending.strip():
                try:
                    return int(json.loads(pending).get("seq", 0))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
        return 0

    def append_event(self, run_id: str, event: dict[str, Any]) -> int:
        """
        Append one event line. Allocates and returns the monotonic seq.
        Starts from recover_seq + 1; callers should not set seq manually.
        """
        with self._event_write_lock(run_id):
            current = self.recover_seq(run_id)
            event["seq"] = current + 1
            line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
            p = self.events_path(run_id)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
                os.fsync(f.fileno())
        return event["seq"]

    @contextmanager
    def _event_write_lock(self, run_id: str) -> Iterator[None]:
        """Serialize one Run's sequence allocation across API/Worker processes."""
        lock = self.resolve(run_id, ".runtime", "events.lock")
        lock.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + 5.0
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                try:
                    os.write(fd, f"{os.getpid()}\n".encode("ascii"))
                    os.fsync(fd)
                finally:
                    os.close(fd)
                break
            except (FileExistsError, PermissionError):
                stale = False
                try:
                    age = time.time() - lock.stat().st_mtime
                    if age > 1.0:
                        owner = int(lock.read_text(encoding="ascii").strip())
                        import psutil

                        stale = not psutil.pid_exists(owner) or age > 30.0
                except FileNotFoundError:
                    continue
                except (OSError, TypeError, ValueError):
                    try:
                        stale = time.time() - lock.stat().st_mtime > 30.0
                    except FileNotFoundError:
                        continue
                if stale:
                    self._unlink_event_lock(lock)
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out acquiring event writer for {run_id}")
                time.sleep(0.005)
        try:
            yield
        finally:
            self._unlink_event_lock(lock)

    @staticmethod
    def _unlink_event_lock(lock: Path) -> None:
        """Release a tiny lease despite transient Windows reader handles."""
        for _ in range(200):
            try:
                lock.unlink(missing_ok=True)
                return
            except PermissionError:
                time.sleep(0.005)
        lock.unlink(missing_ok=True)

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        p = self.events_path(run_id)
        if not p.exists():
            return []
        events = []
        for line in p.read_text(encoding="utf-8").strip().splitlines():
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return events

    def read_event_lines_from(
        self,
        run_id: str,
        offset: int = 0,
    ) -> tuple[list[tuple[dict[str, Any], str]], int]:
        """Read only complete event lines appended after a byte cursor.

        The returned cursor stops before an incomplete trailing line, so a
        concurrent writer can finish that line and the next read will see it.
        """
        lines, cursor = read_complete_lines_from(self.events_path(run_id), offset)
        events: list[tuple[dict[str, Any], str]] = []
        for raw_line in lines:
            if not raw_line.strip():
                continue
            try:
                line = raw_line.decode("utf-8")
                events.append((json.loads(line), line))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return events, cursor

    def event_offset_after_seq(self, run_id: str, seq: int) -> int:
        """Locate the byte cursor immediately after ``seq`` for SSE resume."""
        if seq <= 0:
            return 0
        offset = 0
        while True:
            events, next_offset = self.read_event_lines_from(run_id, offset)
            for event, line in events:
                line_end = offset + len((line + "\n").encode("utf-8"))
                offset = line_end
                if int(event.get("seq", 0)) >= seq:
                    return offset
            if next_offset <= offset or not events:
                return next_offset
            offset = next_offset

    @staticmethod
    def tail_text_lines(
        path: Path, limit: int, chunk_size: int = 64 * 1024
    ) -> list[str]:
        """Return a bounded line tail by seeking backward from file end."""
        if limit <= 0 or not path.is_file():
            return []
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            position = stream.tell()
            chunks: list[bytes] = []
            newline_count = 0
            while position > 0 and newline_count <= limit:
                size = min(chunk_size, position)
                position -= size
                stream.seek(position)
                chunk = stream.read(size)
                chunks.append(chunk)
                newline_count += chunk.count(b"\n")
        return (
            b"".join(reversed(chunks))
            .decode("utf-8", errors="replace")
            .splitlines()[-limit:]
        )

    def repair_events_file(self, run_id: str) -> int:
        """Truncate events.jsonl to its last complete, parseable line.

        A crash mid-append (append_event's f.write interrupted between
        open and fsync) can leave a partial trailing line: no trailing
        newline, or JSON truncated mid-object. Left in place, that partial
        line is not just unreadable -- the next append glues its own
        well-formed line onto the tail of the garbage bytes with no
        separating newline, corrupting the new line too.

        The rule (CORE-ARCHITECTURE.md Sec 1.4/1.5 crash-point requirement):
        a single writer, single-line-at-a-time log can only be corrupted at
        its tail, so the first line that fails to parse ends the valid
        prefix -- everything from there on is dropped. Idempotent: a clean
        file is rewritten byte-for-byte and this returns 0.

        Returns the number of bytes removed (0 if nothing needed repair).
        """
        p = self.events_path(run_id)
        if not p.exists():
            return 0
        raw = p.read_bytes()
        if not raw:
            return 0
        good_lines: list[bytes] = []
        for chunk in raw.split(b"\n"):
            if not chunk.strip():
                continue
            try:
                json.loads(chunk)
            except json.JSONDecodeError:
                break  # first bad/partial line ends the valid prefix
            good_lines.append(chunk)
        repaired = b"".join(line + b"\n" for line in good_lines)
        if repaired == raw:
            return 0
        self.atomic_write(p, repaired)
        return len(raw) - len(repaired)

    def project_run_snapshot(self, run_id: str) -> tuple[RunProjection, dict[str, Any]]:
        """Project lifecycle state from the Journal without writing a second truth."""
        events = self.read_events(run_id)
        projection = project_run(events)
        lifecycle = _project_lifecycle_metadata(events, projection.status)
        lifecycle.update(
            {
                "status": projection.status,
                "projected_at_seq": projection.projected_at_seq,
            }
        )
        return projection, lifecycle

    # -- Logs (deep operations) --

    def begin_task_log_attempt(
        self,
        run_id: str,
        task_id: str,
        queue_seq: int,
    ) -> None:
        """Bind the fixed task log names to one Journal execution attempt.

        The queue event sequence is the attempt identity. Completed live logs
        move under ``logs/attempts`` before the next process starts. Existing
        mixed logs without a marker are archived as ``legacy-through-*`` so we
        preserve them without claiming a false per-attempt boundary.
        """
        if queue_seq < 1:
            raise ValueError("Task log attempt requires a positive queue sequence")
        task_dir = self.resolve(run_id, "logs", "tasks")
        task_dir.mkdir(parents=True, exist_ok=True)
        marker_path = task_dir / f"{task_id}.attempt.json"
        marker = self.read_json(marker_path) or {}
        current_queue_seq = marker.get("queue_seq")
        if current_queue_seq == queue_seq:
            return

        current_paths = [
            task_dir / f"{task_id}.stdout.log",
            task_dir / f"{task_id}.stderr.log",
        ]
        if any(path.exists() for path in current_paths):
            if isinstance(current_queue_seq, int) and current_queue_seq > 0:
                archive_name = f"q{current_queue_seq}"
            else:
                ranges = self.project_run_snapshot(run_id)[0].ranges
                through_seq = ranges[-1].queue_seq if ranges else queue_seq
                archive_name = f"legacy-through-q{through_seq}"
            archive_dir = self.resolve(run_id, "logs", "attempts", archive_name)
            archive_dir.mkdir(parents=True, exist_ok=True)
            for path in current_paths:
                if not path.exists():
                    continue
                destination = archive_dir / path.name
                destination.unlink(missing_ok=True)
                path.replace(destination)

        self.atomic_write_json(
            marker_path,
            {
                "schema_version": 1,
                "queue_seq": queue_seq,
            },
        )

    def append_runtime_record(
        self,
        run_id: str,
        level: str,
        message: str,
        task_id: str | None = None,
        max_mb: int = 50,
    ) -> None:
        """Append a structured diagnostic record. Handles rotation automatically."""
        p = self._rotating_path(run_id, "logs", "runtime.jsonl", max_mb)
        rec = json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "message": message,
                "task_id": task_id,
            },
            ensure_ascii=False,
            default=str,
        )
        with open(p, "a", encoding="utf-8") as f:
            f.write(rec + "\n")
            f.flush()
            os.fsync(f.fileno())

    def append_task_output(
        self, run_id: str, task_id: str, stream: str, text: str, max_kb: int = 1024
    ) -> None:
        """Append task stdout/stderr. Size-bounded; rotates past the cap."""
        task_dir = self.resolve(run_id, "logs", "tasks")
        task_dir.mkdir(parents=True, exist_ok=True)
        p = task_dir / f"{task_id}.{stream}.log"
        if p.exists() and p.stat().st_size > max_kb * 1024:
            backup = task_dir / f"{task_id}.{stream}.1.log"
            backup.unlink(missing_ok=True)
            p.rename(backup)
        with open(p, "a", encoding="utf-8") as f:
            f.write(text)
            f.flush()

    def _rotating_path(self, run_id: str, subdir: str, name: str, max_mb: int) -> Path:
        d = self.resolve(run_id, subdir)
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        if p.exists() and p.stat().st_size > max_mb * 1024 * 1024:
            backup = d / (name + ".1")
            backup.unlink(missing_ok=True)
            p.rename(backup)
        return p

    # -- Cancel signal --

    def cancel_path(self, run_id: str) -> Path:
        return self.resolve(run_id, ".runtime", "cancelled")

    def mark_cancelled(self, run_id: str, queue_seq: int | None = None) -> None:
        """Write the cancel flag, naming the execution it targets.

        The flag outlives the execution it stops (the worker never sees the
        cancel API), so it must carry its target: without the queue seq, a
        cancel aimed at one execution would silently self-cancel every later
        execution queued behind it.
        """
        payload = "" if queue_seq is None else json.dumps({"queue_seq": int(queue_seq)})
        self.atomic_write(self.cancel_path(run_id), payload)

    def cancelled_queue_seq(self, run_id: str) -> int | None:
        """The queue_seq the cancel flag targets, or None when blank/legacy."""
        try:
            raw = self.cancel_path(run_id).read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except ValueError:
            return None
        if isinstance(value, dict) and isinstance(value.get("queue_seq"), int):
            return value["queue_seq"]
        return None

    def clear_cancelled(self, run_id: str) -> None:
        self.cancel_path(run_id).unlink(missing_ok=True)

    def check_cancelled(self, run_id: str) -> bool:
        return self.cancel_path(run_id).exists()

    # -- Temp --

    @contextmanager
    def temp_dir(self, scope: str, purpose: str) -> Iterator[Path]:
        d = self.cache / "tmp" / scope
        d.mkdir(parents=True, exist_ok=True)
        td = tempfile.mkdtemp(prefix=f"{purpose}-", dir=str(d))
        try:
            yield Path(td)
        finally:
            # A dry-run root holds the engine state alias; remove_tree unlinks
            # reparse points before deleting so linked targets are never touched.
            self.remove_tree(Path(td), ignore_errors=True)

    # -- Blob store --

    # A CAS blob is immutable by contract; the read-only flag makes the inode
    # itself refuse an in-place write, so every hardlink (each Run's inputs)
    # fails loudly at write time instead of corrupting the shared bytes.
    _READONLY_MODE = stat.S_IREAD if os.name == "nt" else 0o444
    _WRITABLE_MODE = stat.S_IWRITE if os.name == "nt" else 0o666
    _STAGING_DIRNAME = ".staging"

    def blob_put(self, data: bytes) -> str:
        h = hashlib.sha256(data).hexdigest()
        dest = self.data / "store" / h[:2] / h
        if dest.exists():
            return h
        dest.parent.mkdir(parents=True, exist_ok=True)
        incoming = self.data / "store" / ".incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(incoming), prefix="blob-")
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(tmp, self._READONLY_MODE)
        os.replace(tmp, dest)
        return h

    def blob_put_stream(
        self, source, expected_digest: str, chunk_size: int = 8 * 1024 * 1024
    ) -> tuple[str, int]:
        """Stream an uploaded file into CAS with one pass and bounded memory."""
        incoming = self.data / "store" / ".incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(incoming), prefix="upload-")
        digest = hashlib.sha256()
        size = 0
        try:
            with os.fdopen(fd, "wb") as target:
                while chunk := source.read(chunk_size):
                    digest.update(chunk)
                    size += len(chunk)
                    target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            actual = digest.hexdigest()
            if actual != expected_digest:
                raise ValueError(f"digest mismatch: {actual}")
            dest = self.data / "store" / actual[:2] / actual
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                os.unlink(tmp)
            else:
                os.chmod(tmp, self._READONLY_MODE)
                os.replace(tmp, dest)
            return actual, size
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def blob_get(self, hash_hex: str) -> bytes:
        return (self.data / "store" / hash_hex[:2] / hash_hex).read_bytes()

    def blob_exists(self, hash_hex: str) -> bool:
        return (self.data / "store" / hash_hex[:2] / hash_hex).exists()

    def materialize_run_files(self, run_id: str, entries: list[Any]) -> None:
        """Materialize a frozen client tree into the isolated run directory."""
        run_dir = self.allocate_run(run_id).resolve()
        self.materialize_snapshot_files(run_dir, entries, fetch=self._require_blob)

    def _require_blob(self, path: str, digest: str) -> bytes:
        if not self.blob_exists(digest):
            raise FileNotFoundError(f"missing blob for {path}: {digest}")
        return self.blob_get(digest)

    def materialize_snapshot_files(
        self, target_dir: Path, entries: list[Any], *, fetch
    ) -> None:
        """Materialize a frozen client snapshot into an arbitrary root.

        The one materialization path behind both the worker's run directory
        and a dry-run's temporary root: one escape check, one write primitive.
        Entries whose digest already sits in the CAS are hardlinked from the
        immutable blob; ``fetch(path, digest)`` supplies bytes for the rest
        and owns their client-side validation (dry-run inline blobs).
        """
        target_dir = Path(target_dir).resolve()
        for entry in entries:
            path = entry.path if hasattr(entry, "path") else entry["path"]
            digest = (
                entry.blob_hash if hasattr(entry, "blob_hash") else entry["blob_hash"]
            )
            target = (target_dir / path).resolve(strict=False)
            try:
                target.relative_to(target_dir)
            except ValueError as exc:
                raise ValueError(f"run file escapes snapshot: {path}") from exc
            if self.blob_exists(digest):
                # Re-materialization: the target may already BE the right
                # read-only blob link (rerun) or a stale one (revision change).
                # Windows replace needs write access to the replaced inode.
                blob = self.blob_path(digest)
                if target.exists():
                    try:
                        if os.path.samefile(target, blob):
                            continue
                    except OSError:
                        pass
                    self._make_writable_for_replace(target)
                self._link_blob(digest, target)
            else:
                self.atomic_write(target, fetch(path, digest))

    @staticmethod
    def _make_writable_for_replace(path: Path) -> None:
        """Clear a read-only flag that would block os.replace/os.unlink.

        Hardlinks share the inode, so this also flips the CAS blob the link
        points at; callers that know the superseded digest reseal it, and the
        GC store walk reseals whatever is left.
        """
        try:
            if not path.lstat().st_mode & 0o222:
                os.chmod(path, StorageLayout._WRITABLE_MODE)
        except OSError:
            pass

    def _local_sources(
        self, workspace_root: Path, entries: list[Any], *, user_id: str
    ) -> list[tuple[str, Path, str, bool]]:
        """Resolve every frozen local entry to its approved, digest-matching source.

        Read-only: containment, existence and digest only. Submission's check and
        execution's materialization both go through here, so the two can never
        disagree about which bytes a Run is defined over.

        `workspace_root` is validated against the Backend approved roots for
        `user_id` (src.execution_runtime.workspace_containment), never trusted
        merely because a request named it -- docs/STATUS.md "Workspace root
        registration". `user_id` is keyword-only and required. Until Backend
        startup wires a real checker in via set_approved_roots_checker, no root
        is approved for anyone and every call here raises WORKSPACE_PATH_ESCAPE
        (fail-closed default).
        """
        from src.execution_runtime.workspace_containment import (
            validate_root_containment,
        )

        workspace_root = validate_root_containment(Path(workspace_root), user_id)
        resolved: list[tuple[str, Path, str, bool]] = []
        for entry in entries:
            rel = entry.path if hasattr(entry, "path") else entry["path"]
            expected = (
                entry.blob_hash if hasattr(entry, "blob_hash") else entry["blob_hash"]
            )
            source = (workspace_root / rel).resolve(strict=True)
            try:
                source.relative_to(workspace_root)
            except ValueError as exc:
                raise ValueError(f"local source escapes workspace: {rel}") from exc
            if self.file_digest(source) != expected:
                raise ValueError(f"local source digest changed: {rel}")
            is_control = (
                rel == "Snakefile"
                or rel.endswith(".smk")
                or rel == "config.yaml"
                or rel.startswith("scripts/")
            )
            resolved.append((rel, source, expected, is_control))
        return resolved

    def verify_local_run_files(
        self, workspace_root: Path, entries: list[Any], *, user_id: str
    ) -> None:
        """Submission-time check that the frozen mapping still matches its sources.

        Writes nothing into the Run directory: a submission only verifies the
        Workspace source. New API submissions seal the bytes into CAS in the
        adjacent `seal_local_run_files` step.
        """
        self._local_sources(workspace_root, entries, user_id=user_id)

    def seal_local_run_files(
        self, workspace_root: Path, entries: list[Any], *, user_id: str
    ) -> None:
        """Seal a verified local input mapping into CAS without touching the Run.

        The definition must remain executable if the Workspace changes or is
        temporarily unavailable before the global queue reaches it. The CAS is
        shared by all revisions and Runs, so this is one copy per unique digest,
        not an isolated input tree per revision.
        """
        for _rel, source, expected, _is_control in self._local_sources(
            workspace_root, entries, user_id=user_id
        ):
            if not self.blob_exists(expected):
                with source.open("rb") as stream:
                    self.blob_put_stream(stream, expected)
            # Sealed here, referenced only when the submission commits: the
            # digest is in flight, and its marker holds off a GC that would
            # otherwise judge it by age alone.
            self.touch_staging_marker(expected)

    def materialize_local_run_files(
        self,
        target_dir: Path,
        workspace_root: Path,
        entries: list[Any],
        *,
        user_id: str,
    ) -> None:
        """Expose frozen local inputs in `target_dir` WITHOUT copying them.

        One implementation for both the real run directory and a dry-run's
        temporary root. Control files (Snakefile, *.smk, config.yaml, scripts/)
        are written as real files: the engine reads them and they are tiny.
        Every other input is first sealed in the Backend CAS (one copy per
        digest), then hardlinked from that immutable blob. A Run therefore stores
        no private input bytes and cannot follow an in-place Workspace edit.
        """
        target_dir = Path(target_dir).resolve()
        previous = self.read_json(target_dir / ".tdease" / "local-inputs.json") or []
        previous_paths = {
            item.get("path")
            for item in previous
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        shared: list[dict[str, Any]] = []
        for rel, source, expected, is_control in self._local_sources(
            workspace_root, entries, user_id=user_id
        ):
            target = (target_dir / rel).resolve(strict=False)
            target.relative_to(target_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            if is_control:
                self.atomic_write(target, source.read_bytes())
                continue
            if target.exists():
                if target.is_dir():
                    raise ValueError(
                        f"input target {rel} is a directory in the shared Run tree; "
                        "refusing to remove a workflow-owned path"
                    )
                if rel not in previous_paths:
                    try:
                        if os.path.samefile(source, target):
                            shared.append(
                                {
                                    "path": rel,
                                    "sha256": expected,
                                    "source": str(source),
                                    "strategy": "hardlink",
                                }
                            )
                            continue
                    except OSError:
                        pass
                    raise ValueError(
                        f"input target {rel} already belongs to the shared Run tree; "
                        "refusing to overwrite an unmanaged intermediate or output"
                    )
            try:
                # Seal the source once globally, then point the Run at the
                # immutable blob. The digest check in blob_put_stream also
                # catches a source that changes while it is being read.
                if not self.blob_exists(expected):
                    with source.open("rb") as stream:
                        self.blob_put_stream(stream, expected)
                blob = self.blob_path(expected)
                superseded = None
                if target.exists():
                    # Rerun over the shared tree: the previous hardlink is a
                    # read-only CAS inode. Same bytes -> the link already IS
                    # the right blob; new bytes -> clear the flag (Windows
                    # replace needs write access) and reseal the superseded
                    # blob once the link no longer names it.
                    try:
                        if os.path.samefile(target, blob):
                            shared.append(
                                {
                                    "path": rel,
                                    "sha256": expected,
                                    "source": str(source),
                                    "strategy": "cas_hardlink",
                                }
                            )
                            continue
                    except OSError:
                        pass
                    superseded = next(
                        (
                            item.get("sha256")
                            for item in previous
                            if isinstance(item, dict) and item.get("path") == rel
                        ),
                        None,
                    )
                    self._make_writable_for_replace(target)
                self._link_blob(expected, target)
                if (
                    superseded
                    and superseded != expected
                    and self.blob_exists(superseded)
                ):
                    self._seal_file_if_writable(self.blob_path(superseded))
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"input {rel} cannot be sealed into the Backend CAS "
                    f"({getattr(exc, 'strerror', None) or exc})"
                ) from exc
            shared.append(
                {
                    "path": rel,
                    "sha256": expected,
                    "source": str(source),
                    "strategy": "cas_hardlink",
                }
            )
        self.atomic_write_json(target_dir / ".tdease" / "local-inputs.json", shared)

    def _link_blob(self, digest: str, target: Path) -> None:
        """Atomically expose one immutable CAS blob at a Run-relative path."""
        source = self.blob_path(digest)
        if not source.is_file():
            raise FileNotFoundError(f"missing blob for {digest}")
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.blob-{uuid.uuid4().hex}")
        try:
            os.link(source, temporary)
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def verify_local_inputs(self, run_id: str) -> None:
        manifest = (
            self.read_json(self.resolve(run_id, ".tdease", "local-inputs.json")) or []
        )
        for item in manifest:
            path = self.resolve(run_id, item["path"])
            if not path.is_file() or self.file_digest(path) != item["sha256"]:
                raise ValueError(
                    f"local shared input changed: {item['path']} -- the workspace "
                    "file was edited or deleted while the execution used it. Restore "
                    "the original bytes, or submit a new revision to freeze the "
                    "current file content."
                )

    def execution_output_files(self, run_id: str) -> list[str]:
        """Run-relative paths the engine recorded as its last execution's products.

        The engine writes ``.tdease/execution-outputs.json`` from its own DAG
        at the end of a successful execute-mode run; it is the only authority
        on what an execution actually produced. Returns [] when the record is
        absent (dry-run, never executed, or a run from before the record
        existed) -- callers must NOT fall back to scanning the run directory:
        a narrowed publish surface is correct, guessed products are not.
        """
        record = self.read_json(
            self.resolve(run_id, ".tdease", "execution-outputs.json")
        )
        raw = record.get("outputs") if isinstance(record, dict) else None
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        outputs: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                continue
            normalized = _normalize_run_relative_path(item)
            if normalized and normalized not in seen:
                seen.add(normalized)
                outputs.append(normalized)
        return outputs

    def write_results_manifest(self, run_id: str, definition_revision_id: str) -> Path:
        """Publish the result manifest: content-addressed claims of this Run's products.

        The publish set is attribution, never discovery: (1) `result_specs`
        outputs that materialized, (2) the engine-recorded products of the
        execution that just ran, (3) previously claimed manifest entries whose
        path this execution did not overwrite -- kept verbatim (same digest)
        so a dead rule's output stays published across revisions. Nothing is
        parsed out of the Snakefile text and nothing is swept off the shared
        run tree; when the execution record is missing the surface narrows and
        `provenance_source` records the gap.
        """
        run_root = self.resolve(run_id)
        # A newer definition may have been submitted while this execution was
        # running. Result provenance must use the definition that actually ran,
        # not the mutable pointer in run.json.
        run_data = self.read_definition_snapshot(run_id, definition_revision_id)
        if run_data is None:
            run_data = self.read_json(self.resolve(run_id, "run.json")) or {}
        target = self.resolve(run_id, "results.manifest.json")
        previous_manifest = self.read_json(target)
        if not isinstance(previous_manifest, dict):
            # rerun clears the live manifest before re-executing; the newest
            # retained revision is the continuity anchor that keeps already-
            # claimed entries (and their digests) alive across the rerun.
            retained = self.revision_manifests(run_id)
            previous_manifest = retained[0] if retained else {}
        previously_claimed_files = _claimed_entries(
            previous_manifest.get("files")
        )
        previously_claimed_workflow = _claimed_entries(
            previous_manifest.get("workflow_files")
        )
        record_present = (
            self.resolve(run_id, ".tdease", "execution-outputs.json").is_file()
        )

        entries: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(path: Path) -> None:
            if not path.is_file():
                return
            try:
                rel = (
                    path.resolve(strict=False)
                    .relative_to(run_root.resolve())
                    .as_posix()
                )
            except ValueError:
                return
            if rel in seen:
                return
            seen.add(rel)
            digest = self.file_digest(path)
            with path.open("rb") as source:
                self.blob_put_stream(source, digest)
            entries.append({"path": rel, "size": path.stat().st_size, "sha256": digest})

        explicit_specs = [
            _normalize_run_relative_path(spec.get("output"))
            for spec in (run_data.get("result_specs") or [])
            if isinstance(spec, dict) and isinstance(spec.get("output"), str)
        ]
        for rel in explicit_specs:
            if rel is None:
                continue
            try:
                add(self.resolve(run_id, rel))
            except ValueError:
                continue  # a declared path that will not resolve is simply not listed
        for rel in self.execution_output_files(run_id):
            try:
                add(self.resolve(run_id, rel))
            except ValueError:
                continue

        workflow_entries: list[dict[str, Any]] = []
        workflow_seen: set[str] = set()
        for item in run_data.get("workspace_files") or []:
            rel = item.get("path") if isinstance(item, dict) else None
            if not isinstance(rel, str) or not self._is_workflow_source(rel):
                continue
            source = self.resolve(run_id, rel)
            if not source.is_file() or rel in workflow_seen:
                continue
            workflow_seen.add(rel)
            digest = self.file_digest(source)
            with source.open("rb") as stream:
                self.blob_put_stream(stream, digest)
            workflow_entries.append(
                {"path": rel, "size": source.stat().st_size, "sha256": digest}
            )

        # Fixed retention: entries an earlier manifest already claimed keep
        # their exact digest unless this execution overwrote the same path --
        # a dead rule's output (or a dropped control file) stays published.
        # Lists stay separate and a path is claimed once, in whichever list
        # this execution's fresh evidence put it.
        claimed_paths = seen | {entry["path"] for entry in workflow_entries}
        for entry in previously_claimed_files:
            rel = _normalize_run_relative_path(entry["path"])
            if rel is None or rel in claimed_paths:
                continue
            claimed_paths.add(rel)
            entries.append(entry)
        for entry in previously_claimed_workflow:
            rel = _normalize_run_relative_path(entry["path"])
            if rel is None or rel in claimed_paths:
                continue
            claimed_paths.add(rel)
            workflow_entries.append(entry)

        entries.sort(key=lambda entry: entry["path"])
        journal_seq = self.recover_seq(run_id)
        revision_id = f"rev-{journal_seq:08d}"
        manifest = {
            "schema_version": 2,
            "run_id": run_id,
            "revision_id": revision_id,
            "definition_revision_id": definition_revision_id,
            "journal_seq": journal_seq,
            "parent_revision_id": previous_manifest.get("revision_id"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "provenance_source": (
                "engine_execution" if record_present else "execution_record_missing"
            ),
            "files": entries,
            "workflow_files": sorted(workflow_entries, key=lambda entry: entry["path"]),
        }
        self.atomic_write_json(
            self.resolve(run_id, "revisions", f"{revision_id}.json"), manifest
        )
        self.atomic_write_json(target, manifest)
        return target

    @staticmethod
    def _is_workflow_source(path: str) -> bool:
        normalized = path.replace("\\", "/")
        return (
            normalized in {"Snakefile", "config.yaml"}
            or normalized.endswith(".smk")
            or normalized.startswith("scripts/")
        )

    def revision_manifests(self, run_id: str) -> list[dict[str, Any]]:
        revision_dir = self.resolve(run_id, "revisions")
        if not revision_dir.is_dir():
            return []
        manifests = [self.read_json(path) for path in revision_dir.glob("rev-*.json")]
        return sorted(
            (manifest for manifest in manifests if isinstance(manifest, dict)),
            key=lambda manifest: str(manifest.get("revision_id", "")),
            reverse=True,
        )

    def revision_manifest(
        self, run_id: str, revision_id: str
    ) -> Optional[dict[str, Any]]:
        if not __import__("re").fullmatch(r"rev-[0-9]{8,}", revision_id):
            return None
        return self.read_json(self.resolve(run_id, "revisions", f"{revision_id}.json"))

    def write_definition_snapshot(
        self, run_id: str, definition: dict[str, Any]
    ) -> Path:
        """Persist one small immutable definition without copying run outputs."""
        revision_id = str(definition.get("definition_revision_id", ""))
        if not __import__("re").fullmatch(r"def-[a-f0-9]{24}", revision_id):
            raise ValueError(f"invalid definition revision id: {revision_id!r}")
        target = self.resolve(run_id, "definitions", f"{revision_id}.json")
        self.atomic_write_json(target, definition)
        return target

    def read_definition_snapshot(
        self, run_id: str, revision_id: str
    ) -> Optional[dict[str, Any]]:
        if not __import__("re").fullmatch(r"def-[a-f0-9]{24}", revision_id):
            return None
        return self.read_json(
            self.resolve(run_id, "definitions", f"{revision_id}.json")
        )

    def definition_snapshots(self, run_id: str) -> list[dict[str, Any]]:
        directory = self.resolve(run_id, "definitions")
        if not directory.is_dir():
            return []
        snapshots = [self.read_json(path) for path in directory.glob("def-*.json")]
        return sorted(
            (item for item in snapshots if isinstance(item, dict)),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )

    def blob_path(self, digest: str) -> Path:
        if not __import__("re").fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("invalid blob digest")
        return self.data / "store" / digest[:2] / digest

    def staging_marker_path(self, digest: str) -> Path:
        if not __import__("re").fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("invalid blob digest")
        return self.data / "store" / self._STAGING_DIRNAME / digest

    def touch_staging_marker(self, digest: str) -> None:
        """Mark a digest as in flight: an upload (or a local-input seal) that
        finished but is not yet referenced by any definition. GC must not race
        it -- the blob's age says nothing about whether its submission already
        committed."""
        marker = self.staging_marker_path(digest)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch(exist_ok=True)

    def referenced_blob_digests(self) -> set[str]:
        """Return blobs reachable from active or recoverable Run records.

        Definitions retain input blobs; execution manifests retain published
        result/workflow blobs. The filesystem is the durable source here, so
        this remains correct after SQLite/index loss or a Backend restart.
        """
        digests: set[str] = set()
        run_roots = [self.data / "runs", self.trash / "runs"]
        for runs_root in run_roots:
            if not runs_root.is_dir():
                continue
            for run_dir in runs_root.iterdir():
                if not run_dir.is_dir():
                    continue
                candidates = [
                    *run_dir.glob("definitions/def-*.json"),
                    *run_dir.glob("revisions/rev-*.json"),
                    run_dir / "results.manifest.json",
                ]
                for path in candidates:
                    document = self.read_json(path)
                    if not isinstance(document, dict):
                        continue
                    raw_entries = [
                        *(document.get("workspace_files") or []),
                        *(document.get("files") or []),
                        *(document.get("workflow_files") or []),
                    ]
                    for entry in raw_entries:
                        if not isinstance(entry, dict):
                            continue
                        for field in ("blob_hash", "sha256"):
                            value = entry.get(field)
                            if isinstance(value, str) and __import__("re").fullmatch(
                                r"[a-f0-9]{64}", value
                            ):
                                digests.add(value)
        return digests

    def gc_unreferenced_blobs(
        self, *, min_age_seconds: float = 300.0, staging_ttl_seconds: float | None = None
    ) -> list[str]:
        """Delete old CAS blobs unreachable from active/trash Run records.

        A digest whose staging marker is younger than the staging TTL is exempt:
        an upload that finished but has not yet been attached to its definition
        is in flight, not garbage -- the age grace alone cannot protect a
        multi-file upload. Orphan markers (no blob, or older than the TTL) are
        dropped in the same pass. The walk also seals legacy writable blobs:
        read-only CAS is the invariant, and pre-sealing blobs get the flag here,
        idempotently, amortized over the walk.
        """
        ttl = (
            staging_ttl_seconds
            if staging_ttl_seconds is not None
            else _default_staging_ttl_seconds()
        )
        reachable = self.referenced_blob_digests()
        protected = self._sweep_staging_markers(ttl)
        now = time.time()
        removed: list[str] = []
        store = self.data / "store"
        if not store.is_dir():
            return removed
        for shard in store.iterdir():
            if not shard.is_dir() or shard.name in {
                ".incoming",
                self._STAGING_DIRNAME,
            }:
                continue
            for blob in shard.iterdir():
                if not blob.is_file() or not __import__("re").fullmatch(
                    r"[a-f0-9]{64}", blob.name
                ):
                    continue
                if self._seal_file_if_writable(blob):
                    logger.info("Legacy CAS blob sealed read-only: %s", blob.name)
                if blob.name in reachable or blob.name in protected:
                    continue
                try:
                    if now - blob.stat().st_mtime < min_age_seconds:
                        continue
                    self._unlink_readonly(blob)
                    removed.append(blob.name)
                except OSError:
                    logger.warning("CAS blob could not be collected: %s", blob)
        return removed

    def _sweep_staging_markers(self, ttl: float) -> set[str]:
        """Drop orphan staging markers; return the still-fresh digest set."""
        staging = self.data / "store" / self._STAGING_DIRNAME
        fresh: set[str] = set()
        if not staging.is_dir():
            return fresh
        now = time.time()
        for marker in staging.iterdir():
            if not marker.is_file():
                continue
            if not __import__("re").fullmatch(r"[a-f0-9]{64}", marker.name):
                marker.unlink(missing_ok=True)  # garbage, not a digest marker
                continue
            try:
                age = now - marker.stat().st_mtime
            except OSError:
                continue
            if not self.blob_exists(marker.name) or age >= ttl:
                marker.unlink(missing_ok=True)
                continue
            fresh.add(marker.name)
        return fresh

    def _seal_file_if_writable(self, path: Path) -> bool:
        """Set the read-only flag unless it is already set. Returns what happened."""
        try:
            if not path.lstat().st_mode & 0o222:
                return False
            os.chmod(path, self._READONLY_MODE)
            return True
        except OSError:
            logger.warning("CAS blob could not be sealed: %s", path)
            return False

    def _unlink_readonly(self, path: Path) -> None:
        # Windows refuses to unlink a read-only inode; the flag protects the
        # CAS against writes, not against its own garbage collection.
        if not path.lstat().st_mode & 0o222:
            os.chmod(path, self._WRITABLE_MODE)
        path.unlink()

    def kill_engine_tree(self, run_id: str) -> None:
        """Kill the recorded engine AND its tool children.

        A bare terminate() on the engine pid leaves Snakemake's job children
        (topfd/toppic/...) running unsupervised: they keep file handles open
        inside the run dir and burn CPU after the projection says terminal.
        The engine is started in its own session/process group precisely so
        the whole tree can be taken down in one shot.

        Called by reconcile only after the execution lease is dead: a live
        lease owner owns this engine's outcome through finalization.
        """
        process = self.read_json(self.resolve(run_id, ".runtime", "process.json")) or {}
        engine_pid = process.get("engine_pid")
        if not engine_pid:
            return
        created = process.get("engine_create_time")
        if created and not process_identity_alive(f"{engine_pid}:{created}"):
            return  # the pid was recycled: this is not our engine
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(int(engine_pid)), "/T", "/F"],
                    capture_output=True,
                    timeout=5,
                )
            else:
                try:
                    os.killpg(os.getpgid(int(engine_pid)), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
        except Exception:
            logger.exception(
                "Engine tree kill failed for run %s (pid %s)", run_id, engine_pid
            )

    # -- Trash --

    def trash_run(self, run_id: str, metadata: dict[str, Any]) -> Path:
        """Move one terminal Run to recoverable trash without adding a status."""
        self._validate_run_id(run_id)
        source = self.data / "runs" / run_id
        destination = self.trash / "runs" / run_id
        if not source.is_dir():
            raise FileNotFoundError(run_id)
        if destination.exists():
            raise FileExistsError(f"trashed Run already exists: {run_id}")
        self.atomic_write_json(source / ".tdease" / "trash.json", metadata)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return destination

    def restore_run(self, run_id: str) -> Path:
        """Restore one trashed Run to the active runs directory."""
        self._validate_run_id(run_id)
        source = self.trash / "runs" / run_id
        destination = self.data / "runs" / run_id
        if not source.is_dir():
            raise FileNotFoundError(run_id)
        if destination.exists():
            raise FileExistsError(f"active Run already exists: {run_id}")
        shutil.move(str(source), str(destination))
        (destination / ".tdease" / "trash.json").unlink(missing_ok=True)
        return destination

    def purge_trashed_run(self, run_id: str) -> None:
        """Permanently remove one validated Run from recoverable trash."""
        self._validate_run_id(run_id)
        target = self.trash / "runs" / run_id
        if not target.is_dir():
            raise FileNotFoundError(run_id)
        self.remove_tree(target)
        # Purge is the explicit ownership boundary: only now may bytes that
        # were reachable solely from this Run become collectible. Keep a short
        # grace period for concurrent upload/submission races.
        self.gc_unreferenced_blobs()

    def trashed_run_dirs(self) -> list[Path]:
        root = self.trash / "runs"
        if not root.is_dir():
            return []
        return sorted(
            (path for path in root.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        )


# -- Module singleton --

_storage: Optional[StorageLayout] = None


def get_storage() -> StorageLayout:
    """Return the runtime root frozen from the Backend JSON configuration."""
    global _storage
    if _storage is None:
        _storage = StorageLayout(_resolve_backend_root())
    return _storage


def _resolve_backend_root() -> Path:
    from src.backend_settings import BACKEND_SETTINGS

    return BACKEND_SETTINGS.data_root


def _default_staging_ttl_seconds() -> float:
    from src.backend_settings import BACKEND_SETTINGS

    return float(BACKEND_SETTINGS.staging_ttl_seconds)


def get_tools_root() -> Path:
    """Compute tools root directory (topfd/toppic/msconvert etc local executables).

    Node packages are part of the resolved Backend deployment and live under its
    data root's ``nodes/`` directory. There is one path calculation for execution
    and enumeration; no separate tools-root deployment variable is required.
    """
    from src.backend_settings import BACKEND_SETTINGS

    return BACKEND_SETTINGS.node_root


def set_storage(s: StorageLayout) -> None:
    global _storage
    _storage = s
