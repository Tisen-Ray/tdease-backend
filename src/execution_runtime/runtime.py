"""
TDEase Execution Runtime — programmatic entry point.

Called by the worker:
  preflight(commit) -> PreflightResult
  execute(commit) -> ExecutionResult
  cancel(run_id)   -> bool

preflight and execute share parse_snakefile from parser.py as the single parse entry point.
execute checks storage.check_cancelled(run_id) between tasks.
Error classification: TDEaseError passes through unchanged; unknown exceptions map to ENGINE_RUNTIME_INTERNAL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.contracts import RunCommit
from src.contracts.errors import ErrorCode, TDEaseError
from src.execution_runtime.engine_contract import WorkflowEngineRequest
from src.execution_runtime.engine_layout import cleanup_engine_alias
from src.execution_runtime.events import EventEmitter
from src.execution_runtime.parser import parse_snakefile
from src.execution_runtime.resource_budget import RESOURCE_BUDGET
from src.execution_runtime.snakemake_adapter import SnakemakeAdapter
from src.execution_runtime.storage import get_storage, get_tools_root


@dataclass
class PreflightResult:
    """preflight() return value — transient view model, not persisted."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    estimated_steps: int = 0
    missing_inputs: list[str] = field(default_factory=list)
    tools_required: list[str] = field(default_factory=list)
    step_labels: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """execute() return value."""
    success: bool
    exit_code: int | None = None
    error: TDEaseError | None = None
    run_time_seconds: float = 0.0
    total_tasks: int = 0
    succeeded_tasks: int = 0
    failed_tasks: int = 0
    final_seq: int = 0


# Shell builtins / constructs that never need PATH resolution: they exist as
# builtins or keywords in at least one supported execution shell (cmd.exe on
# Windows, POSIX sh elsewhere). POSIX-only EXTERNAL binaries (cp, mv, rm,
# grep, sed, ...) are deliberately absent — on Windows they would only fail
# at execution time, after minutes of compute. Leaving them out makes the
# which() check in preflight fail fast with that answer.
_SHELL_BUILTINS = frozenset({
    "echo", "python", "python3", "mkdir", "cd", "true", "false",
    "if", "then", "else", "elif", "fi", "for", "while", "do", "done",
    "case", "esac", "in", "export", "source", ".", "set", "unset",
    "exec", "find", "printf", "date", "time", "test", "[",
})
# Proteomics tools — checked against PATH; .exe stripped on Windows
_KNOWN_PROTEO_TOOLS = frozenset({
    "topfd", "toppic", "topindex", "topmg", "topdiff", "topdia",
    "msconvert",
})


def preflight(commit: RunCommit) -> PreflightResult:
    """
    Validate that a Run commit is executable.
    Uses parse_snakefile from parser.py as the single parse entry point.
    """
    errors: list[str] = []
    warnings: list[str] = []
    tools: set[str] = set()
    step_labels: list[str] = []

    try:
        wf = parse_snakefile(commit.snakefile, f"run:{commit.run_id}")
    except SyntaxError as e:
        return PreflightResult(valid=False, errors=[f"Syntax error: {e}"])
    except TDEaseError as e:
        return PreflightResult(valid=False, errors=[str(e)])

    unsupported: set[str] = set()

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
        # Snakemake placeholders (e.g. "{params.toppic_bin}") resolve at
        # runtime from node bindings; resolve_bindings validates those.
        if "{" in first:
            continue
        # Strip .exe suffix on Windows
        first_name = first.rsplit(".", 1)[0] if "." in first else first
        if first_name in _SHELL_BUILTINS or first_name in _KNOWN_PROTEO_TOOLS:
            continue
        tools.add(first)

    import shutil
    for tool in sorted(tools):
        if shutil.which(tool) is None and shutil.which(tool + ".exe") is None:
            errors.append(
                f"tool not found: {tool} (the execution shell is "
                f"cmd.exe on Windows — do file operations with a "
                f"'python -c' one-liner instead of POSIX commands)"
            )

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


def execute(
    commit: RunCommit,
    *,
    revision_id: str,
    execution_mode: str,
    rerun_mode: str = "resume",
) -> ExecutionResult:
    """
    Execute a Run commit.

    1. parse_snakefile (single parse entry point, shared with preflight)
    2. Popen-based task execution (streamed logs + cancel checks)
    3. Error classification: TDEaseError kept as-is; unknown exceptions map to ENGINE_RUNTIME_INTERNAL
    """
    storage = get_storage()
    run_id = commit.run_id

    # Idempotent — worker re-enters after API
    storage.allocate_run(run_id)

    emitter = EventEmitter(run_id)

    start = time.perf_counter()
    snakefile_path = storage.resolve(run_id, "Snakefile")
    storage.atomic_write(snakefile_path, commit.snakefile)

    # Snakemake is the DAG/runtime authority. TDEase supervises one process;
    # it must not reinterpret the Snakefile or execute rules itself.
    total, succeeded, failed = 1, 0, 0
    execution_root = storage.resolve(run_id)
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
    effective_rerun_mode = "overwrite" if rerun_mode == "overwrite" else "resume"
    # Tool binding: bound node packages stay in the Backend catalog; the engine
    # reaches them through absolute paths injected into config["nodes"]. Nothing
    # tool-related is ever written under the Run directory.
    from src.services.node_catalog import bound_node_paths, resolve_bindings

    node_paths = bound_node_paths(
        resolve_bindings(get_tools_root(), commit.nodes)
    )
    engine_request = WorkflowEngineRequest(
        mode="execute",
        snakefile="Snakefile",
        config={**commit.config, "nodes": node_paths} if node_paths else commit.config,
        cores=effective_cores,
        memory_mb=RESOURCE_BUDGET.compute_memory_mb,
        targets=commit.targets,
        rerun_mode=effective_rerun_mode,
        rerun_incomplete=True,
        retries=0,
        job_event_path=".tdease/job-events.jsonl",
    )
    adapter = SnakemakeAdapter(run_id, execution_root, storage, emitter)
    try:
        engine_result = adapter.execute(
            engine_request,
            revision_id=revision_id,
            execution_mode=execution_mode,
            timeout_seconds=7 * 24 * 60 * 60,
        )
    finally:
        cleanup_engine_alias(execution_root)
    if engine_result.cancelled or storage.check_cancelled(run_id):
        emitter.run_cancelled(revision_id, time.perf_counter() - start)
        return ExecutionResult(
            success=False,
            exit_code=engine_result.exit_code,
            error=TDEaseError(
                code=ErrorCode.ENGINE_CANCELLED,
                message=f"Execution cancelled: {run_id}",
                remedy="Resubmit the Run to start a fresh execution.",
                retryable=False,
                details={"run_id": run_id},
            ),
            run_time_seconds=time.perf_counter() - start, total_tasks=1,
            final_seq=emitter.last_seq)
    if engine_result.success:
        succeeded = 1
    else:
        failed = 1
        total_elapsed = time.perf_counter() - start
        error = TDEaseError(
            code=ErrorCode.ENGINE_TASK_FAILED,
            message=f"Task failed: engine (exit {engine_result.exit_code})",
            remedy="Inspect the engine log for the failed task's stderr, then fix and rerun.",
            retryable=False,
            details={"task_id": "engine", "exit_code": engine_result.exit_code,
                     "reason": engine_result.stderr_tail},
        )
        emitter.run_failed(revision_id, engine_result.exit_code, total_elapsed, str(error))
        return ExecutionResult(success=False, exit_code=engine_result.exit_code, error=error,
            run_time_seconds=total_elapsed, total_tasks=1, failed_tasks=1,
            final_seq=emitter.last_seq)

    # Success is finalized by the Worker only after local-input verification
    # and atomic Result Manifest publication. Emitting run.succeeded here would
    # create a terminal fact before the published outputs exist.
    total_elapsed = time.perf_counter() - start
    return ExecutionResult(
        success=True,
        exit_code=0,
        run_time_seconds=total_elapsed,
        total_tasks=total,
        succeeded_tasks=succeeded,
        failed_tasks=failed,
        final_seq=emitter.last_seq,
    )


def cancel(run_id: str) -> bool:
    """Mark a run as cancelled. The worker checks this flag between tasks and inside a task."""
    storage = get_storage()
    storage.mark_cancelled(run_id)
    return True
