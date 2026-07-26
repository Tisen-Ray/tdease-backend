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

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.responses import FileResponse, PlainTextResponse, StreamingResponse

from src.contracts import (
    RunCreateRequest,
    RunCreateResponse,
    RunDryRunRequest,
    RunDryRunResponse,
    RunActionResponse,
    RunListResponse,
    RunRerunRequest,
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

router = APIRouter(prefix="/api/v2/runs", tags=["runs"])


def _run_file(run_id: str, relative: str) -> Path:
    storage = get_storage()
    path = storage.resolve(run_id, relative).resolve(strict=False)
    root = storage.resolve(run_id).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="run path traversal denied") from exc
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
    return RunStatusResponse(
        run_id=run_id,
        name=str(labels.get("name") or run_id),
        workspace_id=data.get("workspace_id", ""),
        status=RunStatus(data.get("status", "QUEUED")),
        mode=data.get("mode", "local"),
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
def dry_run(payload: RunDryRunRequest):
    """Validate an immutable client snapshot with the real workflow engine."""
    commit = payload.commit
    inline_blobs = payload.inline_blobs
    storage = get_storage()
    if not commit.workspace_files:
        raise HTTPException(status_code=422, detail="workspace_files is required")
    try:
        resolved_nodes = resolve_bindings(storage.data / "nodes", commit.nodes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with storage.temp_dir("dry-run", commit.run_id) as root:
        materialize_bindings(root, resolved_nodes, storage.atomic_write)
        if commit.mode == "local":
            if os.environ.get("TDEASE_DEPLOYMENT_MODE", "local") != "local" or not commit.local_workspace_root:
                raise HTTPException(status_code=409, detail="local dry-run is unavailable")
            workspace = Path(commit.local_workspace_root).resolve()
            for entry in commit.workspace_files:
                source = (workspace / entry.path).resolve(strict=True)
                try:
                    source.relative_to(workspace)
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail="local source escapes workspace") from exc
                if storage.file_digest(source) != entry.blob_hash:
                    raise HTTPException(status_code=409, detail=f"local source changed: {entry.path}")
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
                raise HTTPException(status_code=422, detail={"missing_blobs": sorted(set(missing))})
            for entry in commit.workspace_files:
                target = (root / entry.path).resolve(strict=False)
                try:
                    target.relative_to(root.resolve())
                except ValueError as exc:
                    raise HTTPException(status_code=403, detail="snapshot path traversal denied") from exc
                if storage.blob_exists(entry.blob_hash):
                    content = storage.blob_get(entry.blob_hash)
                else:
                    try:
                        content = base64.b64decode(inline_blobs[entry.blob_hash], validate=True)
                    except (KeyError, ValueError) as exc:
                        raise HTTPException(status_code=422, detail=f"invalid inline blob: {entry.blob_hash}") from exc
                    if hashlib.sha256(content).hexdigest() != entry.blob_hash:
                        raise HTTPException(status_code=422, detail=f"inline blob digest mismatch: {entry.blob_hash}")
                storage.atomic_write(target, content)
        snake = next((entry.path for entry in commit.workspace_files if entry.path in {"Snakefile", "workflow.smk"}), None)
        if snake is None:
            raise HTTPException(status_code=422, detail="workspace mapping must contain Snakefile or workflow.smk")
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
        raise HTTPException(status_code=409, detail=error.message)

    if not commit.workspace_files:
        raise HTTPException(status_code=422, detail="workspace_files is required; submit an immutable client file mapping")
    deployment_mode = os.environ.get("TDEASE_DEPLOYMENT_MODE", "local").lower()
    if commit.mode != deployment_mode:
        raise HTTPException(status_code=409, detail=f"run mode {commit.mode} does not match deployment mode {deployment_mode}")
    try:
        resolved_nodes = resolve_bindings(storage.data / "nodes", commit.nodes)
        if deployment_mode == "local":
            if not commit.local_workspace_root:
                raise ValueError("local_workspace_root is required in local mode")
            storage.materialize_local_run_files(commit.run_id, Path(commit.local_workspace_root), commit.workspace_files)
        else:
            if commit.local_workspace_root:
                raise ValueError("local_workspace_root is forbidden in remote mode")
            storage.materialize_run_files(commit.run_id, commit.workspace_files)
        materialize_bindings(storage.resolve(commit.run_id), resolved_nodes, storage.atomic_write)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    snake_entry = next((item for item in commit.workspace_files if item.path in {"Snakefile", "workflow.smk"}), None)
    if snake_entry is None:
        raise HTTPException(status_code=422, detail="workspace mapping must contain Snakefile or workflow.smk")
    snake_text = storage.resolve(commit.run_id, snake_entry.path).read_text(encoding="utf-8")
    if commit.snakefile and commit.snakefile != snake_text:
        raise HTTPException(status_code=409, detail="embedded snakefile differs from mapped client file")

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
async def list_trashed_runs():
    storage = get_storage()
    entries: list[RunTrashEntry] = []
    for directory in storage.trashed_run_dirs():
        data = storage.read_json(directory / "run.json") or {}
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
async def restore_run(run_id: str, request: Request):
    storage = get_storage()
    try:
        storage.restore_run(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trashed Run not found") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    data = storage.read_json(storage.resolve(run_id, "run.json")) or {}
    from src.execution_runtime.events import EventEmitter
    EventEmitter(run_id).run_action("restore", _actor(request))
    return _run_status_response(data, storage)


@router.get("/{run_id}", response_model=RunStatusResponse)
async def get_run(run_id: str):
    """查询 Run 状态 — 从 run.json + events.jsonl 投影。"""
    storage = get_storage()
    data = storage.read_json(storage.resolve(run_id, "run.json"))
    if not data:
        raise HTTPException(status_code=404, detail=run_not_found(run_id).message)

    return _run_status_response(data, storage)


@router.post("/{run_id}/rerun", response_model=RunActionResponse)
async def rerun_run(run_id: str, body: RunRerunRequest, request: Request):
    """Queue the same Run in place, preserving its incremental engine state."""
    storage = get_storage()
    run_json = storage.resolve(run_id, "run.json")
    data = storage.read_json(run_json)
    if not data:
        raise HTTPException(status_code=404, detail=run_not_found(run_id).message)

    status = RunStatus(data.get("status", "QUEUED"))
    if status not in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} is {status.value}; only terminal runs can be rerun",
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
async def trash_run(run_id: str, request: Request):
    storage = get_storage()
    run_json = storage.resolve(run_id, "run.json")
    data = storage.read_json(run_json)
    if not data:
        raise HTTPException(status_code=404, detail=run_not_found(run_id).message)
    status = RunStatus(data.get("status", "QUEUED"))
    if status not in TERMINAL_STATUSES:
        raise HTTPException(status_code=409, detail="only terminal Runs can be moved to trash")
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
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return RunTrashEntry(
        run_id=run_id,
        name=str(labels.get("name") or run_id),
        workspace_id=data.get("workspace_id", ""),
        previous_status=status,
        deleted_at=deleted_at,
        deleted_by=deleted_by,
    )


@router.get("/{run_id}/files")
async def list_run_files(run_id: str, pattern: str = Query("results/**")):
    """Return a hash-addressed manifest for pull/fetch and AI discovery."""
    root = get_storage().resolve(run_id)
    if not root.is_dir():
        raise HTTPException(status_code=404, detail=run_not_found(run_id).message)
    files = []
    for path in sorted(root.glob(pattern)):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel.startswith((".runtime/", ".tdease/", ".snakemake/")):
            continue
        digest = get_storage().file_digest(path)
        files.append({"path": rel, "size": path.stat().st_size, "sha256": digest})
    return {"run_id": run_id, "files": files}


@router.get("/{run_id}/files/{file_path:path}")
async def download_run_file(run_id: str, file_path: str):
    """Stream one run snapshot/result file; Starlette provides HTTP Range support."""
    path = _run_file(run_id, file_path)
    if not path.is_file() or file_path.startswith((".runtime/", ".tdease/", ".snakemake/")):
        raise HTTPException(status_code=404, detail="run file not found")
    digest = get_storage().file_digest(path)
    return FileResponse(path, filename=path.name, headers={"ETag": f'"sha256-{digest}"'})


@router.get("/{run_id}/log")
async def get_run_log(run_id: str, tail: int = Query(200, ge=1, le=10000)):
    paths = [
        _run_file(run_id, "logs/tasks/engine.stdout.log"),
        _run_file(run_id, "logs/tasks/engine.stderr.log"),
    ]
    existing = [path for path in paths if path.is_file()]
    if not existing:
        raise HTTPException(status_code=404, detail="run log not found")
    lines: list[str] = []
    for path in existing:
        lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return PlainTextResponse("\n".join(lines[-tail:]) + ("\n" if lines else ""))


@router.get("/{run_id}/events")
async def get_events_sse(
    run_id: str, request: Request,
    last_event_id: Optional[int] = Query(default=None, alias="last_event_id"),
):
    """SSE 事件流 — events.jsonl 尾部 → SSE。Last-Event-ID 断点续传。"""
    storage = get_storage()
    if not storage.resolve(run_id, "run.json").is_file():
        raise HTTPException(status_code=404, detail=run_not_found(run_id).message)

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
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    workspace_id: Optional[str] = None,
    status: list[RunStatus] | None = Query(default=None),
    query: Optional[str] = Query(default=None, min_length=1, max_length=200),
):
    """列出 Run — 从文件系统扫描。"""
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
async def cancel_run(run_id: str, request: Request):
    """取消 Run — 通过 Storage Layout 写入 cancel 标记。"""
    storage = get_storage()
    data = storage.read_json(storage.resolve(run_id, "run.json"))
    if not data:
        raise HTTPException(status_code=404, detail=run_not_found(run_id).message)

    status = RunStatus(data.get("status", "QUEUED"))
    if status not in (RunStatus.QUEUED, RunStatus.RUNNING):
        from src.contracts import run_not_queued
        raise HTTPException(status_code=409, detail=run_not_queued(run_id, status.value).message)

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
