"""
Runs API v2 — 基于新架构的轻量运行管理。

POST   /api/v2/runs          提交运行
GET    /api/v2/runs          列出运行
GET    /api/v2/runs/:id      查询状态
POST   /api/v2/runs/:id/cancel  取消
GET    /api/v2/runs/:id/log  获取日志
GET    /api/v2/runs/:id/files  列出结果文件
GET    /api/v2/runs/:id/files/:path  下载单个文件
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, FileResponse

from app.models.run import Run, RunCreate, RunStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/runs", tags=["runs"])

# In-memory store (server mode) or delegates to LocalBackend
# For now: simple in-memory dict shared across the process
_runs: dict[str, dict] = {}
_ws_clients: set[WebSocket] = set()


def _get_backend():
    """延迟导入，避免循环依赖。"""
    from src.backends.resolver import resolve_backend
    return resolve_backend()


# ------------------------------------------------------------------
# REST 端点
# ------------------------------------------------------------------

@router.post("", status_code=201)
async def submit_run(body: RunCreate):
    """提交一次 Snakemake 运行。"""
    backend = _get_backend()
    run = await backend.submit(
        workspace=body.workspace,
        snakefile=body.snakefile,
        config=body.config,
        cores=body.cores,
    )
    return {
        "id": run.id,
        "status": run.status,
        "workspace": run.workspace,
        "created_at": run.created_at,
    }


@router.get("")
async def list_runs(
    workspace: Optional[str] = Query(None),
):
    """列出运行。可按 workspace 过滤。"""
    backend = _get_backend()
    if workspace:
        runs = await backend.list_runs(workspace)
    else:
        runs = []  # 全局列表暂不支持
    return [
        {
            "id": r.id,
            "workspace": r.workspace,
            "status": r.status,
            "mode": r.mode,
            "pid": r.pid,
            "exit_code": r.exit_code,
            "created_at": r.created_at,
            "finished_at": r.finished_at,
        }
        for r in runs
    ]


@router.get("/{run_id}")
async def get_run_status(run_id: str):
    """查询单个运行的状态。"""
    backend = _get_backend()
    run = await backend.status(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "id": run.id,
        "workspace": run.workspace,
        "status": run.status,
        "mode": run.mode,
        "pid": run.pid,
        "exit_code": run.exit_code,
        "error": run.error,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str):
    """取消运行。"""
    backend = _get_backend()
    ok = await backend.cancel(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Run not found or already completed")
    return {"cancelled": True, "run_id": run_id}


@router.get("/{run_id}/log")
async def get_run_log(
    run_id: str,
    lines: int = Query(default=50, ge=1, le=1000),
):
    """获取运行日志（tail 最新 N 行）。"""
    backend = _get_backend()
    log = await backend.tail_log(run_id, lines=lines)
    return PlainTextResponse(content=log)


@router.get("/{run_id}/files")
async def list_result_files(
    run_id: str,
    pattern: str = Query(default="results/**"),
):
    """列出/拉取结果文件。"""
    backend = _get_backend()
    files = await backend.pull(run_id, patterns=[pattern])
    return {"files": files, "count": len(files)}


@router.get("/{run_id}/files/{file_path:path}")
async def get_result_file(run_id: str, file_path: str):
    """下载单个结果文件。"""
    backend = _get_backend()
    path = await backend.fetch(run_id, file_path)
    if not path:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)


# ------------------------------------------------------------------
# WebSocket: 实时状态推送
# ------------------------------------------------------------------

@router.websocket("/ws")
async def runs_websocket(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        while True:
            data = await ws.receive_text()
            # 客户端可以发送 { "subscribe": "run_id" } 来订阅特定 run
            # 当前实现：全部广播
    except WebSocketDisconnect:
        _ws_clients.discard(ws)
    except Exception:
        _ws_clients.discard(ws)


async def broadcast_run_status(run_id: str, status: str, **extra):
    """向所有 WebSocket 客户端广播运行状态。"""
    import json
    msg = json.dumps({"type": "run_status", "run_id": run_id, "status": status, **extra})
    dead = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead
