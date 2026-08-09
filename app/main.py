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
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.backend_settings import BACKEND_SETTINGS, BackendSettings

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
logging.basicConfig(
    level=BACKEND_SETTINGS.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
from app.api.runs_v2 import router as runs_v2_router
from app.api.files import router as files_router
from app.api.uploads import router as uploads_router
from app.api.nodes import router as nodes_router
from app.api.capabilities import router as capabilities_router
from app.core.workspace_roots import router as workspace_roots_router, get_workspace_root_registry
from app.core.auth import authenticate_request, router as auth_router
from app.core.errors import ErrorCode, TDEaseError, register_error_handlers

# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TDEase-zero starting (env=%s)", BACKEND_SETTINGS.environment)
    from src.execution_runtime.storage import get_storage
    storage = get_storage()
    storage.bootstrap()
    recovered = storage.reconcile_orphaned_runs()
    if recovered:
        logger.warning("Recovered orphaned runs: %s", recovered)
    db_path = str(storage.data / "database" / "db.sqlite3")
    migrate_database(db_path)
    check_database_health(db_path)
    get_workspace_root_registry().configure(db_path)
    try:
        from src.services.run_index import get_run_index

        get_run_index().reconcile(storage)
        logger.info("Run index reconciled from filesystem truth")
    except Exception:
        logger.exception("Run index rebuild failed; filesystem fallbacks remain available")
    logger.info("Database ready: %s", db_path)

    # Workspace root containment: until this is wired, the fail-closed default in
    # src/execution_runtime/workspace_containment.py approves no root for anyone and
    # every local materialization raises WORKSPACE_PATH_ESCAPE. The registry is the
    # only thing consulted; Run commits carry an opaque root capability, not a path.
    from src.execution_runtime.workspace_containment import set_approved_roots_checker

    # Late-bound on purpose: the route handlers in app/core/workspace_roots.py read
    # the module-level registry at call time, so capturing a bound method here would
    # let the two diverge if the singleton is ever substituted.
    set_approved_roots_checker(
        lambda user_id, candidate_path: get_workspace_root_registry().is_within_approved_root(
            user_id, candidate_path
        )
    )

    logger.info("TDEase-zero ready")
    yield
    logger.info("TDEase-zero shutting down")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
_is_prod = BACKEND_SETTINGS.environment == "production"
_service_instance_id = uuid.uuid4().hex
_service_generation = BACKEND_SETTINGS.backend_generation or _service_instance_id[:12]
_service_started_at = datetime.now(timezone.utc).isoformat()

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
async def desktop_auth(request: Request, call_next):
    try:
        request.state.principal = await authenticate_request(request)
    except HTTPException as exc:
        # `exc.detail` is already the failure envelope (app/core/auth.py builds it
        # from TDEaseError). Wrapping it in {"detail": ...} produced a second,
        # incompatible shape on the wire that no Client could parse with the same
        # code path as every other error -- the envelope goes out as-is.
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)


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
app.include_router(uploads_router)
app.include_router(nodes_router)
app.include_router(capabilities_router)
app.include_router(workspace_roots_router)
app.include_router(auth_router)

# Failure contract — TDEaseError -> envelope response (docs/spec/FAILURE-CONTRACT.md)
register_error_handlers(app)


@app.get("/")
async def root():
    return {
        "name": "TDEase-zero",
        "version": "0.2.0",
        "environment": BACKEND_SETTINGS.environment,
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "instance_id": _service_instance_id,
        "generation": _service_generation,
        "started_at": _service_started_at,
    }


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
    return {
        "status": "ready",
        "engine": "tdease-workflow",
        "instance_id": _service_instance_id,
        "generation": _service_generation,
        "started_at": _service_started_at,
    }


@app.exception_handler(Exception)
async def global_handler(request: Request, exc: Exception):
    """The last resort still speaks the failure contract.

    `str(exc)` is a developer string: it has no code a Client can branch on, no
    remedy a user can act on, and it can carry an absolute path or a secret straight
    out of an arbitrary library's exception message. BACKEND_INTERNAL carries the
    same information a Client can actually use, and the real exception goes to the
    log where it belongs.
    """

    logger.exception("Unhandled error: %s", exc)
    internal = TDEaseError(
        code=ErrorCode.BACKEND_INTERNAL,
        message="The Backend failed to complete this request.",
        remedy=(
            "Retry the request. If it keeps failing, open the Backend log from the "
            "Desktop app and report the entry with this request's X-Request-ID."
        ),
        retryable=True,
    )
    return JSONResponse(status_code=internal.http_status, content=internal.to_envelope())

# ---------------------------------------------------------------------------
# Standalone entrypoint (`python -m app.main`). The packaged Desktop app does not
# use this path -- Electron spawns `uv run uvicorn app.main:app --host ... --port
# ...` directly with a port it already chose (DESKTOP-FIRST-DEPLOYMENT.md §4.1:
# "Electron starts Backend on 127.0.0.1 and a random available port"). This block
# exists for local/manual runs and must honour the same contract: loopback only,
# OS-assigned port by default, and a deterministic, parseable report of whatever
# port was actually bound -- never a fixed 0.0.0.0:8000 that collides across
# instances and is reachable from other local software.
# ---------------------------------------------------------------------------
def _resolve_backend_host(settings: BackendSettings = BACKEND_SETTINGS) -> str:
    """Return the host frozen by the process-wide startup settings."""
    return settings.bind_host


def _resolve_backend_port(settings: BackendSettings = BACKEND_SETTINGS) -> int:
    """0 means "let the OS assign a free port" -- the Desktop default. A caller
    that wants a fixed port for local debugging may still set TDEASE_BACKEND_PORT.
    """
    return settings.bind_port


def _select_backend_port(host: str, port: int) -> int:
    """Resolve the real port to bind, letting the OS assign a free one when
    ``port == 0``.

    Binds and immediately releases a probe socket so the real port is known
    -- deterministically, in this process -- before uvicorn starts. uvicorn's
    own ``fd=`` socket-handoff option is built around AF_UNIX socket
    activation (see uvicorn.Config.bind_socket) and is not a portable fit for
    a plain AF_INET port-0 bind on Windows, so this process hands uvicorn a
    concrete, already-resolved ``--port`` instead of a live socket.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        return sock.getsockname()[1]
    finally:
        sock.close()


def _report_backend_port(port: int, port_file: str | None = None) -> None:
    """Report the bound port deterministically.

    A structured, stable-prefixed stdout line is always emitted; a parent process
    should match on the `TDEASE_BACKEND_PORT=` prefix rather than parsing
    arbitrary log output. If TDEASE_PORT_FILE is set, the port is also written to
    that file so a parent that prefers file-based discovery can poll it instead.
    """
    print(f"TDEASE_BACKEND_PORT={port}", flush=True)
    if port_file:
        Path(port_file).write_text(str(port), encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    _host = _resolve_backend_host()
    _port = _select_backend_port(_host, _resolve_backend_port())
    _report_backend_port(_port, BACKEND_SETTINGS.port_file)
    uvicorn.run("app.main:app", host=_host, port=_port, reload=False)
