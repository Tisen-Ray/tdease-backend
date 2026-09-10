"""
TDEase-nexus API Server — a minimal FastAPI backend.

Does exactly four things:
1. Accept Run commits and enqueue them
2. Serve status queries from run.json + events.jsonl
3. Push the SSE event stream
4. Validate file paths and serve downloads
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import sys
import uuid
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.backend_settings import BACKEND_SETTINGS

# Path setup
_project_root = Path(__file__).parent.parent
_src_path = _project_root / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from app.database.init_db import check_database_health
from app.database.lifecycle import migrate_database

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=BACKEND_SETTINGS.log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
from app.api.runs_v2 import router as runs_v2_router
from app.api.files import router as files_router
from app.api.uploads import router as uploads_router
from app.api.nodes import router as nodes_router
from app.api.capabilities import router as capabilities_router
from app.api.workspace_roots import router as workspace_roots_router
from app.auth import authenticate_request, router as auth_router
from app.errors import register_error_handlers
from src.contracts.errors import ErrorCode, TDEaseError
from src.services.workspace_roots import configure_workspace_root_runtime

# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("TDEase-nexus starting (env=%s)", BACKEND_SETTINGS.environment)
    from src.execution_runtime.storage import get_storage
    storage = get_storage()
    storage.bootstrap()
    recovered = storage.reconcile_orphaned_runs()
    if recovered:
        logger.warning("Recovered orphaned runs: %s", recovered)
    db_path = str(storage.data / "database" / "db.sqlite3")
    migrate_database(db_path)
    check_database_health(db_path)
    configure_workspace_root_runtime(db_path)
    try:
        from src.services.run_index import get_run_index

        get_run_index().reconcile(storage)
        logger.info("Run index reconciled from filesystem truth")
    except Exception:
        logger.exception("Run index rebuild failed; filesystem fallbacks remain available")
    logger.info("Database ready: %s", db_path)

    logger.info("TDEase-nexus ready")
    yield
    logger.info("TDEase-nexus shutting down")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
_is_prod = BACKEND_SETTINGS.environment == "production"
_service_instance_id = uuid.uuid4().hex
_service_generation = BACKEND_SETTINGS.backend_generation or _service_instance_id[:12]
_service_started_at = datetime.now(timezone.utc).isoformat()

app = FastAPI(
    title="TDEase-nexus",
    description="Zero-architecture mass spectrometry workflow backend",
    version="0.2.0",
    docs_url=None if _is_prod else "/docs",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # The desktop Clients: the Electron renderer (file:// sends Origin
    # "null"), the vite dev proxy (a loopback origin), and non-browser
    # processes (no Origin at all). CORS is answered for exactly those --
    # the previous wildcard+credentials combo reflected ANY origin back as
    # allowed, which handed a tokenless local server to every website the
    # user visits. Enforcement lives in browser_origin_gate below.
    allow_origins=["null"],
    allow_origin_regex=r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def browser_origin_gate(request: Request, call_next):
    """Reject cross-origin browser requests before routing.

    In local auth mode every request is trusted, so the boundary against a
    malicious page is not CORS (a simple text/plain POST executes its side
    effect before the unreadable response matters, and DNS rebinding needs
    no CORS at all) but this gate: browsers always attach Origin to
    cross-origin requests, and the only legitimate browser origins are the
    Desktop's own. Non-browser Clients (Electron main, the agent harness)
    send no Origin and pass untouched.
    """
    origin = request.headers.get("origin")
    if origin is not None and origin != "null":
        from urllib.parse import urlparse

        host = (urlparse(origin).hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            error = TDEaseError(
                code=ErrorCode.AUTH_ORIGIN_FORBIDDEN,
                message="cross-origin browser requests are not accepted by this Backend",
                remedy="The Desktop client calls the Backend from its own origin; other sites must not.",
                retryable=False,
            )
            return JSONResponse(
                status_code=error.http_status, content=error.to_envelope()
            )
    return await call_next(request)


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
        # `exc.detail` is already the failure envelope (app/auth.py builds it
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
        "name": "TDEase-nexus",
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
