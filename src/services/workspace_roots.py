"""Durable, per-principal capabilities for Desktop-local Workspace roots — domain.

An absolute path crosses the public boundary only when the Desktop Client attaches a
directory. Later Run requests name the opaque ``root_id`` and a relative Run path;
they cannot assert their own filesystem authorization boundary. Grants live in
Backend-private SQLite state so a Backend restart does not invalidate an open
Workspace. Server/blob deployments never use this capability.

This is the `src/` (domain) half: the registry and the root canonicalisation. The
HTTP surface that exposes it (`app/api/workspace_roots.py`) owns the wire schemas
and the `TDEaseError` raises. The containment rule that validates a candidate path
against these grants lives alongside the engine in
`src/execution_runtime/workspace_containment.py`, which receives the approval check
here as an injected callable (see that module's docstring).

This module must not import FastAPI or `app/**` — `src/` never depends on `app/`
(docs/design/THREE-REPOSITORY-ARCHITECTURE.md §4.1). It owns its own table DDL;
`app/database/lifecycle.py` applies the same DDL at migration time by importing it
from here.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from src.contracts.errors import ErrorCode, TDEaseError

WORKSPACE_ROOT_GRANTS_DDL = """
    CREATE TABLE IF NOT EXISTS workspace_root_grants (
        root_id     TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        path        TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        UNIQUE(user_id, path)
    )
"""


def _is_unc(raw_path: str) -> bool:
    return raw_path.startswith(("\\\\", "//"))


def canonicalize_root(raw_path: str) -> Path:
    """Canonicalise a user-picked directory path for storage and later comparison.

    Refuses anything that is not an absolute, non-UNC path — raising the
    `workspace`-domain `WORKSPACE_IDENTITY_INVALID` error directly (a domain raise
    site speaks the contract error). See the module docstring for why relative and
    UNC paths are refused rather than coerced.
    """

    if not raw_path or not raw_path.strip():
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_IDENTITY_INVALID,
            message="path is required",
            remedy="Submit a non-empty absolute directory path from the native picker.",
            retryable=False,
        )
    if _is_unc(raw_path):
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_IDENTITY_INVALID,
            message=f"UNC paths are not an approved Workspace root shape: {raw_path}",
            remedy="Choose a local directory through the native picker instead of a network share.",
            retryable=False,
        )
    path = Path(raw_path)
    if not path.is_absolute():
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_IDENTITY_INVALID,
            message=f"path must be absolute: {raw_path}",
            remedy="Submit the absolute path returned by the native directory picker.",
            retryable=False,
        )
    resolved = path.resolve(strict=False)
    if not resolved.is_dir():
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_IDENTITY_INVALID,
            message=f"Workspace root is not an existing directory: {raw_path}",
            remedy="Choose an existing Workspace directory through the native picker.",
            retryable=False,
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
        self._connection.execute(WORKSPACE_ROOT_GRANTS_DDL)
        self._connection.commit()

    def register(self, user_id: str, raw_path: str) -> tuple[str, str]:
        """Register an approved root; returns (root_id, canonical_path)."""

        resolved = canonicalize_root(raw_path)
        normalized = os.path.normcase(str(resolved))
        root_id = (
            "root_"
            + hashlib.sha256(f"{user_id}\0{normalized}".encode()).hexdigest()[:24]
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO workspace_root_grants "
                "(root_id, user_id, path, created_at) VALUES (?, ?, ?, ?)",
                (root_id, user_id, str(resolved), datetime.now(UTC).isoformat()),
            )
        return root_id, str(resolved)

    def list_roots(self, user_id: str) -> list[tuple[str, str]]:
        """List (root_id, path) grants for a principal, oldest first."""

        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT root_id, path FROM workspace_root_grants WHERE user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def revoke(self, user_id: str, root_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM workspace_root_grants WHERE user_id = ? AND root_id = ?",
                (user_id, root_id),
            )
            return cursor.rowcount > 0

    def resolve(
        self, user_id: str, root_id: str, relative_path: str = "."
    ) -> Path | None:
        relative = Path(relative_path)
        if relative.is_absolute():
            return None
        with self._lock, self._connect() as conn:
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
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT path FROM workspace_root_grants WHERE user_id = ?", (user_id,)
            ).fetchall()
        return any(_is_contained(resolved_candidate, Path(row[0])) for row in rows)


_registry = WorkspaceRootRegistry()


def get_workspace_root_registry() -> WorkspaceRootRegistry:
    """The one process-lifetime registry instance. Tests may construct their own
    `WorkspaceRootRegistry()` directly instead of going through this singleton."""

    return _registry


def configure_workspace_root_runtime(db_path: str | Path) -> None:
    """Wire the durable root registry into every Backend process.

    The API and the worker are separate processes. Keeping this bootstrap
    beside the registry prevents one process from silently using the in-memory
    fail-closed default while the other uses SQLite-backed grants.
    """
    registry = get_workspace_root_registry()
    registry.configure(db_path)
    from src.execution_runtime.workspace_containment import set_approved_roots_checker

    set_approved_roots_checker(
        lambda user_id, candidate_path: registry.is_within_approved_root(
            user_id, candidate_path
        )
    )
