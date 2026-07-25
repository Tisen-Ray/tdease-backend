"""
TDEase-zero API Server — 极简 FastAPI 后端。

只做四件事：
1. 接收 Run commit 并入库排队
2. 提供 run.json + events.jsonl 状态查询
3. SSE 事件流推送
4. 文件路径校验与下载
"""

from __future__ import annotations

import logging
import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Path setup
_project_root = Path(__file__).parent.parent
_src_path = _project_root / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from app.database.init_db import check_database_health
from app.database.lifecycle import migrate_database

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
log_level = getattr(logging, os.getenv("TDEASE_LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
from app.api.runs_v2 import router as runs_v2_router
from app.api.files import router as files_router
from app.api.workflow_templates import router as workflow_templates_router
from app.api.uploads import router as uploads_router
from app.api.nodes import router as nodes_router
from app.api.templates import router as templates_router

# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TDEase-zero starting (env=%s)", os.getenv("TDEASE_ENV", "development"))
    from src.execution_runtime.storage import get_storage
    storage = get_storage()
    storage.bootstrap()
    recovered = storage.reconcile_orphaned_runs()
    if recovered:
        logger.warning("Recovered orphaned runs: %s", recovered)
    db_path = str(storage.data / "database" / "db.sqlite3")
    try:
        migrate_database(db_path)
        check_database_health(db_path)
        logger.info("Database ready: %s", db_path)
    except Exception as e:
        logger.warning("Database migration skipped: %s", e)

    worker_stop = None
    worker_task = None
    if os.getenv("TDEASE_EMBEDDED_WORKER", "1") == "1":
        from threading import Event
        from src.services.run_worker import run_loop

        worker_stop = Event()
        worker_task = asyncio.create_task(
            asyncio.to_thread(run_loop, 1.0, False, worker_stop)
        )
        logger.info("Embedded run worker started")

    logger.info("TDEase-zero ready")
    yield
    if worker_stop:
        worker_stop.set()
    if worker_task:
        await worker_task
    logger.info("TDEase-zero shutting down")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
_is_prod = os.getenv("TDEASE_ENV") == "production"

app = FastAPI(
    title="TDEase-zero",
    description="Zero-architecture mass spectrometry workflow backend",
    version="0.2.0",
    docs_url=None if _is_prod else "/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.middleware("http")
async def request_log(request: Request, call_next):
    rid = uuid.uuid4().hex[:12]
    start = perf_counter()
    response = await call_next(request)
    elapsed = int((perf_counter() - start) * 1000)
    logger.info("access id=%s %s %s %s %sms", rid, request.method, request.url.path, response.status_code, elapsed)
    response.headers["X-Request-ID"] = rid
    return response

# Routes
app.include_router(runs_v2_router)
app.include_router(files_router)
app.include_router(workflow_templates_router)
app.include_router(uploads_router)
app.include_router(nodes_router)
app.include_router(templates_router)


@app.get("/")
async def root():
    return {
        "name": "TDEase-zero",
        "version": "0.2.0",
        "environment": os.getenv("TDEASE_ENV", "development"),
    }


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    """Readiness reflects execution capability, not optional JSON references."""
    import importlib.util
    if importlib.util.find_spec("snakemake") is None:
        return JSONResponse(status_code=503, content={"status": "not_ready", "missing": "workflow-engine"})
    storage = __import__("src.execution_runtime.storage", fromlist=["get_storage"]).get_storage()
    storage.bootstrap()
    return {"status": "ready", "engine": "tdease-workflow"}


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"error": str(exc)})

# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
