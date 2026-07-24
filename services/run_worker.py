"""
Run Worker — 文件扫描队列 → TDEase Execution Runtime → events.jsonl。

设计约束：
- ~50 行业务逻辑。守护/重启/cgroup 交给 systemd。
- 原子领取（O_CREAT | O_EXCL claim 文件）。
- 调用 Execution Runtime execute()。
- 状态更新全部通过 Storage Layout。
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.contracts import ErrorCode, RunCommit
from src.execution_runtime import execute, get_storage
from src.execution_runtime.storage import StorageLayout


def _data_root() -> Path:
    return Path(os.environ.get("TDEASE_DATA_ROOT", "server-data"))


def _dequeue() -> Optional[dict]:
    """扫描 runs/，原子领取第一个 QUEUED run（O_CREAT|O_EXCL claim 文件）。"""
    runs_dir = _data_root() / "runs"
    if not runs_dir.exists():
        return None

    for rd in sorted(runs_dir.iterdir()):
        if not rd.is_dir():
            continue
        rj = rd / "run.json"
        if not rj.exists():
            continue
        data = json.loads(rj.read_text(encoding="utf-8"))
        if data.get("status") != "QUEUED":
            continue

        claim = rd / ".claimed"
        try:
            fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return data
        except FileExistsError:
            continue

    return None


def execute_run(run_data: dict) -> None:
    """执行一次 Run — 全部通过 Execution Runtime。"""
    run_id = run_data["run_id"]
    storage = get_storage()
    storage.bootstrap()

    # Idempotent — API already created dir and wrote run.queued event
    storage.allocate_run(run_id)

    commit = RunCommit(
        run_id=run_id,
        idempotency_key=run_data.get("idempotency_key", ""),
        workspace_id=run_data.get("workspace_id", ""),
        workspace_tree_hash=run_data.get("workspace_tree_hash", "0" * 64),
        snakefile=run_data.get("snakefile", ""),
        config=run_data.get("config", {}),
        cores=run_data.get("cores", 4),
        user_id=run_data.get("user_id", "worker"),
        mode=run_data.get("mode", "local"),
        packages=run_data.get("packages", []),
        nodes=run_data.get("nodes", []),
    )

    # Update status to RUNNING via storage
    storage.atomic_write_json(
        _data_root() / "runs" / run_id / "run.json",
        {**run_data, "status": "RUNNING",
         "pid": os.getpid(),
         "started_at": datetime.now(timezone.utc).isoformat()},
    )

    result = execute(commit)

    # Terminal status via storage
    status = (
        "SUCCEEDED" if result.success
        else "CANCELLED" if result.error and result.error.code == ErrorCode.EXECUTION_CANCELLED
        else "FAILED"
    )
    run_json = _data_root() / "runs" / run_id / "run.json"
    current = json.loads(run_json.read_text(encoding="utf-8"))
    storage.atomic_write_json(run_json, {
        **current, "status": status,
        "exit_code": result.exit_code,
        "error": str(result.error) if result.error else None,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    })

    # Cleanup claim
    (_data_root() / "runs" / run_id / ".claimed").unlink(missing_ok=True)


def run_loop(poll_interval: float = 1.0, once: bool = False) -> None:
    """Worker 主循环。"""
    get_storage().bootstrap()

    while True:
        try:
            run_data = _dequeue()
            if run_data:
                execute_run(run_data)
            elif once:
                break
            else:
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            break
        except Exception:
            import traceback
            traceback.print_exc()
            time.sleep(poll_interval)


if __name__ == "__main__":
    once = "--once" in sys.argv
    run_loop(once=once)
