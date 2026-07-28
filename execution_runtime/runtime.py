"""
TDEase Execution Runtime — 程序化入口。

Worker 调用:
  preflight(commit) -> PreflightResult
  execute(commit) -> ExecutionResult
  cancel(run_id)   -> bool

preflight 和 execute 共用 parser.py 的 parse_snakefile 作为唯一解析入口。
execute 在 task 之间检查 storage.check_cancelled(run_id)。
错误分类：ExecutionError 原样传递，未知异常 → execution_runtime_internal。
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from src.contracts import RunCommit
from src.execution_runtime.parser import parse_snakefile
from src.execution_runtime.execution import execute_task
from src.execution_runtime.engine_contract import WorkflowEngineRequest
from src.execution_runtime.engine_layout import cleanup_engine_alias
from src.execution_runtime.errors import (
    ExecutionError,
    invalid_workflow,
    runtime_internal,
    cancelled,
    task_failed,
)
from src.execution_runtime.events import EventEmitter
from src.execution_runtime.storage import get_storage
from src.execution_runtime.resource_budget import RESOURCE_BUDGET


@dataclass
class PreflightResult:
    """preflight() 返回 — 临时 view model，不持久化。"""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_steps: int = 0
    missing_inputs: list[str] = field(default_factory=list)
    tools_required: list[str] = field(default_factory=list)
    step_labels: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """execute() 返回。"""
    success: bool
    exit_code: Optional[int] = None
    error: Optional[ExecutionError] = None
    run_time_seconds: float = 0.0
    total_tasks: int = 0
    succeeded_tasks: int = 0
    failed_tasks: int = 0
    final_seq: int = 0


def preflight(commit: RunCommit) -> PreflightResult:
    """
    校验 Run commit 的可执行性。
    统一使用 parser.py 的 parse_snakefile 作为唯一解析入口。
    """
    errors: list[str] = []
    warnings: list[str] = []
    tools: set[str] = set()
    step_labels: list[str] = []

    try:
        wf = parse_snakefile(commit.snakefile, f"run:{commit.run_id}")
    except SyntaxError as e:
        return PreflightResult(valid=False, errors=[f"Syntax error: {e}"])
    except ExecutionError as e:
        return PreflightResult(valid=False, errors=[str(e)])

    unsupported: set[str] = set()

    # Shell builtins / constructs that don't need PATH resolution
    _SHELL_BUILTINS = frozenset({
        "echo", "python", "python3", "ls", "cat", "mkdir", "cd", "true", "false",
        "if", "then", "else", "elif", "fi", "for", "while", "do", "done",
        "case", "esac", "in", "wc", "export", "source", ".", "set", "unset",
        "env", "exec", "xargs", "find", "grep", "sed", "awk", "sort", "uniq",
        "cut", "tr", "head", "tail", "tee", "basename", "dirname", "printf",
        "date", "time", "test", "[", "cp", "mv", "rm", "chmod", "ln",
    })
    # Proteomics tools — checked against PATH; .exe stripped on Windows
    _KNOWN_PROTEO_TOOLS = frozenset({
        "topfd", "toppic", "topindex", "topmg", "topdiff", "topdia",
        "msconvert",
    })

    for rule in wf.rules:
        step_labels.append(rule.name)
        if rule.unsupported:
            unsupported.update(rule.unsupported)
            errors.append(f"rule '{rule.name}': unsupported {sorted(rule.unsupported)}")
        if rule.is_checkpoint:
            errors.append(f"rule '{rule.name}': checkpoint not supported")
        if not rule.shellcmd:
            errors.append(f"rule '{rule.name}': only shell rules are supported")
            continue
        first = rule.shellcmd.strip().split()[0] if rule.shellcmd.strip() else ""
        if not first:
            continue
        # Absolute paths (contain / or \) are trusted as-is
        if "/" in first or "\\" in first:
            continue
        # Strip .exe suffix on Windows
        first_name = first.rsplit(".", 1)[0] if "." in first else first
        if first_name in _SHELL_BUILTINS or first_name in _KNOWN_PROTEO_TOOLS:
            continue
        tools.add(first)

    import shutil
    for tool in sorted(tools):
        if shutil.which(tool) is None and shutil.which(tool + ".exe") is None:
            errors.append(f"tool not found: {tool}")

    if unsupported:
        errors.insert(0, f"unsupported directives: {', '.join(sorted(unsupported))}")

    return PreflightResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        estimated_steps=len(wf.rules),
        tools_required=sorted(tools),
        step_labels=step_labels,
    )


def execute(commit: RunCommit, rerun_mode: str = "resume") -> ExecutionResult:
    """
    执行 Run commit。

    1. parse_snakefile（统一解析入口，与 preflight 共用）
    2. Popen-based task execution（流式日志 + cancel 检查）
    3. 错误分类：ExecutionError 原样保留，未知异常 → runtime_internal
    """
    storage = get_storage()
    run_id = commit.run_id

    # Idempotent — worker re-enters after API
    storage.allocate_run(run_id)

    emitter = EventEmitter(run_id)

    start = time.perf_counter()
    emitter.run_started(pid=os.getpid(), worker_id=platform.node())
    # Long workflows must become publicly RUNNING as soon as their worker starts,
    # rather than remaining QUEUED until the terminal projection after execute().
    storage.sync_run_projection(commit.run_id)
    snakefile_path = storage.resolve(run_id, "Snakefile")
    storage.atomic_write(snakefile_path, commit.snakefile)

    # Snakemake is the DAG/runtime authority. TDEase supervises one process;
    # it must not reinterpret the Snakefile or execute rules itself.
    total, succeeded, failed = 1, 0, 0
    execution_root = storage.resolve(run_id)
    run_dir = str(execution_root)
    effective_cores = min(commit.cores, RESOURCE_BUDGET.compute_cpus)
    if effective_cores != commit.cores:
        storage.append_runtime_record(
            run_id,
            "warning",
            (
                f"stored Run requested {commit.cores} cores; execution was limited "
                f"to the current Backend budget of {effective_cores}"
            ),
            "engine",
        )
    engine_request = WorkflowEngineRequest(
        mode="execute",
        snakefile="Snakefile",
        config=commit.config,
        cores=effective_cores,
        targets=commit.targets,
        rerun_mode=rerun_mode,
        rerun_incomplete=True,
        retries=0,
        job_event_path=".tdease/job-events.jsonl",
    )
    storage.atomic_write_json(
        execution_root / ".tdease" / "engine-request.json",
        engine_request.model_dump(),
    )
    command_parts = [sys.executable, "-m", "src.execution_runtime.engine_runner"]
    try:
        ok, ec, _elapsed, err_text = execute_task(
            run_id=run_id, task_id="engine", step_label="Workflow engine",
            command=command_parts, cwd=run_dir, emitter=emitter,
            display_command="TDEase Workflow Engine",
            timeout=7 * 24 * 60 * 60,
        )
    finally:
        cleanup_engine_alias(execution_root)
    if not ok and (err_text == "cancelled" or storage.check_cancelled(run_id)):
        emitter.run_cancelled(time.perf_counter() - start)
        return ExecutionResult(success=False, exit_code=ec, error=cancelled(run_id),
            run_time_seconds=time.perf_counter() - start, total_tasks=1,
            final_seq=emitter.last_seq)
    if ok:
        succeeded = 1
    else:
        failed = 1
        total_elapsed = time.perf_counter() - start
        error = task_failed("engine", ec, err_text)
        emitter.run_failed(ec, total_elapsed, str(error))
        return ExecutionResult(success=False, exit_code=ec, error=error,
            run_time_seconds=total_elapsed, total_tasks=1, failed_tasks=1,
            final_seq=emitter.last_seq)

    # ── 3. Terminal event ──
    total_elapsed = time.perf_counter() - start
    final_exit = 0 if failed == 0 else 1

    if final_exit == 0:
        emitter.run_succeeded(total_elapsed, total)
    else:
        emitter.run_failed(final_exit, total_elapsed, f"{failed}/{total} tasks failed")

    return ExecutionResult(
        success=final_exit == 0,
        exit_code=final_exit,
        run_time_seconds=total_elapsed,
        total_tasks=total,
        succeeded_tasks=succeeded,
        failed_tasks=failed,
        final_seq=emitter.last_seq,
    )


def cancel(run_id: str) -> bool:
    """标记 run 为已取消。worker 在 task 之间和 task 内检查此标记。"""
    storage = get_storage()
    storage.mark_cancelled(run_id)
    return True
