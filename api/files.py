"""
Files API — serve workspace files to the frontend ViewsFS.

GET  /api/v2/files           Read file content (text)
GET  /api/v2/files?stat=1    File stat (exists, mtime, type, size)
GET  /api/v2/files/list      List files matching glob
PUT  /api/v2/files            Write file content

Writes are restricted: canonical Run/event/log/result files and internal
directories (runs/, database/, store/, .runtime/) are read-only through
this API.  All writes go through Storage Layout atomic primitives.
"""

from __future__ import annotations

import glob as glob_mod
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Body
from fastapi.responses import PlainTextResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/files", tags=["files"])

# ── Paths that the generic Files API must never write to ──
# Canonical Run state, events, logs, and internal directories are owned by
# the Execution Runtime / Storage Layout and must not be mutated via a
# general-purpose file endpoint.
_PROTECTED_WRITE_PREFIXES = (
    "runs/",
    "database/",
    "store/",
    ".runtime/",
    "blobs/",
)

# ── Helpers ──

# Root directory for file operations — respects TDEASE_DATA_ROOT env
def _data_root() -> Path:
    return Path(os.environ.get("TDEASE_DATA_ROOT", "server-data"))


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
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail=f"Path traversal denied: {rel_path}")

    return candidate


@router.get("")
async def read_file(
    path: str = Query(..., description="Workspace-relative file path"),
    stat: int = Query(0, description="Return file stat instead of content"),
):
    abs_path = _safe_path(path)

    if not abs_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

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
    """Like _safe_path but additionally rejects protected write targets."""
    candidate = _safe_path(rel_path)
    root = _data_root().resolve()
    try:
        suffix = str(candidate.relative_to(root)).replace("\\", "/")
    except ValueError:
        raise HTTPException(status_code=403, detail=f"Path traversal denied: {rel_path}")

    for prefix in _PROTECTED_WRITE_PREFIXES:
        if suffix == prefix.rstrip("/") or suffix.startswith(prefix):
            raise HTTPException(
                status_code=403,
                detail=f"Write denied: {rel_path} is in protected area ({prefix})",
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
