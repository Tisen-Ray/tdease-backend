"""
TDEase Storage Layout — 系统中唯一的文件写入原语。

Not an adapter, not an interceptor. This IS the file primitive.
No module may use raw open/write/mkdir directly.

Rules (CONVERGENCE-PLAN.md §3.5):
- atomic_write: temp + fsync + rename + tmp cleanup + parent fsync
- append_event: JSONL, single-writer, internally-allocated monotonic seq
- blob: store/.incoming/<id> → rename to digest key
- temp: TemporaryDirectory only
- logs: fixed names, size caps, rotation, deep write operations
- trash: move → GC with retention

P1 fixes (code review):
- allocate_run: exist_ok=True (API + worker both call, must be idempotent)
- recover_seq: returns persisted last seq from events.jsonl
- check_cancelled / mark_cancelled: unified cancel signal
- resolve: validates run_id and containment

P2 fixes:
- atomic_write: tmp cleanup on write/fsync/replace failure; fsync parent
- append_event: allocates seq internally (only writer)
- append_runtime_record / append_task_output: deep log operations
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

RUN_ID_PATTERN = __import__("re").compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$")


class StorageLayout:
    """TDEase 唯一文件原语。"""

    def __init__(
        self,
        data_root: str | Path,
        cache_root: str | Path | None = None,
        trash_root: str | Path | None = None,
    ):
        self.data = Path(data_root)
        self.cache = Path(cache_root) if cache_root else self.data / "cache"
        self.trash = Path(trash_root) if trash_root else self.data / "trash"

    # ── Bootstrap ──

    def bootstrap(self) -> None:
        """一次性创建固定目录结构。

        与 electron/runtime_config.cjs ensureRuntimeDirectories 对齐。
        不创建 workspaces/（老布局遗留：归属是 run.json 字段而非目录）。
        不创建 system/（随应用发布的资产投影，非运行时 mkdir）。
        """
        for d in [
            self.data / "database",
            self.data / "store",
            self.data / "runs",
            self.cache,
            self.trash,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    # ── Run directory ──

    def allocate_run(self, run_id: str) -> Path:
        """幂等创建 run 目录结构。API 和 worker 都可安全调用。"""
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
        """解析 run 内的路径。验证 run_id 和 containment。"""
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

    # ── Atomic write ──

    def atomic_write(self, target: Path, content: str | bytes) -> None:
        """
        原子写入规范文件。

        同目录临时文件 → fsync → os.replace → fsync parent → cleanup。
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
        # Fsync parent directory for durability (Unix only — Windows rejects dir fsync)
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

    # ── Events (JSONL append, single-writer) ──

    def events_path(self, run_id: str) -> Path:
        return self.resolve(run_id, "events.jsonl")

    def recover_seq(self, run_id: str) -> int:
        """返回 events.jsonl 中已持久化的最大 seq。0 = 空。"""
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
        追加一行事件。分配并返回 monotonic seq。
        通过 recover_seq + 1 开始；调用方不应手动设置 seq。
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

    # ── Logs (deep operations) ──

    def append_runtime_record(self, run_id: str, level: str, message: str,
                               task_id: str | None = None, max_mb: int = 50) -> None:
        """追加结构化诊断记录。自动处理轮转。"""
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
        """追加 task stdout/stderr。大小受限，超过上限时轮转。"""
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

    # ── Cancel signal ──

    def cancel_path(self, run_id: str) -> Path:
        return self.resolve(run_id, ".runtime", "cancelled")

    def mark_cancelled(self, run_id: str) -> None:
        self.atomic_write(self.cancel_path(run_id), "")

    def check_cancelled(self, run_id: str) -> bool:
        return self.cancel_path(run_id).exists()

    # ── Temp ──

    @contextmanager
    def temp_dir(self, scope: str, purpose: str) -> Iterator[Path]:
        d = self.cache / "tmp" / scope
        d.mkdir(parents=True, exist_ok=True)
        td = tempfile.mkdtemp(prefix=f"{purpose}-", dir=str(d))
        try:
            yield Path(td)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    # ── Blob store ──

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
                                    entries: list[Any]) -> None:
        """Freeze controls and share large local inputs without network/CAS transfer."""
        workspace_root = workspace_root.resolve()
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
        self.atomic_write_json(self.resolve(run_id, ".tdease-runtime", "local-inputs.json"), shared)

    def verify_local_inputs(self, run_id: str) -> None:
        manifest = self.read_json(self.resolve(run_id, ".tdease-runtime", "local-inputs.json")) or []
        for item in manifest:
            path = self.resolve(run_id, item["path"])
            if not path.is_file() or self.file_digest(path) != item["sha256"]:
                raise ValueError(f"local shared input changed: {item['path']}")

    def write_results_manifest(self, run_id: str) -> Path:
        entries = []
        for path in self.result_files(run_id):
            if path.is_file():
                entries.append({"path": path.relative_to(self.resolve(run_id)).as_posix(),
                                "size": path.stat().st_size, "sha256": self.file_digest(path)})
        target = self.resolve(run_id, "results.manifest.json")
        self.atomic_write_json(target, {"schema_version": 1, "run_id": run_id, "files": entries})
        return target

    def reconcile_orphaned_runs(self) -> list[str]:
        """Return dead RUNNING runs to QUEUED using file truth, no extra state axis.

        Checks engine_pid (the actual engine_runner subprocess) before falling back
        to pid (the worker). Kills a surviving orphan engine before re-queueing to
        prevent double-run.
        """
        import psutil
        recovered: list[str] = []
        runs = self.data / "runs"
        if not runs.is_dir():
            return recovered
        for directory in runs.iterdir():
            data = self.read_json(directory / "run.json") if directory.is_dir() else None
            if not data or data.get("status") != "RUNNING":
                continue
            # 优先查 engine_pid（engine_runner 子进程），其次 pid（worker）。
            engine_pid = data.get("engine_pid")
            worker_pid = data.get("pid")
            run_id = data["run_id"]
            orphan_alive = False
            for pid_val in (engine_pid, worker_pid):
                if pid_val and psutil.pid_exists(int(pid_val)):
                    orphan_alive = True
                    # 孤儿 engine 存活：先 kill 再重排，防双跑。
                    if pid_val == engine_pid:
                        try:
                            p = psutil.Process(int(pid_val))
                            p.terminate()
                            p.wait(timeout=3)
                        except Exception:
                            try:
                                p.kill()
                            except Exception:
                                pass
                    break
            if orphan_alive:
                # 孤儿还在跑，不重排队——等下次 reconcile。
                continue
            self.release_claim(run_id)
            self.atomic_write_json(directory / "run.json", {**data, "status": "QUEUED", "pid": None, "engine_pid": None})
            recovered.append(run_id)
        return recovered

    # ── Trash ──

    def move_to_trash(self, path: Path) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        dest = self.trash / f"{ts}_{path.name}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))

    # ── Result access ──

    def result_files(self, run_id: str) -> list[Path]:
        rd = self.resolve(run_id, "results")
        if not rd.exists():
            return []
        return sorted(rd.rglob("*"))


# ── Module singleton ──

_storage: Optional[StorageLayout] = None


def get_storage() -> StorageLayout:
    """唯一 backend data-root 解析入口。

    优先级：TDEASE_DATA_ROOT 环境变量 > "server-data" 字面量（仅手工后端
    开发兜底）。桌面 app 由 Electron backend_manager.cjs 注入
    `<dataRoot>/backend/`；测试由 conftest/fixture 注入临时目录。
    其它模块不得再独立读 TDEASE_DATA_ROOT —— 一律走本函数。
    """
    global _storage
    if _storage is None:
        _storage = StorageLayout(os.environ.get("TDEASE_DATA_ROOT", "server-data"))
    return _storage


def get_system_root() -> Path:
    """System 资产根目录。

    TDEASE_SYSTEM_ROOT 环境变量由 Electron backend_manager.cjs 注入
    为 `<dataRoot>/system/`。仅手工后端开发（无 Electron 时）回退到
    仓库 `data/system/`。
    """
    from pathlib import Path as _Path
    return _Path(os.environ.get(
        "TDEASE_SYSTEM_ROOT",
        str(_Path(__file__).resolve().parent.parent.parent / "data" / "system")
    ))


def get_tools_root() -> Path:
    """计算工具根目录（topfd/toppic/msconvert 等本地可执行文件）。

    TDEASE_TOOLS_ROOT 环境变量由 Electron backend_manager.cjs 注入
    为 `<dataRoot>/backend/nodes/`。
    """
    from pathlib import Path as _Path
    return _Path(os.environ.get(
        "TDEASE_TOOLS_ROOT",
        str(get_storage().data / "nodes"),
    ))


def set_storage(s: StorageLayout) -> None:
    global _storage
    _storage = s
