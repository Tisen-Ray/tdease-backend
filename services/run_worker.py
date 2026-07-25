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
from threading import Event
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.contracts import ErrorCode, RunCommit
from src.execution_runtime import execute, get_storage
from src.execution_runtime.storage import StorageLayout


def _data_root() -> Path:
    # 走唯一入口 get_storage()，避免散落的 os.environ.get(..., "server-data")。
    return get_storage().data


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

        try:
            if get_storage().claim_run(data["run_id"]):
                return data
            continue
        except (FileExistsError, KeyError, ValueError):
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
        workspace_files=run_data.get("workspace_files", []),
        local_workspace_root=run_data.get("local_workspace_root"),
        snakefile=run_data.get("snakefile", ""),
        config=run_data.get("config", {}),
        cores=run_data.get("cores", 4),
        user_id=run_data.get("user_id", "worker"),
        mode=run_data.get("mode", "local"),
        packages=run_data.get("packages", []),
        nodes=run_data.get("nodes", []),
        targets=run_data.get("targets", []),
        memory_mb=run_data.get("memory_mb"),
        labels=run_data.get("labels", {}),
    )

    # Update status to RUNNING via storage
    storage.atomic_write_json(
        _data_root() / "runs" / run_id / "run.json",
        {**run_data, "status": "RUNNING",
         "pid": os.getpid(),
         "started_at": datetime.now(timezone.utc).isoformat()},
    )

    try:
        # §4.3 defense-in-depth: create_run is the load-bearing gate, but a
        # hand-edited / replayed run.json could still reach the worker. Reject
        # before the engine starts so the run fails with an explicit Profile
        # error instead of producing a DAG the frontend cannot draw.
        from src.execution_runtime.profile_validator import validate_snakefile_profile
        profile = validate_snakefile_profile(commit.snakefile)
        if not profile.valid:
            raise ValueError(
                "Snakefile violates the static-parseable Profile (§4.3): "
                + "; ".join(profile.errors())
            )
        if commit.mode == "local":
            storage.verify_local_inputs(run_id)
        result = execute(commit)
        if commit.mode == "local":
            storage.verify_local_inputs(run_id)
    except Exception as exc:
        from src.execution_runtime.runtime import ExecutionResult
        from src.execution_runtime.errors import runtime_internal
        result = ExecutionResult(success=False, exit_code=-1, error=runtime_internal(str(exc)))

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

    if status == "SUCCEEDED":
        storage.write_results_manifest(run_id)

    # Cleanup claim
    storage.release_claim(run_id)


def run_loop(
    poll_interval: float = 1.0,
    once: bool = False,
    stop_event: Event | None = None,
) -> None:
    """Worker 主循环。"""
    storage = get_storage()
    storage.bootstrap()
    storage.reconcile_orphaned_runs()

    while True:
        if stop_event and stop_event.is_set():
            return
        try:
            run_data = _dequeue()
            if run_data:
                execute_run(run_data)
            elif once:
                break
            else:
                if stop_event:
                    stop_event.wait(poll_interval)
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
