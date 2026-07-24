"""
LocalBackend — Pure Desktop 模式。

Snakemake 直接 subprocess 在本地跑。
队列在 SQLite 里，worker 在主进程中轮询。
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.backends.base import WorkspaceBackend, RunInfo

logger = logging.getLogger(__name__)


class LocalBackend(WorkspaceBackend):
    """Pure Desktop 实现：一切都在本地。"""

    def __init__(self, data_dir: str | Path = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, RunInfo] = {}  # 内存缓存
        self._processes: dict[str, asyncio.subprocess.Process] = {}  # 活跃进程
        self._load_runs()

    # ------------------------------------------------------------------
    # 队列存储 (JSONL — 简单，不需要 SQLite)
    # ------------------------------------------------------------------

    @property
    def _runs_file(self) -> Path:
        return self.data_dir / "runs.jsonl"

    def _load_runs(self) -> None:
        if self._runs_file.exists():
            with open(self._runs_file) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        self._runs[d["id"]] = RunInfo(**d)
                    except Exception:
                        pass

    def _save_run(self, run: RunInfo) -> None:
        self._runs[run.id] = run
        with open(self._runs_file, "a") as f:
            f.write(json.dumps({
                "id": run.id,
                "workspace": run.workspace,
                "status": run.status,
                "mode": run.mode,
                "pid": run.pid,
                "exit_code": run.exit_code,
                "error": run.error,
                "created_at": run.created_at,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
            }, default=str) + "\n")

    # ------------------------------------------------------------------
    # 接口实现
    # ------------------------------------------------------------------

    async def submit(
        self,
        workspace: str,
        snakefile: str,
        config: Optional[dict] = None,
        cores: int = 4,
    ) -> RunInfo:
        wid = f"run_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        run = RunInfo(
            id=wid,
            workspace=workspace,
            status="QUEUED",
            mode="local",
            created_at=now,
        )
        self._save_run(run)

        # 异步启动 worker（非阻塞）
        asyncio.create_task(self._run_worker(run, snakefile, cores))

        return run

    async def _run_worker(self, run: RunInfo, snakefile: str, cores: int) -> None:
        """执行 Snakemake 子进程。"""
        run.status = "RUNNING"
        run.started_at = datetime.now(timezone.utc).isoformat()
        self._save_run(run)

        # 快照 Snakefile + config
        snap_dir = Path(run.workspace) / ".tdease" / "snapshots" / run.id
        snap_dir.mkdir(parents=True, exist_ok=True)
        src_snake = Path(snakefile)
        if src_snake.exists():
            shutil.copy2(src_snake, snap_dir / src_snake.name)

        log_file = Path(run.workspace) / ".tdease" / "logs" / f"{run.id}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            proc = await asyncio.create_subprocess_exec(
                "snakemake",
                "-s", str(snakefile),
                "--directory", run.workspace,
                "--cores", str(cores),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            run.pid = proc.pid
            self._save_run(run)

            # 流式写日志
            with open(log_file, "w") as lf:
                if proc.stdout:
                    async for line in proc.stdout:
                        lf.write(line.decode(errors="replace"))

            await proc.wait()

            run.exit_code = proc.returncode
            run.status = "DONE" if proc.returncode == 0 else "FAILED"
        except Exception as e:
            run.status = "FAILED"
            run.error = str(e)
            logger.exception("Run %s failed", run.id)
        finally:
            run.finished_at = datetime.now(timezone.utc).isoformat()
            self._save_run(run)

    async def status(self, run_id: str) -> Optional[RunInfo]:
        return self._runs.get(run_id)

    async def pull(
        self,
        run_id: str,
        patterns: list[str] | None = None,
        dest: str | Path | None = None,
    ) -> list[str]:
        run = self._runs.get(run_id)
        if not run:
            raise ValueError(f"Run not found: {run_id}")

        patterns = patterns or ["results/**"]
        dest = Path(dest or Path.cwd() / "downloads" / run_id)
        dest.mkdir(parents=True, exist_ok=True)

        pulled = []
        src_root = Path(run.workspace)
        import glob as _glob
        for pat in patterns:
            for f in src_root.glob(pat):
                if f.is_file():
                    rel = f.relative_to(src_root)
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, target)
                    pulled.append(str(target))
        return pulled

    async def fetch(self, run_id: str, path: str) -> Optional[Path]:
        run = self._runs.get(run_id)
        if not run:
            return None
        fp = Path(run.workspace) / path
        return fp if fp.exists() else None

    async def tail_log(self, run_id: str, lines: int = 50) -> str:
        log_file = Path(self._runs[run_id].workspace) / ".tdease" / "logs" / f"{run_id}.log"
        if not log_file.exists():
            return ""
        result = subprocess.run(
            ["tail", "-n", str(lines), str(log_file)],
            capture_output=True, text=True,
        )
        # Windows 没有 tail，回退到 Python
        if result.returncode != 0:
            with open(log_file) as f:
                all_lines = f.readlines()
            return "".join(all_lines[-lines:])
        return result.stdout

    async def list_runs(self, workspace: str) -> list[RunInfo]:
        return [r for r in self._runs.values() if r.workspace == workspace]

    async def cancel(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if not run or not run.is_active:
            return False
        if run.pid:
            import os as _os
            import signal as _sig
            try:
                _os.kill(run.pid, _sig.SIGTERM)
            except Exception:
                pass
        run.status = "FAILED"
        run.error = "Cancelled by user"
        run.finished_at = datetime.now(timezone.utc).isoformat()
        self._save_run(run)
        return True
