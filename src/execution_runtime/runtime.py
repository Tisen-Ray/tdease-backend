"""
TDEase Execution Runtime — programmatic entry point.

Called by the worker:
  execute(commit) -> ExecutionResult
  cancel(run_id)   -> bool

Workflow validity belongs to the real engine (the Backend dry-run); there is no
client-side Snakefile parsing or static preflight here — WORKFLOW-RUN.md §3.
Error classification: TDEaseError passes through unchanged; unknown exceptions map to ENGINE_RUNTIME_INTERNAL.
"""

from __future__ import annotations

import time
from pathlib import Path
from dataclasses import dataclass, field

from src.contracts import RunCommit
from src.contracts.errors import ErrorCode, TDEaseError
from src.execution_runtime.engine_contract import WorkflowEngineRequest
from src.execution_runtime.engine_layout import cleanup_engine_alias
from src.execution_runtime.events import EventEmitter
from src.execution_runtime.resource_budget import RESOURCE_BUDGET
from src.execution_runtime.snakemake_adapter import SnakemakeAdapter
from src.execution_runtime.storage import get_storage


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


def _resolve_fleet(commit: RunCommit, storage) -> dict | None:
    """Turn a pinned placement into the engine's fleet dispatch section.

    Placement is resolved HERE, once, at execution time — the single seam
    the dry-run and the worker share. "local" and absent both mean the
    ordinary local executor. A pinned node that is not in the registry
    fails the Run (never a silent re-dispatch).
    """
    if commit.placement is None or commit.placement.node == "local":
        return None
    from src.services.node_registry import load_registry

    # The registry lives beside the catalog under the SAME data root the
    # storage owns (works for serve layouts and test layouts alike):
    # <data>/config/nodes.json
    registry_path = storage.data / "config" / "nodes.json"
    registry = load_registry(registry_path)
    entry = next(
        (n for n in registry["nodes"] if n["nodeId"] == commit.placement.node),
        None,
    )
    if entry is None:
        raise TDEaseError(
            code=ErrorCode.RUN_NODE_NOT_FOUND,
            message=(
                f"Pinned fleet node '{commit.placement.node}' is not in the "
                f"registry ({registry_path})"
            ),
            remedy="Enroll the node (POST /api/nodes/enroll) or fix the placement.",
            retryable=False,
        )
    executor_dir = Path(__file__).resolve().parents[3] / "tdease-node" / "executor"
    if not executor_dir.is_dir():
        raise TDEaseError(
            code=ErrorCode.ENGINE_RUNTIME_INTERNAL,
            message=f"tdease-node executor plugin directory missing: {executor_dir}",
            remedy="Check the tdease-node checkout next to the backend.",
            retryable=False,
        )
    tool_map = {
        str(rule): str(tool)
        for rule, tool in (commit.config.get("node_tool_map") or {}).items()
    }
    return {
        "endpoint": entry["url"].rstrip("/"),
        "token": entry.get("token"),
        "tool_map": tool_map,
        "executor_dir": str(executor_dir),
    }


def execute(
    commit: RunCommit,
    *,
    revision_id: str,
    execution_mode: str,
    rerun_mode: str = "resume",
) -> ExecutionResult:
    """
    Execute a Run commit.

    1. Write the frozen Snakefile into the Run directory
    2. Resolve node bindings into engine config (the shared binding seam)
    3. Supervise one engine process; TDEaseError kept as-is, unknown
       exceptions map to ENGINE_RUNTIME_INTERNAL

    Terminals on the engine paths append through run_commands.finish() --
    the command module is the only constructor of lifecycle run.* events
    (BACKEND-RUN-SERVICE.md §2.2), and its fold decides whether this
    execution is still the one that may be terminalized.
    """
    storage = get_storage()
    run_id = commit.run_id

    # Idempotent — worker re-enters after API
    storage.allocate_run(run_id)

    # Job/task/graph events only: lifecycle run.* events (terminals included)
    # belong to the command module (§2.2).
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
    from src.execution_runtime.bindings import engine_config
    from src.services.run_commands import get_run_commands

    fleet = _resolve_fleet(commit, storage)
    if fleet is not None:
        storage.append_runtime_record(
            run_id,
            "info",
            (
                f"placement: node={commit.placement.node} (pinned) "
                f"endpoint={fleet['endpoint']} tools={sorted(fleet['tool_map'].values())}"
            ),
            "engine",
        )

    engine_request = WorkflowEngineRequest(
        mode="execute",
        snakefile="Snakefile",
        config=engine_config(commit),
        cores=effective_cores,
        memory_mb=RESOURCE_BUDGET.compute_memory_mb,
        targets=commit.targets,
        rerun_mode=effective_rerun_mode,
        rerun_incomplete=True,
        retries=0,
        job_event_path=".tdease/job-events.jsonl",
        fleet=fleet,
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
        get_run_commands().finish(
            run_id, "cancelled", run_time_seconds=time.perf_counter() - start
        )
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
            run_time_seconds=time.perf_counter() - start,
            total_tasks=1,
        )
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
            details={
                "task_id": "engine",
                "exit_code": engine_result.exit_code,
                "reason": engine_result.stderr_tail,
            },
        )
        get_run_commands().finish(
            run_id,
            "failed",
            exit_code=engine_result.exit_code,
            run_time_seconds=total_elapsed,
            error_message=str(error),
        )
        return ExecutionResult(
            success=False,
            exit_code=engine_result.exit_code,
            error=error,
            run_time_seconds=total_elapsed,
            total_tasks=1,
            failed_tasks=1,
        )

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
    )


def cancel(run_id: str) -> bool:
    """Mark a run as cancelled. The worker checks this flag between tasks and inside a task."""
    storage = get_storage()
    storage.mark_cancelled(run_id)
    return True
