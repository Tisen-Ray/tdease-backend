"""
TDEase Task Execution — 本地任务执行能力。

Popen-based: 流式捕获 stdout/stderr → storage task logs, 周期性 cancel 检查,
超时后终止进程组, 正确的错误分类。

Provenance: provenance/source-ledger.json — prov-003
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import json
from pathlib import Path
from typing import Optional, Sequence

from src.execution_runtime.events import EventEmitter
from src.execution_runtime.storage import get_storage
from src.execution_runtime.resource_budget import RESOURCE_BUDGET


def execute_task(
    run_id: str,
    task_id: str,
    step_label: str,
    command: str | Sequence[str],
    cwd: str,
    env: dict[str, str] | None = None,
    timeout: int = 600,
    emitter: Optional[EventEmitter] = None,
    display_command: str | None = None,
) -> tuple[bool, int, float, str]:
    """
    执行单个 task。返回 (success, exit_code, duration_seconds, stderr_tail)。

    - Popen shell command，独立进程组
    - stdout → storage.append_task_output（流式，逐行）
    - stderr → storage.append_task_output（流式，逐行）
    - 每个输出行后检查 cancel marker
    - 超时后向进程组发 SIGTERM → SIGKILL
    - 命令脱敏后写入 event
    """
    storage = get_storage()
    run_dir = Path(cwd)

    command_text = display_command or (
        command if isinstance(command, str) else subprocess.list2cmdline(list(command))
    )
    sanitized_cmd = _sanitize_command(command_text)
    if emitter:
        emitter.task_started(task_id, step_label, sanitized_cmd)

    start = time.perf_counter()
    exit_code = -1
    stderr_lines: list[str] = []

    try:
        if task_id == "engine":
            (run_dir / ".tdease" / "job-events.jsonl").unlink(missing_ok=True)
        popen_kwargs: dict = dict(
            shell=isinstance(command, str),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(run_dir),
            env=env or os.environ,
        )
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(command, **popen_kwargs)
        if task_id == "engine":
            _isolate_engine_process(run_id, task_id, proc.pid)
            threading.Thread(
                target=_isolate_engine_descendants,
                args=(proc.pid,),
                daemon=True,
            ).start()
        # 记录 engine_runner 真实 pid（非 worker/uvicorn pid），
        # 以便 reconcile_orphaned_runs 正确识别并 kill 孤儿进程。
        if task_id == "engine":
            _record_engine_pid(run_id, proc.pid)
    except FileNotFoundError:
        elapsed = time.perf_counter() - start
        executable = command.split()[0] if isinstance(command, str) else command[0]
        msg = f"command not found: {executable}"
        if emitter:
            emitter.task_failed(task_id, -1, elapsed, msg)
        storage.append_task_output(run_id, task_id, "stderr", msg)
        return False, -1, elapsed, msg

    try:
        def drain(stream, name: str) -> None:
            if stream is None:
                return
            for line in iter(stream.readline, ""):
                if task_id == "engine":
                    line = _brand_engine_output(line)
                storage.append_task_output(run_id, task_id, name, line)
                if name == "stderr":
                    stderr_lines.append(line)
                    if len(stderr_lines) > 200:
                        del stderr_lines[:-100]

        readers = [
            threading.Thread(target=drain, args=(proc.stdout, "stdout"), daemon=True),
            threading.Thread(target=drain, args=(proc.stderr, "stderr"), daemon=True),
        ]
        for reader in readers:
            reader.start()

        job_event_stop = threading.Event()
        job_event_reader = None
        if task_id == "engine" and emitter is not None:
            job_event_reader = threading.Thread(
                target=_relay_job_events,
                args=(run_dir / ".tdease" / "job-events.jsonl", emitter, job_event_stop),
                daemon=True,
            )
            job_event_reader.start()

        deadline = start + timeout
        while proc.poll() is None:
            # Check cancel
            if storage.check_cancelled(run_id):
                _kill_process_group(proc)
                job_event_stop.set()
                elapsed = time.perf_counter() - start
                if emitter:
                    emitter.task_failed(task_id, -1, elapsed, "cancelled")
                for reader in readers:
                    reader.join(timeout=1)
                return False, -1, elapsed, "cancelled"

            # Check timeout
            if time.perf_counter() > deadline:
                _kill_process_group(proc)
                job_event_stop.set()
                elapsed = time.perf_counter() - start
                msg = f"task timed out after {timeout}s"
                if emitter:
                    emitter.task_failed(task_id, -1, elapsed, msg)
                storage.append_task_output(run_id, task_id, "stderr", msg)
                for reader in readers:
                    reader.join(timeout=1)
                return False, -1, elapsed, msg
            time.sleep(0.05)

        for reader in readers:
            reader.join(timeout=2)
        job_event_stop.set()
        if job_event_reader:
            job_event_reader.join(timeout=2)

        exit_code = proc.returncode

    except Exception as e:
        _kill_process_group(proc)
        elapsed = time.perf_counter() - start
        msg = f"execution error: {e}"
        if emitter:
            emitter.task_failed(task_id, -1, elapsed, msg)
        storage.append_task_output(run_id, task_id, "stderr", msg)
        storage.append_runtime_record(run_id, "error", msg, task_id)
        return False, -1, elapsed, msg

    elapsed = time.perf_counter() - start
    stderr_tail = "".join(stderr_lines[-50:]) if stderr_lines else ""
    success = exit_code == 0

    if emitter:
        if success:
            emitter.task_succeeded(task_id, elapsed)
        else:
            emitter.task_failed(task_id, exit_code, elapsed, stderr_tail[-500:])

    return success, exit_code, elapsed, stderr_tail


def _relay_job_events(path: Path, emitter: EventEmitter, stop: threading.Event) -> None:
    offset = 0
    while not stop.is_set() or (path.exists() and path.stat().st_size > offset):
        if not path.exists():
            stop.wait(0.1)
            continue
        with path.open("r", encoding="utf-8") as stream:
            stream.seek(offset)
            for line in stream:
                try:
                    payload = json.loads(line)
                    if payload.get("type") == "workflow.graph":
                        emitter.workflow_graph({"nodes": payload.get("nodes", []), "edges": payload.get("edges", [])})
                    else:
                        emitter.job_event(
                            __import__("src.contracts", fromlist=["EventType"]).EventType(payload["type"]),
                            int(payload["job_id"]), str(payload["rule"]), payload.get("wildcards"),
                        )
                except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                    continue
            offset = stream.tell()
        stop.wait(0.1)


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


def _apply_compute_isolation(process, psutil_module) -> None:
    process.cpu_affinity(list(RESOURCE_BUDGET.compute_cpu_ids))
    if os.name == "nt":
        process.nice(psutil_module.BELOW_NORMAL_PRIORITY_CLASS)
    else:
        process.nice(5)


def _sanitize_command(cmd: str) -> str:
    """脱敏 command for events — 截断 secret-like patterns。"""
    import re
    s = cmd
    for pat in [r'(token[=:]\s*)\S+', r'(password[=:]\s*)\S+',
                 r'(secret[=:]\s*)\S+', r'(key[=:]\s*)\S{8,}',
                 r'(--password[=\s]+)\S+', r'(Bearer\s+)\S+']:
        s = re.sub(pat, r'\1***', s, flags=re.IGNORECASE)
    return s


def _brand_engine_output(text: str) -> str:
    """Keep the product log protocol TDEase-owned while retaining diagnostics."""
    import re

    branded = (
        text.replace("SNAKEMAKE", "TDEASE WORKFLOW ENGINE")
        .replace("Snakemake version:", "Engine version:")
        .replace("snakemake --", "workflow-engine --")
        .replace(".snakemake", ".tdease/engine")
    )
    return re.sub(r"(?m)^  Command:.*$", "  Command: TDEase Workflow Engine", branded)


def _record_engine_pid(run_id: str, pid: int) -> None:
    """Write engine_runner pid into run.json so reconcile can find/kill orphans."""
    try:
        import json as _json
        storage = get_storage()
        run_json = storage.resolve(run_id, "run.json")
        data = storage.read_json(run_json)
        if data:
            data["engine_pid"] = pid
            storage.atomic_write_json(run_json, data)
    except Exception:
        pass  # best-effort; pid record failure must not crash the engine


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
