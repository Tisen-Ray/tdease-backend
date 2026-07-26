"""
Runs API v2 — SSE 事件流 + 状态查询。

后端只做四件事：接受 commit、排队、执行、流出文件事件。
使用 SSE + Last-Event-ID 推送。

所有写入通过 Storage Layout（Route 不直接 open/write/mkdir）。
"""

from __future__ import annotations

import asyncio
import json
import hashlib
import base64
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import FileResponse, PlainTextResponse, StreamingResponse

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
    TERMINAL_STATUSES,
    run_not_found,
    run_idempotency_conflict,
)
from src.execution_runtime.engine_contract import WorkflowEngineRequest
from src.execution_runtime.storage import get_storage
from src.services.node_catalog import materialize_bindings, resolve_bindings

# Reuses the Backend's own startup-resolved capability document (frozen at import
# time in app/api/capabilities.py) to select a materialization strategy instead of
# reading TDEASE_DEPLOYMENT_MODE per request. See docs/spec/CAPABILITIES.md section 7
# ("Materialization selection rule (resolves 0.2)") and REMAINING-DESIGNS.md section 0.2.
from app.api.capabilities import _CAPABILITIES
from app.core.errors import ErrorCode, TDEaseError

router = APIRouter(prefix="/api/v2/runs", tags=["runs"])

LOCAL_WORKSPACE_HARDLINK = "local_workspace_hardlink"
BLOB_STORE = "blob_store"


async def _reject_legacy_mode_field(request: Request) -> None:
    """Reject a caller-declared `mode` on the commit explicitly (REMAINING-DESIGNS.md
    section 0.2): `mode` has left the Run commit surface. Ignoring it silently would be
    a mysterious behaviour change for a caller that still believes it controls
    materialization; a caller must be told to stop sending it.

    Reads the already-buffered request body (Starlette caches it after FastAPI's own
    pydantic parsing), so this is not a second read of the wire and not an
    environment-variable read.
    """
    raw = await request.json()
    commit_raw = raw.get("commit") if isinstance(raw, dict) else None
    if isinstance(commit_raw, dict) and "mode" in commit_raw:
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


def _select_materialization_strategy(commit) -> str:
    """Resolve the materialization strategy for a commit from the Backend's own
    startup-resolved capabilities -- never from a caller-declared mode and never
    from an environment variable read at request time (DESKTOP-FIRST-DEPLOYMENT.md
    section 8 rule 2; docs/spec/CAPABILITIES.md section 7).

    The strategy is derived from the commit's own shape: a `local_workspace_root`
    reference requests `local_workspace_hardlink`; content-addressed
    `workspace_files` alone request `blob_store`. A shape that requests a strategy
    absent from this Backend's resolved `materialization.strategies` is rejected
    with a `run`-domain error, never silently coerced to a different strategy.
    """
    requested = LOCAL_WORKSPACE_HARDLINK if commit.local_workspace_root else BLOB_STORE
    allowed = _CAPABILITIES.materialization.strategies
    if requested not in allowed:
        raise TDEaseError(
            code=ErrorCode.RUN_MODE_MISMATCH,
            message=(
                f"commit shape requests materialization strategy '{requested}', which "
                f"is not among this Backend's resolved capabilities {list(allowed)}"
            ),
            remedy=(
                "Match the commit shape (local_workspace_root vs. content-addressed "
                "workspace_files) to a strategy listed in GET /api/capabilities' "
                "materialization.strategies, or submit to a Backend that supports it."
            ),
            retryable=False,
        )
    return requested


def _is_owner(data: dict, request: Request) -> bool:
    """The single ownership predicate every Run route consults (REMAINING-DESIGNS.md
    P0 "Resource authorization on read and mutate paths"). With today's single
    `local-owner` Principal this is always true -- that is the point: behaviour is
    unchanged today, but the enforcement point already exists everywhere a Run is
    read or mutated, before a second Principal or Server work ever arrives.
    """
    return data.get("user_id") == request.state.principal.user_id


async def _owned_run(run_id: str, request: Request) -> dict:
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


async def _owned_trashed_run(run_id: str, request: Request) -> dict:
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


def _run_status_response(data: dict, storage) -> RunStatusResponse:
    run_id = data.get("run_id", "")
    labels = data.get("labels") if isinstance(data.get("labels"), dict) else {}
    manifest = storage.read_json(storage.resolve(run_id, "results.manifest.json")) or {}
    result_files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    strategy = data.get("materialization_strategy") or LOCAL_WORKSPACE_HARDLINK
    return RunStatusResponse(
        run_id=run_id,
        name=str(labels.get("name") or run_id),
        workspace_id=data.get("workspace_id", ""),
        status=RunStatus(data.get("status", "QUEUED")),
        mode="local" if strategy == LOCAL_WORKSPACE_HARDLINK else "remote",
        materialization_strategy=strategy,
        cores=data.get("cores", 4),
        pid=data.get("pid"),
        exit_code=data.get("exit_code"),
        error=data.get("error"),
        rerun_mode=data.get("rerun_mode", "resume"),
        labels={str(key): str(value) for key, value in labels.items()},
        result_file_count=len(result_files),
        created_at=_parse_datetime(data.get("created_at")),
        started_at=_parse_datetime(data.get("started_at")) if data.get("started_at") else None,
        finished_at=_parse_datetime(data.get("finished_at")) if data.get("finished_at") else None,
        event_seq_last=storage.recover_seq(run_id),
    )


@router.post("/dry-run", response_model=RunDryRunResponse)
async def dry_run(payload: RunDryRunRequest, request: Request):
    """Validate an immutable client snapshot with the real workflow engine."""
    await _reject_legacy_mode_field(request)
    commit = payload.commit
    inline_blobs = payload.inline_blobs
    storage = get_storage()
    if not commit.workspace_files:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message="A dry-run requires workspace_files: the immutable client file mapping.",
            remedy="Freeze the Workspace into workspace_files and resubmit the plan.",
            retryable=False,
        )
    strategy = _select_materialization_strategy(commit)
    try:
        resolved_nodes = resolve_bindings(storage.data / "nodes", commit.nodes)
    except ValueError as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message=f"The Run node bindings could not be resolved: {exc}",
            remedy="Correct the node bindings on the commit, or install the missing node package.",
            retryable=False,
        ) from exc
    with storage.temp_dir("dry-run", commit.run_id) as root:
        materialize_bindings(root, resolved_nodes, storage.atomic_write)
        if strategy == LOCAL_WORKSPACE_HARDLINK:
            if not commit.local_workspace_root:
                raise TDEaseError(
                    code=ErrorCode.RUN_DRY_RUN_UNAVAILABLE,
                    message="local dry-run requires local_workspace_root for the local_workspace_hardlink strategy",
                    remedy="Submit local_workspace_root, or resubmit a commit shaped for the blob_store strategy.",
                    retryable=False,
                )
            workspace = Path(commit.local_workspace_root).resolve()
            for entry in commit.workspace_files:
                source = (workspace / entry.path).resolve(strict=True)
                try:
                    source.relative_to(workspace)
                except ValueError as exc:
                    raise TDEaseError(
                        code=ErrorCode.WORKSPACE_PATH_ESCAPE,
                        message=f"Local input {entry.path} resolves outside the Workspace root.",
                        remedy="Move the file inside the registered Workspace root and refreeze the mapping.",
                        retryable=False,
                    ) from exc
                if storage.file_digest(source) != entry.blob_hash:
                    raise TDEaseError(
                        code=ErrorCode.WORKSPACE_DIGEST_MISMATCH,
                        message=f"Local input {entry.path} changed after the Workspace was frozen.",
                        remedy="Refreeze the Workspace so the mapping matches the files on disk, then resubmit.",
                        retryable=False,
                    )
                target = root / entry.path
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(source, target)
                except OSError:
                    import shutil
                    shutil.copy2(source, target)
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
        snake = next((entry.path for entry in commit.workspace_files if entry.path in {"Snakefile", "workflow.smk"}), None)
        if snake is None:
            raise TDEaseError(
                code=ErrorCode.RUN_PLAN_INVALID,
                message="The workspace mapping contains no Snakefile or workflow.smk.",
                remedy="Include a Snakefile (or workflow.smk) in workspace_files.",
                retryable=False,
            )
        engine_request = WorkflowEngineRequest(
            mode="dry-run",
            snakefile=snake,
            config=commit.config,
            cores=commit.cores,
            targets=commit.targets,
            rerun_mode="resume",
        )
        storage.atomic_write_json(
            root / ".tdease" / "engine-request.json",
            engine_request.model_dump(),
        )
        command = [sys.executable, "-m", "src.execution_runtime.engine_runner"]
        completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=300, env=os.environ)
        output = completed.stdout + completed.stderr
        return {"valid": completed.returncode == 0, "exit_code": completed.returncode,
                "engine": "tdease-workflow", "output": output[-200_000:]}


@router.post("", status_code=201, response_model=RunCreateResponse)
async def create_run(body: RunCreateRequest, request: Request):
    """
    提交 Run commit。

    使用 Storage Layout 原子写入 run.json + 初始事件。
    """
    await _reject_legacy_mode_field(request)
    commit = body.commit.model_copy(update={"user_id": request.state.principal.user_id})
    storage = get_storage()

    # Idempotent allocation (creates dir if not exists)
    storage.allocate_run(commit.run_id)

    run_json = storage.resolve(commit.run_id, "run.json")

    # Check idempotency first
    existing = storage.read_json(run_json)
    if existing and existing.get("idempotency_key") == commit.idempotency_key:
        return RunCreateResponse(**_run_status_response(existing, storage).model_dump(), idempotent=True)
    if existing:
        error = run_idempotency_conflict(commit.idempotency_key, commit.run_id)
        raise TDEaseError(
            code=ErrorCode.RUN_IDEMPOTENCY_CONFLICT,
            message=error.message,
            remedy="Reuse the existing Run, or submit with a fresh idempotency_key.",
            retryable=False,
        )

    if not commit.workspace_files:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message="workspace_files is required: a Run commits an immutable client file mapping.",
            remedy="Freeze the Workspace into workspace_files and resubmit the commit.",
            retryable=False,
        )
    strategy = _select_materialization_strategy(commit)
    commit = commit.model_copy(update={"materialization_strategy": strategy})
    try:
        resolved_nodes = resolve_bindings(storage.data / "nodes", commit.nodes)
        if strategy == LOCAL_WORKSPACE_HARDLINK:
            if not commit.local_workspace_root:
                raise ValueError("local_workspace_root is required for the local_workspace_hardlink strategy")
            # user_id is passed so containment resolves against *this Principal's*
            # approved Workspace roots (app.core.workspace_roots.is_within_approved_root),
            # never a root the request itself asserts -- see
            # src/execution_runtime/workspace_containment.py's module docstring,
            # "the one call site that currently invokes materialize_local_run_files
            # without a user_id ... must start passing one" (owned by agent B4;
            # this is the B2-owned call site that docstring names).
            storage.materialize_local_run_files(
                commit.run_id, Path(commit.local_workspace_root), commit.workspace_files,
                user_id=commit.user_id,
            )
        else:
            if commit.local_workspace_root:
                raise ValueError("local_workspace_root is forbidden for the blob_store strategy")
            storage.materialize_run_files(commit.run_id, commit.workspace_files)
        materialize_bindings(storage.resolve(commit.run_id), resolved_nodes, storage.atomic_write)
    except (FileNotFoundError, ValueError) as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message=f"The Run snapshot could not be materialized: {exc}",
            remedy="Check that every workspace file is reachable and its digest still matches, then resubmit.",
            retryable=False,
        ) from exc

    snake_entry = next((item for item in commit.workspace_files if item.path in {"Snakefile", "workflow.smk"}), None)
    if snake_entry is None:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_INVALID,
            message="The workspace mapping contains no Snakefile or workflow.smk.",
            remedy="Include a Snakefile (or workflow.smk) in workspace_files.",
            retryable=False,
        )
    snake_text = storage.resolve(commit.run_id, snake_entry.path).read_text(encoding="utf-8")
    if commit.snakefile and commit.snakefile != snake_text:
        raise TDEaseError(
            code=ErrorCode.RUN_PLAN_STALE,
            message="The commit embedded snakefile differs from the mapped Workspace file.",
            remedy="Refreeze the Workspace so both views agree, then resubmit the commit.",
            retryable=False,
        )

    # Atomically write run.json (status QUEUED)
    run_data = commit.model_dump()
    run_data["snakefile"] = snake_text
    run_data["snakefile_path"] = snake_entry.path
    run_data["status"] = "QUEUED"
    run_data["rerun_mode"] = "resume"
    storage.atomic_write_json(run_json, run_data)

    # Write initial event through storage (seq allocated by storage)
    from src.execution_runtime.events import EventEmitter
    emitter = EventEmitter(commit.run_id)
    emitter.run_queued(
        idempotency_key=commit.idempotency_key,
        workspace_tree_hash=commit.workspace_tree_hash,
        user_id=commit.user_id,
        cores=commit.cores,
        workflow_steps=0,
        actor=_actor(request),
    )

    return RunCreateResponse(**_run_status_response(run_data, storage).model_dump(), idempotent=False)


@router.get("/trash", response_model=RunTrashListResponse)
async def list_trashed_runs(request: Request):
    storage = get_storage()
    entries: list[RunTrashEntry] = []
    for directory in storage.trashed_run_dirs():
        data = storage.read_json(directory / "run.json") or {}
        if not _is_owner(data, request):
            continue
        metadata = storage.read_json(directory / ".tdease" / "trash.json") or {}
        labels = data.get("labels") if isinstance(data.get("labels"), dict) else {}
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
async def restore_run(run_id: str, request: Request, _owned: dict = Depends(_owned_trashed_run)):
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
    return _run_status_response(data, storage)


@router.get("/{run_id}", response_model=RunStatusResponse)
async def get_run(run_id: str, data: dict = Depends(_owned_run)):
    """查询 Run 状态 — 从 run.json + events.jsonl 投影。"""
    storage = get_storage()
    return _run_status_response(data, storage)


@router.post("/{run_id}/rerun", response_model=RunActionResponse)
async def rerun_run(run_id: str, body: RunRerunRequest, request: Request, data: dict = Depends(_owned_run)):
    """Queue the same Run in place, preserving its incremental engine state."""
    storage = get_storage()
    run_json = storage.resolve(run_id, "run.json")

    status = RunStatus(data.get("status", "QUEUED"))
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
    storage.atomic_write_json(
        run_json,
        {
            **data,
            "status": RunStatus.QUEUED.value,
            "rerun_mode": body.mode,
            "pid": None,
            "engine_pid": None,
            "exit_code": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        },
    )

    from src.execution_runtime.events import EventEmitter
    EventEmitter(run_id).run_queued(
        rerun=True,
        rerun_mode=body.mode,
        workspace_tree_hash=data.get("workspace_tree_hash", ""),
        user_id=data.get("user_id", ""),
        cores=data.get("cores", 1),
        actor=_actor(request),
    )
    EventEmitter(run_id).run_action("rerun", _actor(request), mode=body.mode)
    return RunActionResponse(
        run_id=run_id,
        status=RunStatus.QUEUED,
        action="rerun",
        mode=body.mode,
    )


@router.post("/{run_id}/trash", response_model=RunTrashEntry)
async def trash_run(run_id: str, request: Request, data: dict = Depends(_owned_run)):
    storage = get_storage()
    status = RunStatus(data.get("status", "QUEUED"))
    if status not in TERMINAL_STATUSES:
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_TERMINAL,
            message=f"Run {run_id} is {status.value}; only a terminal Run can be moved to trash.",
            remedy="Wait for the Run to finish, or cancel it first.",
            retryable=False,
        )
    deleted_at = datetime.now(timezone.utc)
    deleted_by = _actor(request)
    labels = data.get("labels") if isinstance(data.get("labels"), dict) else {}
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
async def list_run_results(run_id: str, data: dict = Depends(_owned_run)):
    """Published Result projection: join `result_specs` against what actually
    materialized (docs/spec/WORKFLOW-RUN-CONTRACT.md 8.4; docs/design/CORE-ARCHITECTURE.md 3).

    Readiness is a join, not a state: a declared spec whose `output` is not yet a
    file on disk projects `status="declared"` -- it is reported, never silently
    omitted. A spec whose `output` exists projects `status="ready"` with the
    current digest. Any file under `results/` that no spec declares never appears
    here; it stays a Technical Artifact, reachable only through
    `GET /api/v2/runs/{run_id}/files`.
    """
    storage = get_storage()
    workspace_id = data.get("workspace_id", "")
    specs = data.get("result_specs") or []
    results: list[RunResultEntry] = []
    for spec in specs:
        result_id = spec.get("result_id", "")
        output = spec.get("output", "")
        path = _run_file(run_id, output)
        digest: Optional[str] = None
        size: Optional[int] = None
        status = "declared"
        if path.is_file():
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
    return RunResultsResponse(run_id=run_id, results=results)


@router.get("/{run_id}/files")
async def list_run_files(run_id: str, pattern: str = Query("results/**"), _owned: dict = Depends(_owned_run)):
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
    files = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        resolved = path.resolve(strict=False)
        try:
            rel = resolved.relative_to(resolved_root).as_posix()
        except ValueError:
            continue
        if rel.startswith((".runtime/", ".tdease/", ".snakemake/")):
            continue
        digest = get_storage().file_digest(resolved)
        files.append({"path": rel, "size": resolved.stat().st_size, "sha256": digest})
    return {"run_id": run_id, "files": files}


@router.get("/{run_id}/files/{file_path:path}")
async def download_run_file(run_id: str, file_path: str, _owned: dict = Depends(_owned_run)):
    """Stream one run snapshot/result file; Starlette provides HTTP Range support."""
    path = _run_file(run_id, file_path)
    if not path.is_file() or file_path.startswith((".runtime/", ".tdease/", ".snakemake/")):
        raise TDEaseError(
            code=ErrorCode.RUN_FILE_NOT_FOUND,
            message=f"Run {run_id} has no readable file at {file_path}.",
            remedy="List the Run files with GET /api/v2/runs/<run_id>/files.",
            retryable=False,
        )
    digest = get_storage().file_digest(path)
    return FileResponse(path, filename=path.name, headers={"ETag": f'"sha256-{digest}"'})


@router.get("/{run_id}/log")
async def get_run_log(run_id: str, tail: int = Query(200, ge=1, le=10000), _owned: dict = Depends(_owned_run)):
    paths = [
        _run_file(run_id, "logs/tasks/engine.stdout.log"),
        _run_file(run_id, "logs/tasks/engine.stderr.log"),
    ]
    existing = [path for path in paths if path.is_file()]
    if not existing:
        raise TDEaseError(
            code=ErrorCode.RUN_FILE_NOT_FOUND,
            message=f"Run {run_id} has no log file yet.",
            remedy="Logs appear once the Run starts; check the Run status first.",
            retryable=False,
        )
    lines: list[str] = []
    for path in existing:
        lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return PlainTextResponse("\n".join(lines[-tail:]) + ("\n" if lines else ""))


@router.get("/{run_id}/events")
async def get_events_sse(
    run_id: str, request: Request,
    last_event_id: Optional[int] = Query(default=None, alias="last_event_id"),
    _owned: dict = Depends(_owned_run),
):
    """SSE 事件流 — events.jsonl 尾部 → SSE。Last-Event-ID 断点续传。"""
    storage = get_storage()

    async def event_generator():
        events_file = storage.events_path(run_id)
        # query param 优先，其次读标准 SSE Last-Event-ID header
        cursor = last_event_id
        if cursor is None:
            header_val = request.headers.get("Last-Event-ID")
            if header_val is not None:
                try:
                    cursor = int(header_val)
                except (ValueError, TypeError):
                    cursor = 0
        sent_seq = cursor or 0

        if events_file.exists():
            for line in events_file.read_text(encoding="utf-8").strip().splitlines():
                if not line.strip():
                    continue
                try:
                    evt = json.loads(line)
                    if evt.get("seq", 0) > sent_seq:
                        yield f"id: {evt['seq']}\ndata: {line}\n\n"
                        sent_seq = evt["seq"]
                except json.JSONDecodeError:
                    continue

        while True:
            if await request.is_disconnected():
                break
            if events_file.exists():
                lines = events_file.read_text(encoding="utf-8").strip().splitlines()
                for line in lines:
                    if not line.strip():
                        continue
                    try:
                        evt = json.loads(line)
                        if evt.get("seq", 0) > sent_seq:
                            yield f"id: {evt['seq']}\ndata: {line}\n\n"
                            sent_seq = evt["seq"]
                    except json.JSONDecodeError:
                        continue
            data = storage.read_json(storage.resolve(run_id, "run.json"))
            if data and data.get("status") in ("SUCCEEDED", "FAILED", "CANCELLED"):
                yield f"event: done\ndata: {{\"status\": \"{data['status']}\"}}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("", response_model=RunListResponse)
async def list_runs(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: Optional[str] = None,
    status: list[RunStatus] | None = Query(default=None),
    query: Optional[str] = Query(default=None, min_length=1, max_length=200),
):
    """列出 Run — 从文件系统扫描，只返回调用方 Principal 拥有的 Run。"""
    storage = get_storage()
    runs_dir = storage.data / "runs"
    if not runs_dir.exists():
        return RunListResponse(runs=[], total=0, offset=offset, limit=limit, has_more=False)

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
        if status and RunStatus(data.get("status", "QUEUED")) not in status:
            continue
        if query:
            labels = data.get("labels") if isinstance(data.get("labels"), dict) else {}
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
async def cancel_run(run_id: str, request: Request, data: dict = Depends(_owned_run)):
    """取消 Run — 通过 Storage Layout 写入 cancel 标记。"""
    storage = get_storage()
    status = RunStatus(data.get("status", "QUEUED"))
    if status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        from src.contracts import run_not_queued
        raise TDEaseError(
            code=ErrorCode.RUN_NOT_QUEUED,
            message=run_not_queued(run_id, status.value).message,
            remedy="Only a queued or running Run can be cancelled.",
            retryable=False,
        )

    # Write cancel marker — worker's task loop checks this
    storage.mark_cancelled(run_id)
    from src.execution_runtime.events import EventEmitter
    EventEmitter(run_id).run_action("cancel", _actor(request), previous_status=status.value)

    # Dequeue: mark CANCELLED if still QUEUED (not yet claimed)
    response_status = status
    if status == RunStatus.QUEUED:
        storage.atomic_write_json(
            storage.resolve(run_id, "run.json"),
            {
                **data,
                "status": RunStatus.CANCELLED.value,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        EventEmitter(run_id).run_cancelled()
        response_status = RunStatus.CANCELLED

    return RunActionResponse(
        run_id=run_id,
        status=response_status,
        action="cancel",
    )
