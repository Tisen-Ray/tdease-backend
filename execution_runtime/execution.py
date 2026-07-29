"""Generic process resource helpers used at workflow process boundaries."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Mapping, Sequence

from src.execution_runtime.storage import get_storage
from src.execution_runtime.resource_budget import RESOURCE_BUDGET


def _isolate_engine_process(run_id: str, task_id: str, pid: int) -> None:
    """Constrain the workflow-engine subtree while leaving service CPUs available."""
    try:
        import psutil

        _apply_compute_isolation(psutil.Process(pid), psutil)
    except Exception as exc:
        message = f"engine resource isolation could not be applied: {exc}"
        storage = get_storage()
        storage.append_task_output(run_id, task_id, "stderr", f"WARNING: {message}\n")
        storage.append_runtime_record(run_id, "warning", message, task_id)


def _isolate_engine_descendants(engine_pid: int) -> None:
    """Apply the Backend budget to every scientific process spawned later."""
    import psutil

    isolated: set[int] = set()
    while psutil.pid_exists(engine_pid):
        try:
            engine = psutil.Process(engine_pid)
            descendants = engine.children(recursive=True)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        for process in descendants:
            if process.pid in isolated:
                continue
            try:
                _apply_compute_isolation(process, psutil)
                isolated.add(process.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                continue
        time.sleep(0.25)


def run_captured_process(
    command: Sequence[str],
    cwd: str | Path,
    timeout: int,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a captured workflow subprocess with the same CPU isolation as Runs."""
    proc = subprocess.Popen(
        list(command),
        cwd=str(cwd),
        env=env if env is not None else os.environ,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    try:
        import psutil

        _apply_compute_isolation(psutil.Process(proc.pid), psutil)
        threading.Thread(
            target=_isolate_engine_descendants,
            args=(proc.pid,),
            daemon=True,
        ).start()
    except Exception:
        pass

    captured: list[str] = ["", ""]

    def communicate() -> None:
        captured[0], captured[1] = proc.communicate()

    reader = threading.Thread(target=communicate, daemon=True)
    reader.start()
    deadline = time.monotonic() + timeout
    failure: str | None = None
    while proc.poll() is None:
        if time.monotonic() > deadline:
            failure = f"workflow process timed out after {timeout}s"
            _kill_process_group(proc)
            break
        time.sleep(0.25)
    reader.join(timeout=5)
    if failure:
        captured[1] = f"{captured[1]}\n{failure}\n"
    return subprocess.CompletedProcess(
        args=list(command),
        returncode=proc.returncode if proc.returncode is not None else -1,
        stdout=captured[0],
        stderr=captured[1],
    )


def _apply_compute_isolation(process, psutil_module) -> None:
    process.cpu_affinity(list(RESOURCE_BUDGET.compute_cpu_ids))
    if os.name == "nt":
        process.nice(psutil_module.BELOW_NORMAL_PRIORITY_CLASS)
    else:
        process.nice(5)


def _kill_process_group(proc: subprocess.Popen) -> None:
    """终止进程组：SIGTERM → 短暂等待 → SIGKILL。"""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            # Windows: taskkill /T kills entire tree
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, timeout=5,
            )
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    proc.kill()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
    except Exception:
        try: proc.kill()
        except Exception: pass
