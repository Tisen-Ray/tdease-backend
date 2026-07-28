"""Durable, per-principal capabilities for Desktop-local Workspace roots.

An absolute path crosses the public boundary only when the Desktop Client attaches a
directory. Later Run requests name the opaque ``root_id`` and a relative Run path;
they cannot assert their own filesystem authorization boundary. Grants live in
Backend-private SQLite state so a Backend restart does not invalidate an open
Workspace. Server/blob deployments never use this capability.
"""

from __future__ import annotations

import os
import hashlib
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/workspace-roots", tags=["workspace-roots"])


# ---------------------------------------------------------------------------
# Wire schema
# ---------------------------------------------------------------------------


class WorkspaceRootRegisterRequest(BaseModel):
    path: str = Field(description="Absolute local directory path chosen through the native picker")


class WorkspaceRootEntry(BaseModel):
    root_id: str
    path: str


class WorkspaceRootListResponse(BaseModel):
    roots: list[WorkspaceRootEntry]


# ---------------------------------------------------------------------------
# Failure envelope (CORE-ARCHITECTURE.md section 7.1), `workspace` domain
# ---------------------------------------------------------------------------


def _envelope(*, code: str, message: str, remedy: str, retryable: bool = False) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "domain": "workspace",
            "message": message,
            "remedy": remedy,
            "retryable": retryable,
        }
    }


def _reject(*, code: str, message: str, remedy: str, status_code: int = 400) -> HTTPException:
    return HTTPException(status_code=status_code, detail=_envelope(code=code, message=message, remedy=remedy))


# ---------------------------------------------------------------------------
# Canonicalisation
# ---------------------------------------------------------------------------


def _is_unc(raw_path: str) -> bool:
    return raw_path.startswith("\\\\") or raw_path.startswith("//")


def canonicalize_root(raw_path: str) -> Path:
    """Canonicalise a user-picked directory path for storage and later comparison.

    Raises the `workspace`-domain envelope (via `HTTPException`) for anything that is
    not an absolute, non-UNC path. See the module docstring for why relative and UNC
    paths are refused rather than coerced.
    """

    if not raw_path or not raw_path.strip():
        raise _reject(
            code="WORKSPACE_IDENTITY_INVALID",
            message="path is required",
            remedy="Submit a non-empty absolute directory path from the native picker.",
        )
    if _is_unc(raw_path):
        raise _reject(
            code="WORKSPACE_IDENTITY_INVALID",
            message=f"UNC paths are not an approved Workspace root shape: {raw_path}",
            remedy="Choose a local directory through the native picker instead of a network share.",
        )
    path = Path(raw_path)
    if not path.is_absolute():
        raise _reject(
            code="WORKSPACE_IDENTITY_INVALID",
            message=f"path must be absolute: {raw_path}",
            remedy="Submit the absolute path returned by the native directory picker.",
        )
    resolved = path.resolve(strict=False)
    if not resolved.is_dir():
        raise _reject(
            code="WORKSPACE_IDENTITY_INVALID",
            message=f"Workspace root is not an existing directory: {raw_path}",
            remedy="Choose an existing Workspace directory through the native picker.",
        )
    return resolved


def _comparison_parts(path: Path) -> tuple[str, ...]:
    parts = path.parts
    if os.name == "nt":
        return tuple(part.lower() for part in parts)
    return parts


def _is_contained(candidate: Path, root: Path) -> bool:
    """True if `candidate` equals `root` or is nested beneath it.

    Compared part-by-part (not by string prefix) so that e.g. `/root-2` is never
    mistaken for a child of `/root` -- a plain string `startswith` check has exactly
    that bug.
    """

    candidate_parts = _comparison_parts(candidate)
    root_parts = _comparison_parts(root)
    if len(candidate_parts) < len(root_parts):
        return False
    return candidate_parts[: len(root_parts)] == root_parts


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class WorkspaceRootRegistry:
    """Durable per-principal root grants backed by Backend-private SQLite."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._db_path: Path | None = None
        self._connection = sqlite3.connect(":memory:", check_same_thread=False)
        self._ensure_schema()

    def configure(self, db_path: str | Path) -> None:
        with self._lock:
            self._connection.close()
            self._db_path = Path(db_path)
            self._connection = sqlite3.connect(self._db_path, check_same_thread=False)
            self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        return self._connection

    def _ensure_schema(self) -> None:
        from app.database.lifecycle import WORKSPACE_ROOT_GRANTS_DDL

        self._connection.execute(WORKSPACE_ROOT_GRANTS_DDL)
        self._connection.commit()

    def register(self, user_id: str, raw_path: str) -> WorkspaceRootEntry:
        resolved = canonicalize_root(raw_path)
        normalized = os.path.normcase(str(resolved))
        root_id = "root_" + hashlib.sha256(f"{user_id}\0{normalized}".encode()).hexdigest()[:24]
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO workspace_root_grants "
                    "(root_id, user_id, path, created_at) VALUES (?, ?, ?, ?)",
                    (root_id, user_id, str(resolved), datetime.now(timezone.utc).isoformat()),
                )
        return WorkspaceRootEntry(root_id=root_id, path=str(resolved))

    def list_roots(self, user_id: str) -> list[WorkspaceRootEntry]:
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT root_id, path FROM workspace_root_grants WHERE user_id = ? ORDER BY created_at",
                    (user_id,),
                ).fetchall()
        return [WorkspaceRootEntry(root_id=row[0], path=row[1]) for row in rows]

    def revoke(self, user_id: str, root_id: str) -> bool:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    "DELETE FROM workspace_root_grants WHERE user_id = ? AND root_id = ?",
                    (user_id, root_id),
                )
                return cursor.rowcount > 0

    def resolve(self, user_id: str, root_id: str, relative_path: str = ".") -> Path | None:
        relative = Path(relative_path)
        if relative.is_absolute():
            return None
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT path FROM workspace_root_grants WHERE user_id = ? AND root_id = ?",
                    (user_id, root_id),
                ).fetchone()
        if row is None:
            return None
        root = Path(row[0]).resolve(strict=False)
        candidate = (root / relative).resolve(strict=False)
        return candidate if _is_contained(candidate, root) else None

    def is_within_approved_root(self, user_id: str, candidate_path: str) -> bool:
        """Return whether a path belongs to one of the principal's durable grants."""

        try:
            resolved_candidate = Path(candidate_path).resolve(strict=False)
        except (OSError, ValueError):
            return False
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT path FROM workspace_root_grants WHERE user_id = ?", (user_id,)
                ).fetchall()
        return any(_is_contained(resolved_candidate, Path(row[0])) for row in rows)


_registry = WorkspaceRootRegistry()


def get_workspace_root_registry() -> WorkspaceRootRegistry:
    """The one process-lifetime registry instance. Tests may construct their own
    `WorkspaceRootRegistry()` directly instead of going through this singleton."""

    return _registry


# ---------------------------------------------------------------------------
# HTTP surface -- exported, not wired. Router registration in `app/main.py` and any
# auth allowlisting are owned by whoever wires routers (see `app/api/capabilities.py`
# for the established pattern this module follows).
# ---------------------------------------------------------------------------


@router.post("", response_model=WorkspaceRootEntry, status_code=201)
async def register_workspace_root(body: WorkspaceRootRegisterRequest, request: Request) -> WorkspaceRootEntry:
    """Electron calls this once per launch, immediately after the native directory
    picker returns a path, before any Run commit may reference it."""

    principal = request.state.principal
    return _registry.register(principal.user_id, body.path)


@router.get("", response_model=WorkspaceRootListResponse)
async def list_workspace_roots(request: Request) -> WorkspaceRootListResponse:
    from app.api.capabilities import _CAPABILITIES

    if "local_workspace_hardlink" not in _CAPABILITIES.materialization.strategies:
        raise _reject(
            code="WORKSPACE_LOCAL_UNAVAILABLE",
            message="This Backend does not expose Client-local filesystem materialization.",
            remedy="Upload the Run manifest blobs using the blob_store strategy.",
            status_code=409,
        )
    principal = request.state.principal
    return WorkspaceRootListResponse(roots=_registry.list_roots(principal.user_id))


@router.delete("/{root_id}", status_code=204)
async def revoke_workspace_root(root_id: str, request: Request) -> None:
    principal = request.state.principal
    if not _registry.revoke(principal.user_id, root_id):
        raise _reject(
            code="WORKSPACE_ROOT_NOT_FOUND",
            message="The Workspace root capability does not exist.",
            remedy="Attach the Workspace again before running it.",
            status_code=404,
        )
