"""
Runs API v2 — SSE event stream + status queries.

The backend does exactly four things: accept commits, queue, execute, stream file events.
Pushed via SSE + Last-Event-ID.

All writes go through the Storage Layout (routes never open/write/mkdir directly).
"""

from __future__ import annotations

import asyncio
import logging
import json
import hashlib
import base64
import os
import sys
import fnmatch
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import FileResponse, PlainTextResponse, Response, StreamingResponse

from src.contracts import (
    ResultRef,
    RunCreateRequest,
    RunCreateResponse,
    RunDryRunRequest,
    RunDryRunResponse,
    RunActionResponse,
    RunListResponse,
    RunRerunRequest,
    RunResultEntry,
    RunResultsResponse,
    RunStatus,
    RunStatusResponse,
    RunTrashEntry,
    RunTrashListResponse,
    RunWorkflowGraphResponse,
    TERMINAL_STATUSES,
)
from src.execution_runtime.engine_contract import WorkflowEngineRequest
from src.execution_runtime.storage import get_storage, get_tools_root
from src.execution_runtime.resource_budget import RESOURCE_BUDGET
from src.execution_runtime.execution import run_captured_process
from src.execution_runtime.execution import backend_child_env
from src.services.node_catalog import (
    bound_node_paths,
    resolve_bindings,
)
from src.services.run_definition import freeze_definition

# Reuses the Backend's own startup-resolved capability document (frozen at import
# time in app/api/capabilities.py) to select a materialization strategy instead of
# reading TDEASE_DEPLOYMENT_MODE per request. See docs/spec/CAPABILITIES.md section 7
# ("Materialization selection rule (resolves 0.2)") and docs/STATUS.md.
from app.api.capabilities import _CAPABILITIES
from src.contracts.errors import ErrorCode, TDEaseError

router = APIRouter(prefix="/api/v2/runs", tags=["runs"])
logger = logging.getLogger(__name__)

LOCAL_WORKSPACE_HARDLINK = "local_workspace_hardlink"
BLOB_STORE = "blob_store"


def _index_run(data: dict, storage) -> None:
    index = None
    try:
        from src.services.run_index import get_run_index

        index = get_run_index()
        run_id = str(data.get("run_id", ""))
        index.upsert_run(data, storage.recover_seq(run_id))
        index.catch_up_run(storage, run_id)
    except Exception:
        if index is not None:
            index.mark_dirty()
        logger.exception("Run index update failed for %s", data.get("run_id"))


def _remove_indexed_run(run_id: str) -> None:
    index = None
    try:
        from src.services.run_index import get_run_index

        index = get_run_index()
        index.remove_run(run_id)
    except Exception:
        if index is not None:
            index.mark_dirty()
        logger.exception("Run index removal failed for %s", run_id)


def _indexed_files(run_id: str, revision_id: str) -> list[dict] | None:
    try:
        from src.services.run_index import get_run_index

        index = get_run_index()
        if index.is_dirty():
            index.reconcile(get_storage())
        return index.files_for_revision(run_id, revision_id)
    except Exception:
        logger.exception("Run file index query failed for %s:%s", run_id, revision_id)
        return None


def _read_text_verbatim(path: Path) -> str:
    """Read a Run file's exact text, with no newline translation.

    `Path.read_text()` opens in universal-newline mode: it turns CRLF into LF.
    The plan freezes the Snakefile's raw text (the Client reads the file's bytes
    as UTF-8), so a Snakefile written with Windows line endings — every copy
    made from a CRLF template, or saved by an editor that uses CRLF — would
    never equal the frozen text and every prepare/dry-run would fail with
    RUN_PLAN_STALE, deterministically and on every retry. Compare bytes to
    bytes instead.
    """
    return path.read_bytes().decode("utf-8")


def _snakefile_mismatch_detail(commit_text: str, file_text: str) -> str:
    """Say how the frozen text and the file on disk differ, in one line.

    A bare "the texts differ" is a black box: the caller cannot tell a real edit
    from a newline translation, and the incident of 2026-09-09 shows what that
    costs — a Run that "cannot be registered". Naming the difference (lengths,
    first divergence, or the newline case outright) turns the error into the
    diagnosis.
    """
    if commit_text.replace("\r\n", "\n") == file_text.replace("\r\n", "\n"):
        return (
            "the texts differ only in line endings "
            f"(commit {commit_text.count(chr(13) + chr(10))} CRLF line(s), "
            f"file {file_text.count(chr(13) + chr(10))} CRLF line(s))"
        )
    limit = min(len(commit_text), len(file_text))
    offset = next((i for i in range(limit) if commit_text[i] != file_text[i]), limit)
    line = commit_text.count("\n", 0, offset) + 1
    return (
        f"commit {len(commit_text)} chars, file {len(file_text)} chars; "
        f"first difference at char {offset} (line {line}): "
        f"commit {commit_text[offset:offset + 12]!r} vs file {file_text[offset:offset + 12]!r}"
    )


def _validate_compute_budget(cores: int) -> None:
    if cores > RESOURCE_BUDGET.compute_cpus:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message=(
                f"Run requests {cores} cores, but this Backend permits at most "
                f"{RESOURCE_BUDGET.compute_cpus}; "
                f"{RESOURCE_BUDGET.reserved_service_cpus} of "
                f"{RESOURCE_BUDGET.logical_cpus} logical CPUs are reserved for services."
            ),
            remedy="Lower commit.cores to GET /api/capabilities limits.max_cores and retry.",
            retryable=False,
        )


def _resolve_memory_budget(memory_mb: int | None) -> int:
    requested = memory_mb if memory_mb is not None else RESOURCE_BUDGET.compute_memory_mb
    if requested > RESOURCE_BUDGET.compute_memory_mb:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message=(
                f"Run requests {requested} MB, but this Backend permits at most "
                f"{RESOURCE_BUDGET.compute_memory_mb} MB; "
                f"{RESOURCE_BUDGET.reserved_service_memory_mb} MB of "
                f"{RESOURCE_BUDGET.total_memory_mb} MB is reserved for services."
            ),
            remedy="Lower commit.memory_mb to GET /api/capabilities limits.max_memory_mb and retry.",
            retryable=False,
        )
    return requested


def _schedule_commit(commit, user_id: str):
    """Apply the Backend-owned scheduling envelope to an accepted definition.

    Callers may describe a workflow, but they do not control process memory or
    the engine's parallelism ceiling. Snakemake schedules rule-level threads
    and resources inside this fixed Backend budget.
    """
    return commit.model_copy(update={
        "user_id": user_id,
        "cores": RESOURCE_BUDGET.compute_cpus,
        "memory_mb": RESOURCE_BUDGET.compute_memory_mb,
    })


async def _reject_removed_commit_fields(request: Request) -> None:
    """Reject commit fields that have left the Run surface, by name.

    Ignoring a removed field silently would be a mysterious behaviour change for
    a caller that still believes it controls that part of the definition; a
    caller must be told to stop sending it (docs/STATUS.md):
    - `local_workspace_root`: the Client absolute path; replaced by the opaque
      `local_root_id` capability.
    - `mode`: the caller-declared materialization choice; the Backend selects it
      from its own capabilities and records it.
    - `packages`: the pre-Node tool-lock list; a Run locks executables through
      `nodes` (id + content digest) only.

    Reads the already-buffered request body (Starlette caches it after FastAPI's own
    pydantic parsing), so this is not a second read of the wire and not an
    environment-variable read.
    """
    raw = await request.json()
    commit_raw = raw.get("commit") if isinstance(raw, dict) else None
    if not isinstance(commit_raw, dict):
        return
    if "local_workspace_root" in commit_raw:
        raise TDEaseError(
            code=ErrorCode.RUN_MODE_MISMATCH,
            message="the Run commit no longer accepts a Client absolute local_workspace_root",
            remedy="Attach the Workspace once, then submit local_root_id and local_run_path.",
            retryable=False,
        )
    if "mode" in commit_raw:
        raise TDEaseError(
            code=ErrorCode.RUN_MODE_MISMATCH,
            message="the Run commit no longer accepts a caller-declared 'mode' field",
            remedy=(
                "Remove 'mode' from the commit. The Backend selects the materialization "
                "strategy itself from GET /api/capabilities' materialization.strategies "
                "and records the chosen strategy on the Run."
            ),
            retryable=False,
        )
    if "packages" in commit_raw:
        raise TDEaseError(
            code=ErrorCode.RUN_MODE_MISMATCH,
            message="the Run commit no longer accepts a 'packages' field",
            remedy=(
                "Remove 'packages' from the commit. Executable identity is locked by "
                "'nodes' (node id + package digest), which is what the Backend resolves "
                "and executes."
            ),
            retryable=False,
        )


def _approved_local_run_root(commit) -> Path:
    """Resolve a local commit's Workspace root through the durable capability.

    Containment resolves against *this Principal's* approved Workspace roots
    (src.services.workspace_roots.is_within_approved_root), never a root the
    request itself asserts -- see
    src/execution_runtime/workspace_containment.py's module docstring.
    """
    from src.services.workspace_roots import get_workspace_root_registry

    root = get_workspace_root_registry().resolve(
        commit.user_id, commit.local_root_id, commit.local_run_path or "."
    )
    if root is None:
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_PATH_ESCAPE,
            message="Workspace root capability is missing, revoked, or the Run path escapes it.",
            remedy="Register the Workspace root with this Backend, then retry.",
            retryable=False,
        )
    return root


def _require_uploaded_blobs(storage, entries) -> None:
    """Submission check for the content-addressed strategy: the bytes must exist.

    Submission stores nothing in the run directory; the worker materializes the
    definition it starts, so the blobs must already be uploaded.
    """
    missing = sorted({entry.blob_hash for entry in entries if not storage.blob_exists(entry.blob_hash)})
    if missing:
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_BLOB_NOT_FOUND,
            message="Some workspace files are not present in the blob store.",
            remedy="Upload the missing blobs, then resubmit.",
            retryable=False,
            details={"missing_blobs": missing},
        )


def _snakefile_text_from_source(commit, storage, local_run_root) -> str:
    """The verbatim Snakefile the commit is defined over, read from its source.

    The frozen mapping names the file; this reads it where it actually lives --
    the Workspace file for a local Run, the content store for an uploaded one --
    so the agreement check does not depend on a materialized copy.
    """
    entry = next((item for item in commit.workspace_files if item.path == "Snakefile"), None)
    if entry is None:
        raise ValueError("The Run mapping does not contain its root Snakefile")
    if local_run_root is not None:
        return _read_text_verbatim(Path(local_run_root) / entry.path)
    return storage.blob_get(entry.blob_hash).decode("utf-8")


def _select_materialization_strategy(commit) -> str:
    """Resolve the materialization strategy for a commit from the Backend's own
    startup-resolved capabilities -- never from a caller-declared mode and never
    from an environment variable read at request time (docs/design/THREE-REPOSITORY-ARCHITECTURE.md;
    docs/spec/CAPABILITIES.md section 7).

    The strategy is derived from the commit's own shape: a Backend-issued `local_root_id`
    reference requests `local_workspace_hardlink`; content-addressed
    `workspace_files` alone request `blob_store`. A shape that requests a strategy
    absent from this Backend's resolved `materialization.strategies` is rejected
    with a `run`-domain error, never silently coerced to a different strategy.
    """
    requested = LOCAL_WORKSPACE_HARDLINK if commit.local_root_id else BLOB_STORE
    allowed = _CAPABILITIES.materialization.strategies
    if requested not in allowed:
        raise TDEaseError(
            code=ErrorCode.RUN_MODE_MISMATCH,
            message=(
                f"commit shape requests materialization strategy '{requested}', which "
                f"is not among this Backend's resolved capabilities {list(allowed)}"
            ),
            remedy=(
                "Match the commit shape (local_root_id vs. content-addressed "
                "workspace_files) to a strategy listed in GET /api/capabilities' "
                "materialization.strategies, or submit to a Backend that supports it."
            ),
            retryable=False,
        )
    return requested


def _is_same_workspace_run(existing: dict, commit) -> bool:
    """A Run id is the durable execution identity of one Workspace Run.

    Reusing that id is allowed only for a new immutable definition of the same
    Workspace directory. It must never turn an arbitrary id collision into a
    cross-workspace overwrite.
    """
    existing_path = existing.get("workspace_run_path") or existing.get("local_run_path")
    submitted_path = commit.workspace_run_path or commit.local_run_path
    return (
        existing.get("workspace_id") == commit.workspace_id
        and isinstance(existing_path, str)
        and existing_path == submitted_path
    )


def _is_owner(data: dict, request: Request) -> bool:
    """The single ownership predicate every Run route consults (docs/STATUS.md
    P0 "Resource authorization on read and mutate paths"). With today's single
    `local-owner` Principal this is always true -- that is the point: behaviour is
    unchanged today, but the enforcement point already exists everywhere a Run is
    read or mutated, before a second Principal or Server work ever arrives.
    """
    return data.get("user_id") == request.state.principal.user_id


def _owned_run(run_id: str, request: Request) -> dict:
    """FastAPI dependency: load `run_id`'s run.json and enforce `_is_owner`.

    Applied via `Depends()` on every route addressed by `run_id` below, rather than
    a copy-pasted `if` in each handler, so the enforcement point is one function. A
    Run that exists but is not owned by the caller is reported identically to a Run
    that does not exist (404): ownership must never be observable from response
    shape.
    """
    storage = get_storage()
    data = storage.read_json(storage.resolve(run_id, "run.json"))
    if not data or not _is_owner(data, request):
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_FOUND,
            message=f"Run {run_id} was not found.",
            remedy="Check the run_id, or list Runs with GET /api/v2/runs.",
            retryable=False,
        )
    return data


def _owned_trashed_run(run_id: str, request: Request) -> dict:
    """Same enforcement as `_owned_run`, for a Run currently in trash."""
    storage = get_storage()
    data = storage.read_json(storage.trash / "runs" / run_id / "run.json")
    if not data or not _is_owner(data, request):
        raise TDEaseError(
            code=ErrorCode.RUN_TRASH_NOT_FOUND,
            message=f"No trashed Run {run_id} was found.",
            remedy="List the trash with GET /api/v2/runs/trash to see what can be restored.",
            retryable=False,
        )
    return data


def _run_file(run_id: str, relative: str) -> Path:
    storage = get_storage()
    path = storage.resolve(run_id, relative).resolve(strict=False)
    root = storage.resolve(run_id).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_PATH_ESCAPE,
            message="The requested file path resolves outside the Run directory.",
            remedy="Request a path relative to the Run root, with no parent-directory segments.",
            retryable=False,
        ) from exc
    return path


def _actor(request: Request) -> str:
    source = request.headers.get("X-TDEase-Actor", "user").strip().lower()
    if source not in {"user", "ai"}:
        source = "user"
    return f"{source}:{request.state.principal.user_id}"


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def _run_status_value(run_id: str, storage) -> RunStatus:
    projection, _lifecycle = storage.project_run_snapshot(run_id)
    if projection.status is None:
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_FOUND,
            message=f"Run {run_id} has no submitted Journal entry.",
            remedy="Resubmit the Run definition.",
            retryable=False,
        )
    return RunStatus(projection.status)


def _run_status_response(data: dict, storage) -> RunStatusResponse:
    run_id = data.get("run_id", "")
    projection, lifecycle = storage.project_run_snapshot(run_id)
    status_value = lifecycle.get("status")
    if status_value is None:
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_FOUND,
            message=f"Run {run_id} has no submitted Journal entry.",
            remedy="Resubmit the Run definition.",
            retryable=False,
        )
    raw_labels = data.get("labels")
    labels: dict = raw_labels if isinstance(raw_labels, dict) else {}
    manifest = storage.read_json(storage.resolve(run_id, "results.manifest.json")) or {}
    raw_result_files = manifest.get("files")
    result_files: list = raw_result_files if isinstance(raw_result_files, list) else []
    process = storage.read_json(storage.resolve(run_id, ".runtime", "process.json")) or {}
    events = storage.read_events(run_id)
    queue_event = next(
        (event for event in reversed(events) if event.get("type") == "run.queue_requested"),
        None,
    )
    queue_data = queue_event.get("data") if isinstance(queue_event, dict) else {}
    if not isinstance(queue_data, dict):
        queue_data = {}
    active_range = next((item for item in reversed(projection.ranges) if item.is_open), None)
    strategy = data.get("materialization_strategy") or LOCAL_WORKSPACE_HARDLINK
    raw_rerun_mode = queue_data.get("rerun_mode")
    rerun_mode: Literal["resume", "overwrite"] = (
        raw_rerun_mode if raw_rerun_mode in ("resume", "overwrite") else "resume"
    )
    return RunStatusResponse(
        run_id=run_id,
        name=str(labels.get("name") or run_id),
        workspace_id=data.get("workspace_id", ""),
        workspace_run_path=data.get("workspace_run_path") or data.get("local_run_path"),
        # The execution definition exists from run.submitted onward. A results
        # manifest is only a terminal-success artifact, so it cannot be the
        # source for the live Run header's revision identity.
        current_revision=(
            manifest.get("revision_id")
            if status_value == RunStatus.SUCCEEDED.value and manifest.get("revision_id")
            else projection.current_revision_id
        ),
        active_revision=active_range.revision_id if active_range else None,
        queued_revision=projection.current_revision_id if projection.queued_at_seq is not None else None,
        execution_count=len(projection.ranges),
        status=RunStatus(status_value),
        materialization_strategy=strategy,
        cores=data.get("cores", 4),
        pid=process.get("engine_pid"),
        exit_code=lifecycle.get("exit_code"),
        error=lifecycle.get("error"),
        rerun_mode=rerun_mode,
        labels={str(key): str(value) for key, value in labels.items()},
        result_file_count=len(result_files),
        created_at=_parse_datetime(data.get("created_at")),
        started_at=_parse_datetime(lifecycle.get("started_at")) if lifecycle.get("started_at") else None,
        finished_at=_parse_datetime(lifecycle.get("finished_at")) if lifecycle.get("finished_at") else None,
        event_seq_last=storage.recover_seq(run_id),
    )


@router.post("/dry-run", response_model=RunDryRunResponse)
async def dry_run(payload: RunDryRunRequest, request: Request):
    """Validate an immutable client snapshot with the real workflow engine."""
    await _reject_removed_commit_fields(request)
    commit = _schedule_commit(payload.commit, request.state.principal.user_id)
    inline_blobs = payload.inline_blobs
    storage = get_storage()
    if not storage.claim_execution_slot():
        raise TDEaseError(
            code=ErrorCode.RUN_DRY_RUN_UNAVAILABLE,
            message="The Backend execution slot is busy with another Run or dry-run.",
            remedy="Wait for the current execution to finish, then retry the dry-run.",
            retryable=True,
        )
    try:
        return await asyncio.to_thread(_dry_run_with_slot, commit, inline_blobs, storage)
    finally:
        storage.release_execution_slot()


def _dry_run_with_slot(commit, inline_blobs: dict[str, str], storage):
    """Materialize and supervise one dry-run without blocking the API event loop."""
    if not commit.workspace_files:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message="A dry-run requires workspace_files: the immutable client file mapping.",
            remedy="Freeze the Workspace into workspace_files and resubmit the plan.",
            retryable=False,
        )
    strategy = _select_materialization_strategy(commit)
    try:
        resolved_nodes = resolve_bindings(get_tools_root(), commit.nodes)
    except ValueError as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message=f"The Run node bindings could not be resolved: {exc}",
            remedy="Correct the node bindings on the commit, or install the missing node package.",
            retryable=False,
        ) from exc
    with storage.temp_dir("dry-run", commit.run_id) as root:
        if strategy == LOCAL_WORKSPACE_HARDLINK:
            if not commit.local_root_id:
                raise TDEaseError(
                    code=ErrorCode.RUN_DRY_RUN_UNAVAILABLE,
                    message="local dry-run requires a Backend-issued local_root_id",
                    remedy="Attach the Workspace root, then submit its root_id and relative Run path.",
                    retryable=False,
                )
            workspace = _approved_local_run_root(commit)
            # The same materialization the worker uses for a real Run: control
            # files written, every other input sealed once into CAS and
            # hardlinked from there; no per-Run input copy is made.
            storage.materialize_local_run_files(root, workspace, commit.workspace_files, user_id=commit.user_id)
        else:
            missing = [entry.blob_hash for entry in commit.workspace_files
                       if not storage.blob_exists(entry.blob_hash) and entry.blob_hash not in inline_blobs]
            if missing:
                raise TDEaseError(
                    code=ErrorCode.WORKSPACE_BLOB_NOT_FOUND,
                    message="Some workspace files are not present in the blob store.",
                    remedy="Upload the missing blobs, or resubmit them inline as inline_blobs.",
                    retryable=False,
                    details={"missing_blobs": sorted(set(missing))},
                )
            for entry in commit.workspace_files:
                target = (root / entry.path).resolve(strict=False)
                try:
                    target.relative_to(root.resolve())
                except ValueError as exc:
                    raise TDEaseError(
                        code=ErrorCode.WORKSPACE_PATH_ESCAPE,
                        message=f"Workspace file {entry.path} resolves outside the Run snapshot.",
                        remedy="Use Workspace-relative paths with no parent-directory segments in workspace_files.",
                        retryable=False,
                    ) from exc
                if storage.blob_exists(entry.blob_hash):
                    content = storage.blob_get(entry.blob_hash)
                else:
                    try:
                        content = base64.b64decode(inline_blobs[entry.blob_hash], validate=True)
                    except (KeyError, ValueError) as exc:
                        raise TDEaseError(
                            code=ErrorCode.RUN_PLAN_INVALID,
                            message=f"Inline blob {entry.blob_hash} is missing or is not valid base64.",
                            remedy="Send each inline blob as standard base64 keyed by its sha256 digest.",
                            retryable=False,
                        ) from exc
                    if hashlib.sha256(content).hexdigest() != entry.blob_hash:
                        raise TDEaseError(
                            code=ErrorCode.WORKSPACE_DIGEST_MISMATCH,
                            message=f"Inline blob content does not hash to its declared digest {entry.blob_hash}.",
                            remedy="Recompute the sha256 of the file content and resubmit.",
                            retryable=False,
                        )
                storage.atomic_write(target, content)
        snake_entry = next((entry for entry in commit.workspace_files if entry.path == "Snakefile"), None)
        if snake_entry is None:
            raise TDEaseError(
                code=ErrorCode.RUN_PLAN_INVALID,
                message="The Run mapping does not contain its root Snakefile.",
                remedy="Create or complete runs/<run>/Snakefile, then prepare the Run again.",
                retryable=False,
            )
        snake_target = (root / snake_entry.path).resolve()
        snake_text = _read_text_verbatim(snake_target)
        if commit.snakefile != snake_text:
            raise TDEaseError(
                code=ErrorCode.RUN_PLAN_STALE,
                message=(
                    "The commit embedded snakefile differs from the mapped Run file: "
                    f"{_snakefile_mismatch_detail(commit.snakefile, snake_text)}."
                ),
                remedy=(
                    "Re-read runs/<run>/Snakefile and submit its current text "
                    "(the file changed since the plan froze it), then retry dry-run."
                ),
                retryable=False,
            )
        bound_paths = bound_node_paths(resolved_nodes)
        engine_request = WorkflowEngineRequest(
            mode="dry-run",
            snakefile="Snakefile",
            config={**commit.config, "nodes": bound_paths} if bound_paths else commit.config,
            cores=commit.cores,
            memory_mb=commit.memory_mb,
            targets=commit.targets,
            rerun_mode="resume",
            projection_path=".tdease/workflow-projection.json",
        )
        storage.atomic_write_json(
            root / ".tdease" / "engine-request.json",
            engine_request.model_dump(),
        )
        command = [sys.executable, "-m", "src.execution_runtime.engine_runner"]
        completed = run_captured_process(
            command,
            root,
            300,
            backend_child_env(),
        )
        output = completed.stdout + completed.stderr
        projection = storage.read_json(root / ".tdease" / "workflow-projection.json")
        return {"valid": completed.returncode == 0, "exit_code": completed.returncode,
                "engine": "tdease-workflow", "output": output[-200_000:],
                "projection": projection}


@router.post("", status_code=201, response_model=RunCreateResponse)
async def create_run(body: RunCreateRequest, request: Request):
    """Validate the request envelope, then perform durable submission off-loop."""
    await _reject_removed_commit_fields(request)
    return await asyncio.to_thread(_create_run, body, request)


def _create_run(body: RunCreateRequest, request: Request):
    """
    Submit a Run commit.

    Atomically writes run.json + initial events via the Storage Layout.
    """
    commit = _schedule_commit(body.commit, request.state.principal.user_id)
    storage = get_storage()

    # Idempotent allocation (creates dir if not exists)
    storage.allocate_run(commit.run_id)

    run_json = storage.resolve(commit.run_id, "run.json")

    # Check idempotency first. A fresh idempotency key for the same Workspace
    # Run is a new definition revision, not a second anonymous Backend Run.
    existing = storage.read_json(run_json)
    if existing and existing.get("idempotency_key") == commit.idempotency_key:
        _index_run(existing, storage)
        return RunCreateResponse(**_run_status_response(existing, storage).model_dump(), idempotent=True)
    if existing:
        if not _is_same_workspace_run(existing, commit):
            raise TDEaseError(
                code=ErrorCode.RUN_IDEMPOTENCY_CONFLICT,
                message=f"Idempotency key {commit.idempotency_key} already exists (run: {commit.run_id})",
                remedy="A Backend Run id belongs to one Workspace Run and cannot be reused elsewhere.",
                retryable=False,
            )
        # No status gates a new definition. A Run is always editable and always
        # continuable: the submission appends a new revision and a queue request
        # (the Journal accepts both from any status), and the worker materializes
        # the newest definition when it starts. If an execution is in flight, the
        # new definition is queued behind it; the finished execution keeps its own
        # journal range and results manifest, so provenance is recorded rather
        # than locked away.

    if not commit.workspace_files:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message="workspace_files is required: a Run commits an immutable client file mapping.",
            remedy="Freeze the Workspace into workspace_files and resubmit the commit.",
            retryable=False,
        )
    strategy = _select_materialization_strategy(commit)
    commit = commit.model_copy(update={"materialization_strategy": strategy})
    # Submission validates and seals the frozen mapping into shared CAS without
    # touching the Run directory. The worker later materializes links for the
    # definition it starts, so revisions share bytes without private copies.
    local_run_root = None
    try:
        resolve_bindings(get_tools_root(), commit.nodes)
        if strategy == LOCAL_WORKSPACE_HARDLINK:
            if not commit.local_root_id:
                raise ValueError("local_root_id is required for the local_workspace_hardlink strategy")
            local_run_root = _approved_local_run_root(commit)
            storage.verify_local_run_files(local_run_root, commit.workspace_files, user_id=commit.user_id)
            # Freeze local bytes now, once into shared CAS. The Run directory
            # remains untouched until the worker starts this exact revision.
            storage.seal_local_run_files(local_run_root, commit.workspace_files, user_id=commit.user_id)
        else:
            if commit.local_root_id or commit.local_run_path:
                raise ValueError("local root references are forbidden for the blob_store strategy")
            _require_uploaded_blobs(storage, commit.workspace_files)
    except (FileNotFoundError, ValueError) as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message=f"The Run definition could not be prepared: {exc}",
            remedy=(
                "Check that every workspace file is reachable, unchanged, and on the same "
                "volume as the Backend data root, then resubmit."
            ),
            retryable=False,
        ) from exc

    try:
        snake_entry = next((item for item in commit.workspace_files if item.path == "Snakefile"), None)
        if snake_entry is None:
            raise ValueError("The Run mapping does not contain its root Snakefile")
        snake_text = _snakefile_text_from_source(commit, storage, local_run_root)
        if commit.snakefile and commit.snakefile != snake_text:
            raise TDEaseError(
                code=ErrorCode.RUN_PLAN_STALE,
                message=(
                    "The commit embedded Snakefile differs from the mapped Run file: "
                    f"{_snakefile_mismatch_detail(commit.snakefile, snake_text)}."
                ),
                remedy=(
                    "Re-read runs/<run>/Snakefile and submit its current text "
                    "(the file changed since the plan froze it), then resubmit."
                ),
                retryable=False,
            )
    except TDEaseError:
        raise
    except (FileNotFoundError, ValueError) as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message=f"The Run workflow could not be prepared: {exc}",
            remedy="Create or complete runs/<run>/Snakefile, then prepare the Run again.",
            retryable=False,
        ) from exc

    # The Backend definition is immutable. Lifecycle belongs only to events.jsonl.
    run_data = commit.model_dump()
    run_data["snakefile"] = snake_text
    run_data = freeze_definition(run_data)
    if existing:
        # The row's creation time and user-facing title belong to the durable
        # Workspace Run, while every frozen definition gets its own journal
        # revision. Results from older successful definitions remain in
        # revisions/*.json and their content-addressed blobs.
        run_data["created_at"] = existing.get("created_at", run_data["created_at"])
        if not run_data.get("labels"):
            run_data["labels"] = existing.get("labels", {})
    # Definitions are immutable, small, and addressable by content digest.
    # They are deliberately separate from the shared execution tree: a new
    # revision never gets a second copy of intermediates or engine state.
    storage.write_definition_snapshot(commit.run_id, run_data)
    storage.atomic_write_json(run_json, run_data)

    # Establish the disposable list projection before publishing lifecycle
    # events. Event projection is asynchronous and may run immediately; without
    # this baseline row it observes a Run that the list index cannot identify.
    # The second call below catches the row up through the durable Journal
    # before the 201 response makes the Run externally visible.
    _index_run(run_data, storage)

    # Write initial event through storage (seq allocated by storage)
    from src.execution_runtime.events import EventEmitter
    emitter = EventEmitter(commit.run_id)
    revision_id = str(run_data["definition_revision_id"])
    emitter.run_submitted(
        revision_id,
        idempotency_key=commit.idempotency_key,
        workspace_tree_hash=commit.workspace_tree_hash,
        user_id=commit.user_id,
        cores=commit.cores,
        workflow_steps=0,
        actor=_actor(request),
    )
    emitter.run_queue_requested(
        revision_id,
        "execute",
        rerun_mode="resume",
        actor=_actor(request),
    )
    _index_run(run_data, storage)

    return RunCreateResponse(**_run_status_response(run_data, storage).model_dump(), idempotent=False)


@router.get("/trash", response_model=RunTrashListResponse)
def list_trashed_runs(request: Request):
    storage = get_storage()
    entries: list[RunTrashEntry] = []
    for directory in storage.trashed_run_dirs():
        data = storage.read_json(directory / "run.json") or {}
        if not _is_owner(data, request):
            continue
        metadata = storage.read_json(directory / ".tdease" / "trash.json") or {}
        raw_labels = data.get("labels")
        labels: dict = raw_labels if isinstance(raw_labels, dict) else {}
        entries.append(RunTrashEntry(
            run_id=data.get("run_id", directory.name),
            name=str(labels.get("name") or data.get("run_id") or directory.name),
            workspace_id=data.get("workspace_id", ""),
            previous_status=RunStatus(metadata.get("previous_status", data.get("status", "FAILED"))),
            deleted_at=_parse_datetime(metadata.get("deleted_at") or datetime.fromtimestamp(directory.stat().st_mtime, tz=timezone.utc)),
            deleted_by=str(metadata.get("deleted_by", "unknown")),
        ))
    entries.sort(key=lambda entry: (entry.deleted_at, entry.run_id), reverse=True)
    return RunTrashListResponse(runs=entries, total=len(entries))


@router.post("/trash/{run_id}/restore", response_model=RunStatusResponse)
def restore_run(run_id: str, request: Request, _owned: dict = Depends(_owned_trashed_run)):
    storage = get_storage()
    try:
        storage.restore_run(run_id)
    except FileNotFoundError as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_TRASH_NOT_FOUND,
            message=f"No trashed Run {run_id} was found.",
            remedy="List the trash with GET /api/v2/runs/trash to see what can be restored.",
            retryable=False,
        ) from exc
    except FileExistsError as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_IDEMPOTENCY_CONFLICT,
            message=f"A Run directory named {run_id} already exists, so the trashed one cannot be restored.",
            remedy="Trash or rename the live Run with that id first, then restore again.",
            retryable=False,
        ) from exc
    data = storage.read_json(storage.resolve(run_id, "run.json")) or {}
    from src.execution_runtime.events import EventEmitter
    EventEmitter(run_id).run_action("restore", _actor(request))
    _index_run(data, storage)
    index = None
    try:
        from src.services.run_index import get_run_index

        index = get_run_index()
        for manifest in storage.revision_manifests(run_id):
            index.replace_manifest(run_id, manifest)
    except Exception:
        if index is not None:
            index.mark_dirty()
        logger.exception("Run file index restore failed for %s", run_id)
    return _run_status_response(data, storage)


@router.delete("/trash/{run_id}", status_code=204)
def purge_trashed_run(
    run_id: str,
    request: Request,
    _owned: dict = Depends(_owned_trashed_run),
) -> Response:
    """Permanently remove a trashed Run and its rebuildable index projection."""
    storage = get_storage()
    storage.purge_trashed_run(run_id)
    _remove_indexed_run(run_id)
    return Response(status_code=204)


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str, data: dict = Depends(_owned_run)):
    """Query run status — projected from run.json + events.jsonl."""
    storage = get_storage()
    return _run_status_response(data, storage)


@router.get("/{run_id}/graph", response_model=RunWorkflowGraphResponse)
def get_run_graph(run_id: str, data: dict = Depends(_owned_run)):
    """Project the frozen dry-run DAG through persisted structured job events."""
    storage = get_storage()
    try:
        from src.services.run_index import get_run_index

        indexed = get_run_index().graph_projection(run_id)
        if indexed and indexed["projected_at_seq"] >= storage.recover_seq(run_id):
            statuses = {job["job_id"]: job["status"] for job in indexed["jobs"]}
            wildcards = {job["job_id"]: job["wildcards"] for job in indexed["jobs"]}
            if _run_status_value(run_id, storage) == RunStatus.CANCELLED:
                for node in indexed.get("nodes", []):
                    statuses.setdefault(node.get("id"), "cancelled")
            return {
                "run_id": run_id,
                "nodes": [
                    {
                        **node,
                        "status": statuses.get(
                            node.get("id"), node.get("initial_status", "waiting")
                        ),
                        "wildcards": wildcards.get(node.get("id"), {}),
                    }
                    for node in indexed.get("nodes", [])
                ],
                "edges": indexed.get("edges", []),
            }
    except Exception:
        # A locked, dirty, or rebuilding index is never allowed to delay graph
        # delivery. The immutable event log remains the authoritative fallback.
        pass
    projection = {"nodes": [], "edges": []}
    statuses: dict[int, str] = {}
    wildcards: dict[int, dict[str, str]] = {}
    event_status = {
        "job.started": "running",
        "job.succeeded": "succeeded",
        "job.failed": "failed",
    }
    for event in storage.read_events(run_id):
        if event.get("type") == "workflow.graph":
            payload = event.get("data") or {}
            projection = {"nodes": payload.get("nodes", []), "edges": payload.get("edges", [])}
            statuses.clear()
            wildcards.clear()
            continue
        status = event_status.get(str(event.get("type", "")))
        payload = event.get("data") or {}
        job_id = payload.get("job_id")
        if status and isinstance(job_id, int):
            statuses[job_id] = status
            if isinstance(payload.get("wildcards"), dict):
                wildcards[job_id] = {str(k): str(v) for k, v in payload["wildcards"].items()}
    if _run_status_value(run_id, storage) == RunStatus.CANCELLED:
        for node in projection.get("nodes", []):
            statuses.setdefault(node.get("id"), "cancelled")
    return {
        "run_id": run_id,
        "nodes": [
            {**node, "status": statuses.get(node.get("id"), node.get("initial_status", "waiting")),
             "wildcards": wildcards.get(node.get("id"), {})}
            for node in projection.get("nodes", [])
        ],
        "edges": projection.get("edges", []),
    }


@router.post("/{run_id}/rerun", response_model=RunActionResponse)
def rerun_run(run_id: str, body: RunRerunRequest, request: Request, data: dict = Depends(_owned_run)):
    """Queue the same Run in place, preserving its incremental engine state."""
    storage = get_storage()
    status = _run_status_value(run_id, storage)
    if status not in TERMINAL_STATUSES:
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_TERMINAL,
            message=f"Run {run_id} is {status.value}; only a terminal Run can be rerun.",
            remedy="Wait for the Run to finish, or cancel it before rerunning.",
            retryable=False,
        )

    storage.clear_cancelled(run_id)
    storage.release_claim(run_id)
    storage.resolve(run_id, "results.manifest.json").unlink(missing_ok=True)
    from src.execution_runtime.events import EventEmitter
    EventEmitter(run_id).run_queue_requested(
        str(data["definition_revision_id"]),
        "continue",
        rerun_mode=body.mode,
        actor=_actor(request),
    )
    EventEmitter(run_id).run_action("rerun", _actor(request), mode=body.mode)
    _index_run(data, storage)
    return RunActionResponse(
        run_id=run_id,
        status=RunStatus.QUEUED,
        action="rerun",
        mode=body.mode,
    )


@router.post("/{run_id}/trash", response_model=RunTrashEntry)
def trash_run(run_id: str, request: Request, data: dict = Depends(_owned_run)):
    storage = get_storage()
    status = _run_status_value(run_id, storage)
    if status not in TERMINAL_STATUSES:
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_TERMINAL,
            message=f"Run {run_id} is {status.value}; only a terminal Run can be moved to trash.",
            remedy="Wait for the Run to finish, or cancel it first.",
            retryable=False,
        )
    deleted_at = datetime.now(timezone.utc)
    deleted_by = _actor(request)
    raw_labels = data.get("labels")
    labels: dict = raw_labels if isinstance(raw_labels, dict) else {}
    from src.execution_runtime.events import EventEmitter
    EventEmitter(run_id).run_action("trash", deleted_by)
    try:
        storage.trash_run(run_id, {
            "schema_version": 1,
            "run_id": run_id,
            "previous_status": status.value,
            "deleted_at": deleted_at.isoformat(),
            "deleted_by": deleted_by,
        })
        _remove_indexed_run(run_id)
    except FileExistsError as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_IDEMPOTENCY_CONFLICT,
            message=f"A trash entry for {run_id} already exists.",
            remedy="Restore or purge the existing trash entry before trashing this Run again.",
            retryable=False,
        ) from exc
    return RunTrashEntry(
        run_id=run_id,
        name=str(labels.get("name") or run_id),
        workspace_id=data.get("workspace_id", ""),
        previous_status=status,
        deleted_at=deleted_at,
        deleted_by=deleted_by,
    )


@router.get("/{run_id}/results", response_model=RunResultsResponse)
def list_run_results(run_id: str, data: dict = Depends(_owned_run)):
    """Published Result projection: join `result_specs` against what actually
    materialized (docs/spec/WORKFLOW-RUN.md; docs/design/CORE-ARCHITECTURE.md 3).

    Readiness is a join, not a state: a declared spec whose `output` is not yet a
    file on disk projects `status="declared"` -- it is reported, never silently
    omitted. A spec whose `output` exists projects `status="ready"` with the
    current digest. Any file under `results/` that no spec declares never appears
    here; it stays a Technical Artifact, reachable only through
    `GET /api/v2/runs/{run_id}/files`.

    The declared specs belong to the definition the current results manifest
    names -- the last SUCCESSFUL execution -- not to the latest pointer in
    run.json. A new definition submitted while no newer result exists must not
    lend its spec list to files an older execution produced.
    """
    storage = get_storage()
    workspace_id = data.get("workspace_id", "")
    current_manifest = storage.read_json(storage.resolve(run_id, "results.manifest.json")) or {}
    revision_id = current_manifest.get("revision_id")
    definition_revision_id = current_manifest.get("definition_revision_id")
    published_definition = (
        storage.read_definition_snapshot(run_id, str(definition_revision_id))
        if isinstance(definition_revision_id, str) else None
    ) or data
    specs = published_definition.get("result_specs") or []
    if not specs:
        # The agent does not classify or select outputs. When a workflow has
        # no optional product metadata, its Snakemake default targets are the
        # authoritative publish set and receive a neutral file projection.
        specs = [
            {
                "result_id": f"output-{hashlib.sha256(output.encode('utf-8')).hexdigest()[:20]}",
                "name": Path(output).name,
                "kind": "workflow_output",
                "dimensions": {},
                "output": output,
            }
            for output in storage._declared_output_files_from_data(published_definition)
        ]
    indexed = _indexed_files(run_id, revision_id) if isinstance(revision_id, str) else None
    indexed_by_path = {
        entry["path"]: entry for entry in (indexed or [])
        if entry.get("role") == "result" and isinstance(entry.get("path"), str)
    }
    if not indexed_by_path and isinstance(current_manifest, dict):
        indexed_by_path = {
            entry["path"]: entry
            for entry in current_manifest.get("files", [])
            if isinstance(entry, dict) and isinstance(entry.get("path"), str)
        }
    results: list[RunResultEntry] = []
    for spec in specs:
        result_id = spec.get("result_id", "")
        output = spec.get("output", "")
        path = _run_file(run_id, output)
        digest: Optional[str] = None
        size: Optional[int] = None
        status = "declared"
        published_entry = indexed_by_path.get(output)
        if published_entry is not None and isinstance(published_entry.get("sha256"), str):
            # Published results are content-addressed. Their Run-relative
            # path belongs to the shared execution tree and may be replaced or
            # removed by a later revision without invalidating the old result.
            blob = storage.blob_path(str(published_entry["sha256"]))
            if blob.is_file():
                status = "ready"
                digest = str(published_entry["sha256"])
                size = int(published_entry.get("size", blob.stat().st_size))
        elif not current_manifest and path.is_file():
            # Pre-publication/legacy projection: an active execution can still
            # expose a materialized declared output before its manifest exists.
            status = "ready"
            digest = storage.file_digest(path)
            size = path.stat().st_size
        results.append(RunResultEntry(
            result_id=result_id,
            name=spec.get("name", ""),
            kind=spec.get("kind", ""),
            dimensions=spec.get("dimensions") or {},
            output=output,
            status=status,
            digest=digest,
            size=size,
            ref=ResultRef(workspace_id=workspace_id, run_id=run_id, result_id=result_id, digest=digest),
        ))
    return RunResultsResponse(
        run_id=run_id,
        results=results,
        definition_revision_id=(
            str(definition_revision_id) if isinstance(definition_revision_id, str) else None
        ),
    )


@router.get("/{run_id}/files")
def list_run_files(
    run_id: str,
    pattern: str = Query("results/**"),
    revision: Optional[str] = Query(None),
    include_workflow: bool = Query(False),
    data: dict = Depends(_owned_run),
):
    """Return a hash-addressed manifest for pull/fetch and AI discovery.

    `pattern` is caller-controlled and fed to `Path.glob`, which honours a
    literal `..` path segment; `Path.relative_to` on an *unresolved* glob
    result is a lexical string-prefix check, not a containment check, so a
    pattern like `"../<other-run>/**"` would otherwise walk straight past
    this route's own `Depends(_owned_run)` and list another Principal's Run
    (or arbitrary Backend data, e.g. `"../../database/*"`). Every candidate
    is therefore resolved (`strict=False`) and re-checked for containment
    under the *resolved* run root -- the same resolve-then-contain pattern
    `_run_file` already uses for single-file downloads -- before it is
    trusted, and a literal `..` segment in `pattern` itself is rejected
    up front as defense in depth.
    """
    if any(part == ".." for part in pattern.replace("\\", "/").split("/")):
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_PATH_ESCAPE,
            message="The glob pattern must not contain parent-directory segments.",
            remedy="Use a pattern relative to the Run root, such as results/**.",
            retryable=False,
        )
    root = get_storage().resolve(run_id)
    if not root.is_dir():
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_FOUND,
            message=f"Run {run_id} was not found.",
            remedy="Check the run_id, or list Runs with GET /api/v2/runs.",
            retryable=False,
        )
    resolved_root = root.resolve()
    storage = get_storage()
    if revision:
        manifest = storage.revision_manifest(run_id, revision)
        if manifest is None:
            raise TDEaseError(
                code=ErrorCode.RUN_FILE_NOT_FOUND,
                message=f"Run {run_id} has no retained revision {revision}.",
                remedy="List retained revisions with GET /api/v2/runs/<run_id>/revisions.",
                retryable=False,
            )
        raw_result_entries = manifest.get("files")
        result_entries: list = raw_result_entries if isinstance(raw_result_entries, list) else []
        raw_workflow_entries = manifest.get("workflow_files")
        workflow_entries: list = raw_workflow_entries if isinstance(raw_workflow_entries, list) else []
        entries = [
            *({**entry, "role": "result"} for entry in result_entries if isinstance(entry, dict)),
            *({**entry, "role": "workflow"} for entry in workflow_entries if include_workflow and isinstance(entry, dict)),
        ]
        files = [
            entry for entry in entries
            if isinstance(entry.get("path"), str)
            and (pattern == "results/**" or fnmatch.fnmatch(entry["path"], pattern))
        ]
        return {"run_id": run_id, "revision_id": revision, "files": files}

    current_manifest = storage.read_json(storage.resolve(run_id, "results.manifest.json")) or {}
    current_revision = current_manifest.get("revision_id")
    # Once a result manifest exists, it is the last published snapshot even if
    # a newer definition is queued/running/failed. Do not fall back to the
    # shared Run tree: a later revision is allowed to reuse and rewrite those
    # physical paths, but must not rewrite the older revision's observation.
    if isinstance(current_revision, str) and current_manifest.get("files"):
        indexed = _indexed_files(run_id, current_revision)
        if indexed is None:
            indexed = [
                {**entry, "role": "result"}
                for entry in current_manifest.get("files", [])
                if isinstance(entry, dict)
            ] + [
                {**entry, "role": "workflow"}
                for entry in current_manifest.get("workflow_files", [])
                if isinstance(entry, dict)
            ]
        files = [
            {
                "path": entry["path"],
                "size": entry["size"],
                "sha256": entry["sha256"],
                "role": entry["role"],
            }
            for entry in indexed
            if (include_workflow or entry.get("role") == "result")
            and (
                pattern == "results/**"
                or fnmatch.fnmatch(str(entry.get("path", "")), pattern)
            )
        ]
        return {"run_id": run_id, "revision_id": current_revision, "files": files}

    files = []
    seen: set[str] = set()

    def add(resolved: Path) -> None:
        try:
            rel = resolved.relative_to(resolved_root).as_posix()
        except ValueError:
            return
        if rel.startswith((".runtime/", ".tdease/", ".snakemake/", "revisions/")) or rel in seen:
            return
        seen.add(rel)
        files.append({"path": rel, "size": resolved.stat().st_size, "sha256": storage.file_digest(resolved)})

    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        add(path.resolve(strict=False))

    # A flat-layout template names its outputs in `rule all`, at the run root rather
    # than under results/. The default discovery pattern would then report files:[]
    # for a run whose declared outputs all sit at the root -- a SUCCEEDED run
    # indistinguishable from one that produced nothing. Only under the default pattern (an explicit
    # caller pattern is honoured verbatim), also surface the declared outputs that
    # actually materialized so the default view is never silently empty over real
    # products.
    if pattern == "results/**":
        manifest = storage.read_json(storage.resolve(run_id, "results.manifest.json")) or {}
        for entry in manifest.get("files", []):
            rel = entry.get("path") if isinstance(entry, dict) else None
            if not isinstance(rel, str):
                continue
            try:
                artifact = _run_file(run_id, rel)
            except TDEaseError:
                continue
            if artifact.is_file() and rel not in seen:
                seen.add(rel)
                files.append({
                    "path": rel,
                    "size": entry.get("size", artifact.stat().st_size),
                    "sha256": entry.get("sha256") or storage.file_digest(artifact),
                })

        # A manifest is finalized only after terminal success. While a Run is
        # active, expose its current execution outputs without hashing files
        # that are still growing. Submitted inputs and Backend-private state
        # stay hidden; terminal responses are replaced by the verified manifest.
        if not manifest.get("files"):
            run_data = storage.read_json(storage.resolve(run_id, "run.json")) or {}
            submitted = {
                item.get("path") for item in (run_data.get("workspace_files") or [])
                if isinstance(item, dict) and isinstance(item.get("path"), str)
            }
            for candidate in root.rglob("*"):
                if not candidate.is_file():
                    continue
                rel = candidate.relative_to(root).as_posix()
                if rel in submitted or rel in {"run.json", "events.jsonl", "results.manifest.json"}:
                    continue
                if rel.startswith((".runtime/", ".tdease/", ".snakemake/", "nodes/", "logs/", "revisions/")):
                    continue
                if any(part.endswith("_idx") for part in Path(rel).parts):
                    continue
                if rel in seen:
                    continue
                seen.add(rel)
                files.append({
                    "path": rel,
                    "size": candidate.stat().st_size,
                    "sha256": None,
                })
        for rel in storage.declared_output_files(run_id):
            try:
                declared = _run_file(run_id, rel)
            except TDEaseError:
                continue  # a declared path that will not resolve is simply not listed
            if declared.is_file():
                add(declared.resolve(strict=False))

    files.sort(key=lambda entry: entry["path"])
    return {"run_id": run_id, "files": files}


@router.get("/{run_id}/files/{file_path:path}")
def download_run_file(
    run_id: str,
    file_path: str,
    revision: Optional[str] = Query(None),
    data: dict = Depends(_owned_run),
):
    """Stream one run snapshot/result file; Starlette provides HTTP Range support."""
    storage = get_storage()
    if revision:
        manifest = storage.revision_manifest(run_id, revision)
        entries = [
            *(manifest.get("files", []) if manifest else []),
            *(manifest.get("workflow_files", []) if manifest else []),
        ]
        entry = next(
            (item for item in entries if isinstance(item, dict) and item.get("path") == file_path),
            None,
        )
        if entry is None:
            raise TDEaseError(
                code=ErrorCode.RUN_FILE_NOT_FOUND,
                message=f"Revision {revision} has no readable file at {file_path}.",
                remedy="List the revision files before requesting an exact path.",
                retryable=False,
            )
        try:
            path = storage.blob_path(str(entry.get("sha256", "")))
        except ValueError:
            path = Path()
        if not path.is_file():
            raise TDEaseError(
                code=ErrorCode.RUN_FILE_NOT_FOUND,
                message=f"The retained bytes for {revision}:{file_path} are unavailable.",
                remedy="Check the Backend retention policy and revision manifest integrity.",
                retryable=False,
            )
        digest = str(entry["sha256"])
        return FileResponse(path, filename=Path(file_path).name, headers={"ETag": f'"sha256-{digest}"'})

    # The no-query form means "the last published value", not "whatever bytes
    # currently happen to occupy this shared Run path". A later revision may
    # reuse that path while the older result is still the public current result.
    current_manifest = storage.read_json(storage.resolve(run_id, "results.manifest.json")) or {}
    current_entries = [
        *(current_manifest.get("files", []) if isinstance(current_manifest, dict) else []),
        *(current_manifest.get("workflow_files", []) if isinstance(current_manifest, dict) else []),
    ]
    published = next(
        (item for item in current_entries
         if isinstance(item, dict) and item.get("path") == file_path),
        None,
    )
    if published is not None:
        digest = str(published.get("sha256", ""))
        try:
            path = storage.blob_path(digest)
        except ValueError:
            path = Path()
        if not path.is_file():
            raise TDEaseError(
                code=ErrorCode.RUN_FILE_NOT_FOUND,
                message=f"The retained bytes for {file_path} are unavailable.",
                remedy="Check the Backend retention policy and revision manifest integrity.",
                retryable=False,
            )
        return FileResponse(path, filename=Path(file_path).name, headers={"ETag": f'"sha256-{digest}"'})

    path = _run_file(run_id, file_path)
    if not path.is_file() or file_path.startswith((".runtime/", ".tdease/", ".snakemake/", "revisions/")):
        raise TDEaseError(
            code=ErrorCode.RUN_FILE_NOT_FOUND,
            message=f"Run {run_id} has no readable file at {file_path}.",
            remedy="List the Run files with GET /api/v2/runs/<run_id>/files.",
            retryable=False,
        )
    digest = None
    current_revision = current_manifest.get("revision_id")
    if _run_status_value(run_id, storage) == RunStatus.SUCCEEDED and isinstance(current_revision, str):
        indexed = _indexed_files(run_id, current_revision)
        indexed_entry = next(
            (entry for entry in (indexed or []) if entry.get("path") == file_path),
            None,
        )
        if indexed_entry:
            digest = str(indexed_entry.get("sha256", "")) or None
    digest = digest or get_storage().file_digest(path)
    return FileResponse(path, filename=path.name, headers={"ETag": f'"sha256-{digest}"'})


@router.get("/{run_id}/revisions")
def list_run_revisions(run_id: str, _owned: dict = Depends(_owned_run)):
    revisions = []
    for manifest in get_storage().revision_manifests(run_id):
        raw_files = manifest.get("files")
        files: list = raw_files if isinstance(raw_files, list) else []
        raw_workflow_files = manifest.get("workflow_files")
        workflow_files: list = raw_workflow_files if isinstance(raw_workflow_files, list) else []
        revisions.append({
            "revision_id": manifest.get("revision_id"),
            "parent_revision_id": manifest.get("parent_revision_id"),
            "created_at": manifest.get("created_at"),
            "file_count": len(files),
            "workflow_file_count": len(workflow_files),
        })
    return {"run_id": run_id, "revisions": revisions}


@router.get("/{run_id}/definitions")
def list_run_definitions(run_id: str, _owned: dict = Depends(_owned_run)):
    """List immutable submitted definitions, including definitions that failed.

    Result revisions are a separate projection: they exist only after a
    successful execution. A definition is still a real revision when dry-run
    or materialization fails, so it must not disappear from Run history.
    """
    storage = get_storage()
    manifests = storage.revision_manifests(run_id)
    projection, _snapshot = storage.project_run_snapshot(run_id)
    terminal_by_definition: dict[str, dict] = {}
    for execution in projection.ranges:
        if execution.terminal_type is None:
            status = "RUNNING"
        else:
            status = {
                "run.succeeded": "SUCCEEDED",
                "run.failed": "FAILED",
                "run.cancelled": "CANCELLED",
            }.get(execution.terminal_type)
        if status:
            terminal_by_definition[execution.revision_id] = {
                "status": status,
                "result_revision_id": next(
                    (item.get("revision_id") for item in manifests
                     if item.get("definition_revision_id") == execution.revision_id),
                    None,
                ),
            }
    definitions = []
    for definition in storage.definition_snapshots(run_id):
        definition_id = definition.get("definition_revision_id")
        if not isinstance(definition_id, str):
            continue
        manifest = next(
            (item for item in manifests if item.get("definition_revision_id") == definition_id),
            None,
        )
        details = terminal_by_definition.get(definition_id, {})
        if not details and projection.current_revision_id == definition_id and projection.queued_at_seq is not None:
            details = {"status": "QUEUED", "result_revision_id": None}
        files = manifest.get("files", []) if isinstance(manifest, dict) else []
        workflow_files = manifest.get("workflow_files", []) if isinstance(manifest, dict) else []
        definitions.append({
            "definition_revision_id": definition_id,
            "created_at": definition.get("created_at"),
            "workspace_tree_hash": definition.get("workspace_tree_hash"),
            "status": details.get("status"),
            "result_revision_id": details.get("result_revision_id"),
            "file_count": len(files) if isinstance(files, list) else 0,
            "workflow_file_count": len(workflow_files) if isinstance(workflow_files, list) else 0,
        })
    return {"run_id": run_id, "definitions": definitions}


@router.get("/{run_id}/definitions/{definition_revision_id}")
def get_run_definition(run_id: str, definition_revision_id: str, _owned: dict = Depends(_owned_run)):
    """Read one frozen definition in full -- the exact Snakefile text, config,
    node digests and input manifest that THIS revision ran (or will run).

    This is the self-correction channel: an Agent diffs what it is about to
    change against what an earlier revision actually executed, instead of
    reconstructing history from memory. Content-addressed and immutable.
    """
    import re as _re

    if not _re.fullmatch(r"def-[a-f0-9]{24}", definition_revision_id):
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_FOUND,
            message=f"Invalid definition revision id: {definition_revision_id}",
            remedy="List definitions with GET /api/v2/runs/{run_id}/definitions.",
            retryable=False,
        )
    storage = get_storage()
    definition = storage.read_definition_snapshot(run_id, definition_revision_id)
    if definition is None:
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_FOUND,
            message=f"No definition {definition_revision_id} for run {run_id}.",
            remedy="List definitions with GET /api/v2/runs/{run_id}/definitions.",
            retryable=False,
        )
    return {
        "run_id": run_id,
        "definition_revision_id": definition_revision_id,
        "created_at": definition.get("created_at"),
        "workspace_tree_hash": definition.get("workspace_tree_hash"),
        "snakefile": definition.get("snakefile", ""),
        "config": definition.get("config", {}),
        "nodes": definition.get("nodes", []),
        "targets": definition.get("targets", []),
        "result_specs": definition.get("result_specs", []),
        "workspace_files": definition.get("workspace_files", []),
    }


@router.get("/{run_id}/log")
def get_run_log(run_id: str, tail: int = Query(200, ge=1, le=10000), _owned: dict = Depends(_owned_run)):
    # The worker section comes first: a Run that died BEFORE the engine
    # (materialize, digest gates, capability) has no engine logs at all, and
    # without this source the log surface would read empty -- the failure
    # stage would be invisible to the Agent.
    paths = [
        _run_file(run_id, "logs/tasks/worker.log"),
        _run_file(run_id, "logs/tasks/engine.stdout.log"),
        _run_file(run_id, "logs/tasks/engine.stderr.log"),
    ]
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return PlainTextResponse("")
    lines: list[str] = []
    for path in existing:
        lines.extend(get_storage().tail_text_lines(path, tail))
    return PlainTextResponse("\n".join(lines[-tail:]) + ("\n" if lines else ""))


@router.get("/{run_id}/events")
async def get_events_sse(
    run_id: str, request: Request,
    last_event_id: Optional[int] = Query(default=None, alias="last_event_id"),
    _owned: dict = Depends(_owned_run),
):
    """SSE event stream — tail of events.jsonl to SSE. Last-Event-ID resumes the stream."""
    storage = get_storage()

    async def event_generator():
        # Query param takes precedence; otherwise read the standard SSE Last-Event-ID header
        cursor = last_event_id
        if cursor is None:
            header_val = request.headers.get("Last-Event-ID")
            if header_val is not None:
                try:
                    cursor = int(header_val)
                except (ValueError, TypeError):
                    cursor = 0
        sent_seq = cursor or 0
        file_offset = await asyncio.to_thread(
            storage.event_offset_after_seq, run_id, sent_seq
        )

        while True:
            if await request.is_disconnected():
                break
            event_lines, file_offset = await asyncio.to_thread(
                storage.read_event_lines_from, run_id, file_offset
            )
            for evt, line in event_lines:
                if evt.get("seq", 0) > sent_seq:
                    yield f"id: {evt['seq']}\ndata: {line}\n\n"
                    sent_seq = evt["seq"]
            projection, _snapshot = await asyncio.to_thread(
                storage.project_run_snapshot, run_id
            )
            if projection.status in ("SUCCEEDED", "FAILED", "CANCELLED"):
                # The Worker can append the terminal event after this loop's
                # incremental read but before the projection snapshot. Never
                # let `done` overtake journal bytes the snapshot has already
                # observed; immediately drain from the current byte offset.
                if sent_seq < projection.projected_at_seq:
                    continue
                payload = json.dumps(
                    {
                        "status": projection.status,
                        "last_event_id": sent_seq,
                    },
                    separators=(",", ":"),
                )
                yield f"event: done\ndata: {payload}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=RunListResponse)
def list_runs(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: Optional[str] = None,
    status: list[RunStatus] | None = Query(default=None),
    query: Optional[str] = Query(default=None, min_length=1, max_length=200),
):
    """List owned Runs through the rebuildable index, with filesystem fallback."""
    storage = get_storage()
    runs_dir = storage.data / "runs"
    if not runs_dir.exists():
        return RunListResponse(runs=[], total=0, offset=offset, limit=limit, has_more=False)

    try:
        from src.services.run_index import get_run_index

        index = get_run_index()
        if index.is_dirty():
            index.reconcile(storage)
        run_ids, total = index.list_run_ids(
            request.state.principal.user_id, offset, limit, workspace_id,
            [item.value for item in status] if status else None, query,
        )
        page = []
        for run_id in run_ids:
            data = storage.read_json(storage.resolve(run_id, "run.json"))
            if not data or not _is_owner(data, request):
                raise RuntimeError(f"stale Run index row: {run_id}")
            page.append(data)
        runs = [_run_status_response(run, storage) for run in page]
        return RunListResponse(
            runs=runs, total=total, offset=offset, limit=limit,
            has_more=offset + len(runs) < total,
        )
    except Exception:
        logger.exception("Run index query failed; scanning filesystem truth")

    all_runs = []
    for rd in sorted(runs_dir.iterdir(), reverse=True):
        if not rd.is_dir():
            continue
        data = storage.read_json(rd / "run.json")
        if not data:
            continue
        if not _is_owner(data, request):
            continue
        if workspace_id and data.get("workspace_id") != workspace_id:
            continue
        if status:
            try:
                if _run_status_value(str(data.get("run_id", rd.name)), storage) not in status:
                    continue
            except TDEaseError:
                continue
        if query:
            raw_labels = data.get("labels")
            labels: dict = raw_labels if isinstance(raw_labels, dict) else {}
            haystack = " ".join([
                str(data.get("run_id", "")),
                str(data.get("workspace_id", "")),
                *(str(value) for value in labels.values()),
            ]).lower()
            if query.lower() not in haystack:
                continue
        all_runs.append(data)

    all_runs.sort(
        key=lambda item: (_parse_datetime(item.get("created_at")), str(item.get("run_id", ""))),
        reverse=True,
    )

    total = len(all_runs)
    page = all_runs[offset:offset + limit]

    runs = [_run_status_response(run, storage) for run in page]
    return RunListResponse(
        runs=runs,
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + len(runs) < total,
    )


@router.post("/{run_id}/cancel", response_model=RunActionResponse)
def cancel_run(run_id: str, request: Request, data: dict = Depends(_owned_run)):
    """Cancel a run — writes the cancel flag through the Storage Layout."""
    storage = get_storage()
    status = _run_status_value(run_id, storage)
    if status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_QUEUED,
            message=f"Run {run_id} is {status.value} and cannot be cancelled",
            remedy="Only a queued or running Run can be cancelled.",
            retryable=False,
        )

    # Write cancel marker naming the execution it targets — the worker's task
    # loop checks it, and a later execution must be able to tell that an older
    # flag is not aimed at it.
    projection, _snapshot = storage.project_run_snapshot(run_id)
    open_range = next((item for item in reversed(projection.ranges) if item.is_open), None)
    target_seq = open_range.queue_seq if status == RunStatus.RUNNING and open_range else projection.queued_at_seq
    storage.mark_cancelled(run_id, target_seq)
    from src.execution_runtime.events import EventEmitter
    EventEmitter(run_id).run_action("cancel", _actor(request), previous_status=status.value)

    # Dequeue: mark CANCELLED if still QUEUED (not yet claimed)
    response_status = status
    if status == RunStatus.QUEUED:
        EventEmitter(run_id).run_cancelled(str(data["definition_revision_id"]))
        response_status = RunStatus.CANCELLED
        _index_run(data, storage)

    return RunActionResponse(
        run_id=run_id,
        status=response_status,
        action="cancel",
    )
