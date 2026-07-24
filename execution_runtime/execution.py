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
from pathlib import Path
from typing import Optional

from src.execution_runtime.events import EventEmitter
from src.execution_runtime.storage import get_storage


def execute_task(
    run_id: str,
    task_id: str,
    step_label: str,
    command: str,
    cwd: str,
    env: dict[str, str] | None = None,
    timeout: int = 600,
    emitter: Optional[EventEmitter] = None,
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

    sanitized_cmd = _sanitize_command(command)
    if emitter:
        emitter.task_started(task_id, step_label, sanitized_cmd)

    start = time.perf_counter()
    exit_code = -1
    stderr_lines: list[str] = []

    try:
        popen_kwargs: dict = dict(
            shell=True,
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
    except FileNotFoundError:
        elapsed = time.perf_counter() - start
        msg = f"command not found: {command.split()[0]}"
        if emitter:
            emitter.task_failed(task_id, -1, elapsed, msg)
        storage.append_task_output(run_id, task_id, "stderr", msg)
        return False, -1, elapsed, msg

    try:
        def drain(stream, name: str) -> None:
            if stream is None:
                return
            for line in iter(stream.readline, ""):
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

        deadline = start + timeout
        while proc.poll() is None:
            # Check cancel
            if storage.check_cancelled(run_id):
                _kill_process_group(proc)
                elapsed = time.perf_counter() - start
                if emitter:
                    emitter.task_failed(task_id, -1, elapsed, "cancelled")
                for reader in readers:
                    reader.join(timeout=1)
                return False, -1, elapsed, "cancelled"

            # Check timeout
            if time.perf_counter() > deadline:
                _kill_process_group(proc)
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


def _sanitize_command(cmd: str) -> str:
    """脱敏 command for events — 截断 secret-like patterns。"""
    import re
    s = cmd
    for pat in [r'(token[=:]\s*)\S+', r'(password[=:]\s*)\S+',
                 r'(secret[=:]\s*)\S+', r'(key[=:]\s*)\S{8,}',
                 r'(--password[=\s]+)\S+', r'(Bearer\s+)\S+']:
        s = re.sub(pat, r'\1***', s, flags=re.IGNORECASE)
    return s


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
