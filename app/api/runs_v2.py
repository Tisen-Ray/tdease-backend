"""
Runs API v2 — SSE 事件流 + 状态查询。

后端只做四件事：接受 commit、排队、执行、流出文件事件。
使用 SSE + Last-Event-ID 推送。

所有写入通过 Storage Layout（Route 不直接 open/write/mkdir）。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.responses import StreamingResponse

from src.contracts import (
    RunCommit,
    RunCreateRequest,
    RunListResponse,
    RunStatus,
    RunStatusResponse,
    run_not_found,
)
from src.execution_runtime.storage import get_storage

router = APIRouter(prefix="/api/v2/runs", tags=["runs"])


@router.post("", status_code=201)
async def create_run(body: RunCreateRequest):
    """
    提交 Run commit。

    使用 Storage Layout 原子写入 run.json + 初始事件。
    """
    commit = body.commit
    storage = get_storage()

    # Idempotent allocation (creates dir if not exists)
    storage.allocate_run(commit.run_id)

    run_json = storage.resolve(commit.run_id, "run.json")

    # Check idempotency first
    existing = storage.read_json(run_json)
    if existing and existing.get("idempotency_key") == commit.idempotency_key:
        return {"run_id": commit.run_id, "status": existing.get("status", "QUEUED"), "idempotent": True}

    if not commit.workspace_files:
        raise HTTPException(status_code=422, detail="workspace_files is required; submit an immutable client file mapping")
    try:
        storage.materialize_run_files(commit.run_id, commit.workspace_files)
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
    )

    return {"run_id": commit.run_id, "status": "QUEUED", "idempotent": False}


@router.get("/{run_id}", response_model=RunStatusResponse)
async def get_run(run_id: str):
    """查询 Run 状态 — 从 run.json + events.jsonl 投影。"""
    storage = get_storage()
    data = storage.read_json(storage.resolve(run_id, "run.json"))
    if not data:
        raise HTTPException(status_code=404, detail=run_not_found(run_id).message)

    last_seq = storage.recover_seq(run_id)

    return RunStatusResponse(
        run_id=run_id,
        workspace_id=data.get("workspace_id", ""),
        status=RunStatus(data.get("status", "QUEUED")),
        mode=data.get("mode", "local"),
        cores=data.get("cores", 4),
        pid=data.get("pid"),
        exit_code=data.get("exit_code"),
        error=data.get("error"),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
        started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
        finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
        event_seq_last=last_seq,
    )


@router.get("/{run_id}/events")
async def get_events_sse(
    run_id: str, request: Request,
    last_event_id: Optional[int] = Query(default=None, alias="last_event_id"),
):
    """SSE 事件流 — events.jsonl 尾部 → SSE。Last-Event-ID 断点续传。"""
    storage = get_storage()

    async def event_generator():
        events_file = storage.events_path(run_id)
        sent_seq = last_event_id or 0

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
):
    """列出 Run — 从文件系统扫描。"""
    storage = get_storage()
    runs_dir = storage.data / "runs"
    if not runs_dir.exists():
        return RunListResponse(runs=[], total=0, offset=offset, limit=limit)

    all_runs = []
    for rd in sorted(runs_dir.iterdir(), reverse=True):
        if not rd.is_dir():
            continue
        data = storage.read_json(rd / "run.json")
        if not data:
            continue
        if workspace_id and data.get("workspace_id") != workspace_id:
            continue
        all_runs.append(data)

    total = len(all_runs)
    page = all_runs[offset:offset + limit]

    runs = [
        RunStatusResponse(
            run_id=r.get("run_id", ""),
            workspace_id=r.get("workspace_id", ""),
            status=RunStatus(r.get("status", "QUEUED")),
            mode=r.get("mode", "local"),
            cores=r.get("cores", 4),
            pid=r.get("pid"),
            exit_code=r.get("exit_code"),
            error=r.get("error"),
            created_at=datetime.fromisoformat(r["created_at"]) if r.get("created_at") else datetime.utcnow(),
            started_at=datetime.fromisoformat(r["started_at"]) if r.get("started_at") else None,
            finished_at=datetime.fromisoformat(r["finished_at"]) if r.get("finished_at") else None,
            event_seq_last=0,
        )
        for r in page
    ]
    return RunListResponse(runs=runs, total=total, offset=offset, limit=limit)


@router.post("/{run_id}/cancel", status_code=200)
async def cancel_run(run_id: str):
    """取消 Run — 通过 Storage Layout 写入 cancel 标记。"""
    storage = get_storage()
    data = storage.read_json(storage.resolve(run_id, "run.json"))
    if not data:
        raise HTTPException(status_code=404, detail=run_not_found(run_id).message)

    status = data.get("status", "")
    if status not in ("QUEUED", "RUNNING"):
        from src.contracts import run_not_queued
        raise HTTPException(status_code=409, detail=run_not_queued(run_id, status).message)

    # Write cancel marker — worker's task loop checks this
    storage.mark_cancelled(run_id)

    # Dequeue: mark CANCELLED if still QUEUED (not yet claimed)
    if status == "QUEUED":
        storage.atomic_write_json(
            storage.resolve(run_id, "run.json"),
            {**data, "status": "CANCELLED"},
        )

    return {"run_id": run_id, "status": "CANCELLED"}
