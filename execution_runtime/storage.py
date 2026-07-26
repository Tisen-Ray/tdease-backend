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
- run.json "status" field is a projection, derived from events.jsonl by
  src.execution_runtime.run_projector.project_run through
  sync_run_projection -- the only place this module writes that field.
  Nothing else may write "status" independently; run_worker.py and
  reconcile_orphaned_runs below both go through it now.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional

from src.execution_runtime.run_projector import RunProjection, project_run

RUN_ID_PATTERN = __import__("re").compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


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
            "results", "logs", "logs/tasks", "config",
            ".runtime", ".runtime/task-records",
            ".runtime/incomplete", ".runtime/locks",
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
        if not resolved.startswith(base_str) and resolved != os.path.normpath(str(base)):
            raise ValueError(f"Path escapes run dir: {segments}")
        return p

    def run_exists(self, run_id: str) -> bool:
        return (self.data / "runs" / run_id).is_dir()

    # -- Atomic write --

    def atomic_write(self, target: Path, content: str | bytes) -> None:
        """
        Atomically write a canonical file.

        Same-directory temp file -> fsync -> os.replace -> fsync parent -> cleanup.
        """
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        encoding = "utf-8" if isinstance(content, str) else None
        fd, tmp = tempfile.mkstemp(
            dir=str(target.parent),
            prefix="." + target.name + ".",
        )
        try:
            if encoding:
                os.write(fd, content.encode(encoding))
            else:
                os.write(fd, content)
            os.fsync(fd)
        except Exception:
            os.close(fd)
            try: os.unlink(tmp)
            except OSError: pass
            raise
        os.close(fd)
        try:
            os.replace(tmp, target)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise
        # Fsync parent directory for durability (Unix only -- Windows rejects dir fsync)
        if os.name != "nt":
            dfd = os.open(str(target.parent), os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)

    def atomic_write_json(self, target: Path, obj: dict | list) -> None:
        self.atomic_write(target, json.dumps(obj, indent=2, ensure_ascii=False, default=str))

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
        """Atomically claim one queued run; claim storage is runtime-owned."""
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

    # -- Events (JSONL append, single-writer) --

    def events_path(self, run_id: str) -> Path:
        return self.resolve(run_id, "events.jsonl")

    def recover_seq(self, run_id: str) -> int:
        """Return the highest persisted seq in events.jsonl. 0 = empty."""
        p = self.events_path(run_id)
        if not p.exists():
            return 0
        last = 0
        for line in p.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            try:
                evt = json.loads(line)
                s = evt.get("seq", 0)
                if s > last:
                    last = s
            except json.JSONDecodeError:
                continue
        return last

    def append_event(self, run_id: str, event: dict[str, Any]) -> int:
        """
        Append one event line. Allocates and returns the monotonic seq.
        Starts from recover_seq + 1; callers should not set seq manually.
        """
        current = self.recover_seq(run_id)
        event["seq"] = current + 1
        line = json.dumps(event, ensure_ascii=False, default=str) + "\n"
        p = self.events_path(run_id)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
        return event["seq"]

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

    def sync_run_projection(self, run_id: str, *, claim_held: bool = True) -> RunProjection:
        """Recompute run.json "status" from events.jsonl.

        The only place run.json "status" field is written
        (CORE-ARCHITECTURE.md Sec 1.4): a pure projection of the event log,
        never an independent write. Callers (run_worker.py,
        reconcile_orphaned_runs) call this after appending or observing
        events instead of computing/writing a status themselves. Preserves
        every other field already in run.json (commit data, pid
        bookkeeping); only "status" and "projected_at_seq" are touched, and
        "status" is left alone when there are no events yet (nothing to
        project -- run.json may still hold its just-created QUEUED write).

        `claim_held` (default True, matching every existing caller except
        one) distinguishes a resync driven by a Run whose claim this
        process actually found held -- run_worker.execute_run's own call
        (its claim is held for the Run's entire execution), and
        reconcile_orphaned_runs whenever it found the claim still held
        before releasing it -- from a resync of a Run that was never
        claimed at all since its most recent (re)queue.

        Only in that unclaimed case can run.json's own QUEUED write (made
        directly by create_run/rerun_run, still the only other status
        writer per the invariant above) be more current than what the
        event log alone can justify: REMAINING-DESIGNS.md Sec 1 requires
        reopening execution to be represented by a fresh run.started,
        which by design (run_projector.py's rule table; see
        tests/fixtures/run-projection/trailing-queued-after-terminal-does-not-requeue)
        a bare run.queued rerun/audit event never retroactively supplies --
        so projecting the event log alone would silently revert a
        just-requeued, not-yet-picked-up Run back to its previous terminal
        status. Skipping the overwrite here -- only when this Run's claim
        was not held and reconcile_orphaned_runs did not otherwise need to
        intervene for it in this pass -- closes a real gap: a Backend
        restart between "rerun requested" and "the worker dequeues it"
        previously discarded the rerun with no error anywhere (`_dequeue`
        never finding a QUEUED run again, because this function had just
        reverted it back to its prior terminal status).
        """
        events = self.read_events(run_id)
        projection = project_run(events)
        run_json = self.resolve(run_id, "run.json")
        current = self.read_json(run_json) or {"run_id": run_id}
        updated = dict(current)
        pending_requeue_not_yet_claimed = (
            not claim_held
            and current.get("status") == "QUEUED"
            and projection.status not in (None, "QUEUED")
        )
        if projection.status is not None and not pending_requeue_not_yet_claimed:
            updated["status"] = projection.status
        updated["projected_at_seq"] = projection.projected_at_seq
        self.atomic_write_json(run_json, updated)
        return projection

    # -- Logs (deep operations) --

    def append_runtime_record(self, run_id: str, level: str, message: str,
                               task_id: str | None = None, max_mb: int = 50) -> None:
        """Append a structured diagnostic record. Handles rotation automatically."""
        p = self._rotating_path(run_id, "logs", "runtime.jsonl", max_mb)
        rec = json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            "task_id": task_id,
        }, ensure_ascii=False, default=str)
        with open(p, "a", encoding="utf-8") as f:
            f.write(rec + "\n")
            f.flush()
            os.fsync(f.fileno())

    def append_task_output(self, run_id: str, task_id: str, stream: str,
                            text: str, max_kb: int = 1024) -> None:
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

    def mark_cancelled(self, run_id: str) -> None:
        self.atomic_write(self.cancel_path(run_id), "")

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
            shutil.rmtree(td, ignore_errors=True)

    # -- Blob store --

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
        os.replace(tmp, dest)
        return h

    def blob_put_stream(self, source, expected_digest: str,
                        chunk_size: int = 8 * 1024 * 1024) -> tuple[str, int]:
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
        for entry in entries:
            path = entry.path if hasattr(entry, "path") else entry["path"]
            digest = entry.blob_hash if hasattr(entry, "blob_hash") else entry["blob_hash"]
            target = (run_dir / path).resolve(strict=False)
            try:
                target.relative_to(run_dir)
            except ValueError as exc:
                raise ValueError(f"run file escapes snapshot: {path}") from exc
            if not self.blob_exists(digest):
                raise FileNotFoundError(f"missing blob for {path}: {digest}")
            self.atomic_write(target, self.blob_get(digest))

    def materialize_local_run_files(self, run_id: str, workspace_root: Path,
                                    entries: list[Any], *, user_id: str) -> None:
        """Freeze controls and share large local inputs without network/CAS transfer.

        workspace_root is validated against the Backend approved roots for
        `user_id` (src.execution_runtime.workspace_containment), never
        trusted merely because this request named it -- REMAINING-DESIGNS.md
        Sec 1 "Workspace root registration". `user_id` is keyword-only and
        required -- the caller (app/api/runs_v2.py) must pass
        `RunCommit.user_id`, never omit it. Until Backend startup wires a
        real checker in via set_approved_roots_checker, no root is approved
        for anyone and every call here raises WORKSPACE_PATH_ESCAPE
        (fail-closed default).
        """
        from src.execution_runtime.workspace_containment import validate_root_containment

        workspace_root = validate_root_containment(Path(workspace_root), user_id)
        run_dir = self.allocate_run(run_id).resolve()
        shared: list[dict[str, Any]] = []
        for entry in entries:
            rel = entry.path if hasattr(entry, "path") else entry["path"]
            expected = entry.blob_hash if hasattr(entry, "blob_hash") else entry["blob_hash"]
            source = (workspace_root / rel).resolve(strict=True)
            try:
                source.relative_to(workspace_root)
            except ValueError as exc:
                raise ValueError(f"local source escapes workspace: {rel}") from exc
            if self.file_digest(source) != expected:
                raise ValueError(f"local source digest changed: {rel}")
            target = (run_dir / rel).resolve(strict=False)
            target.relative_to(run_dir)
            target.parent.mkdir(parents=True, exist_ok=True)
            is_control = rel == "Snakefile" or rel.endswith(".smk") or rel == "config.yaml" or rel.startswith("scripts/")
            if is_control:
                self.atomic_write(target, source.read_bytes())
            else:
                try:
                    os.link(source, target)
                    strategy = "hardlink"
                except OSError:
                    shutil.copy2(source, target)
                    strategy = "copy"
                shared.append({"path": rel, "sha256": expected, "source": str(source), "strategy": strategy})
        self.atomic_write_json(self.resolve(run_id, ".tdease", "local-inputs.json"), shared)

    def verify_local_inputs(self, run_id: str) -> None:
        manifest = self.read_json(self.resolve(run_id, ".tdease", "local-inputs.json")) or []
        for item in manifest:
            path = self.resolve(run_id, item["path"])
            if not path.is_file() or self.file_digest(path) != item["sha256"]:
                raise ValueError(f"local shared input changed: {item['path']}")

    def declared_output_files(self, run_id: str) -> list[str]:
        """Run-root-relative paths the committed workflow *declared* it would produce.

        Two sources, unioned in order: the commit's `result_specs[].output`
        (explicit Published Results), then the concrete targets of the Snakefile's
        `rule all` input (resolved against the Run's `config`). This is what makes a
        flat-layout template -- whose outputs sit at the run root, not under
        `results/` -- have a non-empty canonical result list, so a SUCCEEDED Run whose
        declared table came back empty still lists that table and is distinguishable
        from a Run that produced nothing (docs/design/EVIDENCE-AND-KNOWLEDGE.md 2.6).

        Best-effort and never raising: an unparseable Snakefile yields the
        result_specs alone (or []), and the caller falls back to the `results/**`
        glob. Traversal segments and absolute paths are dropped.
        """
        data = self.read_json(self.resolve(run_id, "run.json")) or {}
        candidates: list[str] = []
        for spec in (data.get("result_specs") or []):
            if isinstance(spec, dict):
                output = spec.get("output")
                if isinstance(output, str) and output:
                    candidates.append(output)
        snakefile = data.get("snakefile")
        if isinstance(snakefile, str) and snakefile:
            from src.execution_runtime.declared_outputs import rule_all_outputs
            candidates.extend(rule_all_outputs(snakefile, data.get("config")))

        seen: set[str] = set()
        result: list[str] = []
        for rel in candidates:
            normalized = rel.replace("\\", "/").lstrip("/")
            parts = normalized.split("/")
            if not normalized or ".." in parts or (len(parts[0]) == 2 and parts[0][1] == ":"):
                continue
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    def write_results_manifest(self, run_id: str) -> Path:
        run_root = self.resolve(run_id)
        entries: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add(path: Path) -> None:
            if not path.is_file():
                return
            try:
                rel = path.resolve(strict=False).relative_to(run_root.resolve()).as_posix()
            except ValueError:
                return
            if rel in seen:
                return
            seen.add(rel)
            entries.append({"path": rel, "size": path.stat().st_size, "sha256": self.file_digest(path)})

        # Declared outputs first (rule all / result_specs), then nested results/**
        # for templates that use that layout -- so both a flat and a results/-rooted
        # template surface their actual products.
        for rel in self.declared_output_files(run_id):
            try:
                add(self.resolve(run_id, rel))
            except ValueError:
                continue  # a declared path that will not resolve is simply not listed
        for path in self.result_files(run_id):
            add(path)

        entries.sort(key=lambda entry: entry["path"])
        target = self.resolve(run_id, "results.manifest.json")
        self.atomic_write_json(target, {"schema_version": 1, "run_id": run_id, "files": entries})
        return target

    def _engine_pid_alive(self, data: dict[str, Any]) -> bool:
        """Whether the recorded engine_runner child (the actual computation
        process, not the worker/uvicorn process that dequeued it) is still
        alive. Only engine_pid is treated as authoritative evidence of a
        live execution -- pid is the worker own bookkeeping and, being
        just an OS pid number, is too easily a stale/reused value to trust
        for "is this Run still really running"."""
        import psutil
        engine_pid = data.get("engine_pid")
        return bool(engine_pid) and psutil.pid_exists(int(engine_pid))

    def _kill_engine_pid(self, data: dict[str, Any]) -> None:
        import psutil
        engine_pid = data.get("engine_pid")
        if not engine_pid:
            return
        try:
            proc = psutil.Process(int(engine_pid))
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
        except Exception:
            pass  # best-effort; reconciliation proceeds regardless

    def reconcile_orphaned_runs(self) -> list[str]:
        """Recover Runs whose worker died -- driven by events, not by trusting
        run.json own "status" field, and always converging within this one
        pass (CORE-ARCHITECTURE.md Sec 1.4, REMAINING-DESIGNS.md Sec 1
        "Recovery convergence").

        Four things happen for every Run directory, in order:

        1. repair_events_file -- drop any partial trailing line left by a
           crash mid-append, so the projection below reads a clean log and
           future appends do not get glued onto garbage bytes (crash point
           c: mid-append with a partial line).
        2. Unconditional claim release. This loop runs once at startup,
           before any live worker exists, so any ".runtime/claimed" file on
           record belongs to a process that is no longer running -- there is
           no in-progress dequeue for this reconciliation to respect.
           Released regardless of projected status, and *before* branch 3
           below decides whether a status change needs an event. Without
           this, a crash between a Run's projection reaching a terminal
           status and that worker's own release_claim call (crash point b:
           "projection update and process exit") leaves a claim file that
           silently blocks every future Continue/resume dequeue for that
           run_id forever -- no error anywhere, just a Run stuck QUEUED
           after a later rerun because claim_run's O_CREAT|O_EXCL keeps
           failing against a lock nobody still holds.
        3. Orphan handling, driven by the projected status:
           - projection RUNNING with an open execution range whose
             engine_pid is not alive: this range crashed mid-execution.
             Kill any lingering process, then close the range with an
             explicit run.failed event ("orphaned"). The Run converges to
             FAILED and can be retried through Continue.
           - projection QUEUED and a claim was held (released in step 2):
             the worker died before ever appending run.started. Append a
             run.action audit event. The projection was already QUEUED --
             the event log never said otherwise -- so no status flip is
             needed, only the claim release from step 2.
           Both shapes append an event, matching "orphan kill and recovery
           always emit an event" -- a silent run.json rewrite never does.
        4. sync_run_projection -- every Run, orphaned or not, gets
           run.json resynced from its (possibly just-updated) projection.
           This is what closes the crash window between "event appended"
           and "projection updated" (crash point a): a Run whose events
           already carried a terminal fact when this process died, but
           whose run.json never caught up, converges here with no new
           event needed.
        """
        recovered: list[str] = []
        runs = self.data / "runs"
        if not runs.is_dir():
            return recovered
        for directory in sorted(runs.iterdir()):
            if not directory.is_dir():
                continue
            run_id = directory.name
            try:
                self._validate_run_id(run_id)
            except ValueError:
                continue

            self.repair_events_file(run_id)
            projection = project_run(self.read_events(run_id))
            data = self.read_json(directory / "run.json") or {}

            was_claimed = self.is_claimed(run_id)
            if was_claimed:
                self.release_claim(run_id)

            intervened = False
            if projection.status == "RUNNING":
                has_open_range = any(r.is_open for r in projection.ranges)
                if has_open_range and not self._engine_pid_alive(data):
                    self._kill_engine_pid(data)
                    from src.execution_runtime.events import EventEmitter
                    EventEmitter(run_id).run_failed(
                        exit_code=None,
                        run_time_seconds=0.0,
                        error_message="orphaned: worker process not found (backend restarted)",
                    )
                    recovered.append(run_id)
                    intervened = True
            elif projection.status == "QUEUED" and was_claimed:
                from src.execution_runtime.events import EventEmitter
                EventEmitter(run_id).run_action("orphan_reclaimed", "system")
                recovered.append(run_id)
                intervened = True

            # `claim_held` also folds in whether this pass just intervened
            # for this Run (appended an orphan-recovery event above): a Run
            # this reconciliation pass had to act on is never the "cleanly
            # requeued, waiting for its first pickup" case sync_run_projection
            # guards against, regardless of whether a claim survived to be
            # released in step 2.
            self.sync_run_projection(run_id, claim_held=was_claimed or intervened)

        return recovered

    # -- Trash --

    def move_to_trash(self, path: Path) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dest = self.trash / f"{ts}_{path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))

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

    def trashed_run_dirs(self) -> list[Path]:
        root = self.trash / "runs"
        if not root.is_dir():
            return []
        return sorted((path for path in root.iterdir() if path.is_dir()), key=lambda path: path.name)

    # -- Result access --

    def result_files(self, run_id: str) -> list[Path]:
        rd = self.resolve(run_id, "results")
        if not rd.exists():
            return []
        return sorted(rd.rglob("*"))


# -- Module singleton --

_storage: Optional[StorageLayout] = None


def get_storage() -> StorageLayout:
    """The single backend data-root resolution entry point.

    Priority: TDEASE_DATA_ROOT env var > "server-data" literal (manual
    backend-dev fallback only). Desktop app has Electron backend_manager.cjs
    inject <dataRoot>/backend/; tests inject a temp dir via conftest/fixture.
    No other module may independently read TDEASE_DATA_ROOT -- always go
    through this function.
    """
    global _storage
    if _storage is None:
        _storage = StorageLayout(os.environ.get("TDEASE_DATA_ROOT", "server-data"))
    return _storage


def get_system_root() -> Path:
    """System asset root directory.

    TDEASE_SYSTEM_ROOT env var is injected by Electron backend_manager.cjs
    as <dataRoot>/system/. Manual backend dev (no Electron) falls back to
    the repo data/system/.
    """
    from pathlib import Path as _Path
    return _Path(os.environ.get(
        "TDEASE_SYSTEM_ROOT",
        str(_Path(__file__).resolve().parent.parent.parent / "data" / "system")
    ))


def get_tools_root() -> Path:
    """Compute tools root directory (topfd/toppic/msconvert etc local executables).

    TDEASE_TOOLS_ROOT env var is injected by Electron backend_manager.cjs
    as <dataRoot>/backend/nodes/.
    """
    from pathlib import Path as _Path
    return _Path(os.environ.get(
        "TDEASE_TOOLS_ROOT",
        str(get_storage().data / "nodes"),
    ))


def set_storage(s: StorageLayout) -> None:
    global _storage
    _storage = s
