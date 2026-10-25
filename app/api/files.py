"""
Files API — serve workspace files to the frontend ViewsFS.

GET  /api/v2/files           Read file content (text)
GET  /api/v2/files?stat=1    File stat (exists, mtime, type, size)
GET  /api/v2/files/list      List files matching glob
PUT  /api/v2/files            Write file content

Reads AND writes are restricted: canonical Run/event/log/result files, the
SQLite database, and the CAS blob store (runs/, database/, store/, blobs/,
.runtime/, .tdease/, .snakemake/) are not reachable through this
general-purpose, unauthenticated-per-Run endpoint at all -- it carries no
run_id/principal context to enforce ownership with, so those paths are
served exclusively through app/api/runs_v2.py's ownership-gated routes
instead. Writes additionally reject the Backend nodes/ directory: its
rules.smk files are executed as Python by Snakemake, so an unrestricted
write there is remote code execution. All writes go through Storage Layout
atomic primitives.
"""

from __future__ import annotations

import glob as glob_mod
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import PlainTextResponse, JSONResponse

from src.contracts.errors import ErrorCode, TDEaseError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/files", tags=["files"])

# ── Paths this generic, unauthenticated-per-Run Files API must never READ ──
# `runs/` holds every Principal's Run data (results, logs, the materialized
# workspace); `database/` and `store/` hold the SQLite DB and the CAS blob
# store. This API takes no run_id / principal context at all -- unlike
# app/api/runs_v2.py's `_owned_run`-gated routes, there is no ownership
# check possible here, so the only safe answer is "not reachable through
# this endpoint at all". Run files are served exclusively through
# runs_v2.py's ownership-gated `GET /api/v2/runs/{run_id}/files/...`.
# Confirmed unused by the Client today (TDEase-FrontEnd/src/services/views-fs.ts:
# "The backend files API (api/v2/files) is NOT used by the frontend.").
_PROTECTED_READ_PREFIXES = (
    "runs/",
    "trash/",
    "database/",
    "store/",
    "blobs/",
    ".runtime/",
    ".tdease/",
    ".snakemake/",
)

# ── Paths that the generic Files API must never write to ──
# Canonical Run state, events, logs, and internal directories are owned by
# the Execution Runtime / Storage Layout and must not be mutated via a
# general-purpose file endpoint. The resolved `nodes/` directory additionally
# holds the Snakemake rule files (`rules.smk`) that every workflow node's
# `shell:` directives live in -- Snakemake imports and executes them as
# Python, so an unrestricted write here is arbitrary code execution in the
# Backend process the next time any Run touches that node.
_PROTECTED_WRITE_PREFIXES = _PROTECTED_READ_PREFIXES + ("nodes/",)

# ── Helpers ──

# Root directory for file operations — single resolution point get_storage()
# (src/execution_runtime/storage.py); runtime root-resolution logic is no longer scattered.
def _data_root() -> Path:
    from src.execution_runtime.storage import get_storage
    return get_storage().data


def _safe_path(rel_path: str) -> Path:
    """Resolve and validate a path under data root.

    Both relative and absolute paths are resolved (symlinks, junctions, ..)
    *before* containment check — lexical-only checks can be bypassed by
    ``C:/data-root/runs/../outside`` on Windows.
    """
    root = _data_root().resolve()
    cleaned = rel_path.replace("\\", "/")

    if cleaned.startswith("/") or (len(cleaned) >= 2 and cleaned[1] == ":"):
        # Absolute path (Unix /foo/bar or Windows C:/foo/bar)
        candidate = Path(cleaned).resolve(strict=False)
    else:
        # Relative — join to root then resolve to collapse .. and symlinks
        candidate = (root / cleaned.lstrip("/")).resolve(strict=False)

    try:
        suffix = candidate.relative_to(root).as_posix()
    except ValueError:
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_PATH_ESCAPE,
            message="The requested path resolves outside the Backend data root.",
            remedy="Request a path relative to the data root, with no parent-directory segments.",
            retryable=False,
            details={"path": rel_path},
        )

    for prefix in _PROTECTED_READ_PREFIXES:
        stripped = prefix.rstrip("/")
        if suffix == stripped or suffix.startswith(prefix):
            raise TDEaseError(
                code=ErrorCode.WORKSPACE_PATH_ESCAPE,
                message="That path is in a protected area and cannot be read through this endpoint.",
                remedy=(
                    "Read Run data through GET /api/v2/runs/<run_id>/files, which enforces "
                    "Run ownership."
                ),
                retryable=False,
                details={"path": rel_path, "protected_prefix": prefix},
            )

    return candidate


@router.get("")
async def read_file(
    path: str = Query(..., description="Workspace-relative file path"),
    stat: int = Query(0, description="Return file stat instead of content"),
):
    abs_path = _safe_path(path)

    if not abs_path.exists():
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_FILE_NOT_FOUND,
            message="No file exists at that path.",
            remedy="List the directory with GET /api/v2/files/list to see what is there.",
            retryable=False,
            details={"path": path},
        )

    if stat:
        st = abs_path.stat()
        return {
            "path": path,
            "exists": True,
            "type": "directory" if abs_path.is_dir() else "file",
            "size": st.st_size,
            "mtime": st.st_mtime * 1000,  # ms epoch
        }

    if abs_path.is_dir():
        # Return directory listing rather than 400
        root = _data_root()
        children = []
        for child in sorted(abs_path.iterdir()):
            try:
                rel = str(child.relative_to(root)).replace("\\", "/")
                st = child.stat()
                children.append({
                    "name": child.name,
                    "path": rel,
                    "type": "directory" if child.is_dir() else "file",
                    "size": st.st_size,
                    "mtime": st.st_mtime * 1000,
                })
            except OSError:
                pass
        return {"path": path, "type": "directory", "children": children}

    try:
        content = abs_path.read_text(encoding="utf-8")
        return PlainTextResponse(content)
    except UnicodeDecodeError:
        # Binary file — return base64
        import base64
        data = abs_path.read_bytes()
        return {
            "path": path,
            "encoding": "base64",
            "data": base64.b64encode(data).decode("ascii"),
            "size": len(data),
        }


@router.get("/list")
async def list_files(
    cwd: str = Query("", description="Base directory"),
    glob: str = Query("*", description="Glob pattern"),
):
    """List files matching a glob pattern relative to cwd."""
    root = _data_root().resolve()
    base = _safe_path(cwd) if cwd else root
    if not base.exists() or not base.is_dir():
        return {"files": []}

    pattern = str(base / glob)
    matches = glob_mod.glob(pattern, recursive=True)
    files = []
    for m in matches:
        try:
            rel = str(Path(m).resolve().relative_to(root)).replace("\\", "/")
            files.append(rel)
        except ValueError:
            continue

    return {"files": sorted(files), "cwd": str(base.relative_to(root))}


def _writable_path(rel_path: str) -> Path:
    """Like _safe_path but additionally rejects protected write-only targets
    (_safe_path itself already rejects every _PROTECTED_READ_PREFIXES entry,
    which _PROTECTED_WRITE_PREFIXES is a superset of)."""
    candidate = _safe_path(rel_path)
    root = _data_root().resolve()
    try:
        suffix = str(candidate.relative_to(root)).replace("\\", "/")
    except ValueError:
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_PATH_ESCAPE,
            message="The requested path resolves outside the Backend data root.",
            remedy="Write to a path relative to the data root, with no parent-directory segments.",
            retryable=False,
            details={"path": rel_path},
        )

    for prefix in _PROTECTED_WRITE_PREFIXES:
        if suffix == prefix.rstrip("/") or suffix.startswith(prefix):
            raise TDEaseError(
                code=ErrorCode.WORKSPACE_PATH_ESCAPE,
                message="That path is in a protected area and cannot be written through this endpoint.",
                remedy=(
                    "Run data, the database, the blob store and the node packages are written "
                    "only by the Backend itself. Submit a Run instead of writing its files."
                ),
                retryable=False,
                details={"path": rel_path, "protected_prefix": prefix},
            )
    return candidate


@router.put("")
async def write_file(
    path: str = Body(..., embed=True),
    content: str = Body(..., embed=True),
):
    """Write text content to a file. Protected paths are rejected."""
    from src.execution_runtime.storage import get_storage

    abs_path = _writable_path(path)

    storage = get_storage()
    storage.bootstrap()
    storage.atomic_write(abs_path, content)
    return {"path": path, "written": True}
