"""Per-Principal registered Workspace roots -- Desktop filesystem authorization.

`DESKTOP-FIRST-DEPLOYMENT.md` section 5 and `REMAINING-DESIGNS.md` P0 "Workspace root
registration":

    containment in `src/execution_runtime/storage.py:377-385` validates against the
    root supplied in the request, not a previously approved root.

That is a caller asserting its own boundary, not containment. This module is the half
of the fix that Electron and the registration endpoint own: the user picks a directory
through the native picker, Electron registers the resolved root with the Backend
*once per launch*, and every later Run commit's `local_workspace_root` must resolve
beneath a root this module already approved for that Principal -- never against a
value the commit itself asserts.

The other half -- making `storage.materialize_local_run_files` (and any other
containment check in `src/execution_runtime/storage.py`) call the lookup function
below instead of trusting `commit.local_workspace_root` directly -- is owned by
another agent (`src/execution_runtime/**` is out of scope here). The exact interface
that agent must call is `is_within_approved_root`, restated on the registry class
below and in the B2 agent report.

Decisions stated here, not left implicit:

- A **relative path is rejected**. Electron's native picker always returns an
  absolute path; a relative one has no stable meaning across the Electron process's
  cwd and the Backend's own cwd, so there is no ambiguous "resolve against some base"
  fallback -- it is refused outright.
- A **UNC path is rejected** (`\\\\host\\share\\...` or POSIX `//host/share/...`).
  Desktop Workspace roots are local-machine directories; a UNC path is a network
  location with different identity, availability and permission semantics that this
  design does not cover yet (`DESKTOP-FIRST-DEPLOYMENT.md` section 8 defers remote
  storage transports). This may be revisited explicitly if a future release needs it;
  it is not silently allowed today.
- **Symlinks and junctions are resolved** (`Path.resolve()`) before a root is stored,
  so containment comparisons always compare real paths. Otherwise a symlink could be
  registered, approved, and then swapped to point somewhere else after registration --
  a TOCTOU-shaped bypass of the very containment this module exists to provide.
- **Windows paths are compared case-insensitively** (NTFS is case-insensitive,
  case-preserving), but the stored/displayed path keeps the resolved casing so
  registration output stays readable; only the *comparison key* is case-folded.

Storage is process-lifetime and in-memory. Electron re-registers the root on every
Desktop launch (`DESKTOP-FIRST-DEPLOYMENT.md` section 5 step 2), so no on-disk
persistence is required for the current single-process Desktop release; a future
Server would replace this in-memory dict with a per-tenant persistent store without
changing the public interface below.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
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
    return path.resolve(strict=False)


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


@dataclass
class _PrincipalRoots:
    by_id: dict[str, Path] = field(default_factory=dict)

    def add(self, resolved: Path) -> str:
        target_key = _comparison_parts(resolved)
        for root_id, existing in self.by_id.items():
            if _comparison_parts(existing) == target_key:
                return root_id
        root_id = f"root-{len(self.by_id) + 1}"
        self.by_id[root_id] = resolved
        return root_id


class WorkspaceRootRegistry:
    """Process-lifetime, per-Principal registered Workspace root store."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._principals: dict[str, _PrincipalRoots] = {}

    def register(self, user_id: str, raw_path: str) -> WorkspaceRootEntry:
        resolved = canonicalize_root(raw_path)
        with self._lock:
            roots = self._principals.setdefault(user_id, _PrincipalRoots())
            root_id = roots.add(resolved)
        return WorkspaceRootEntry(root_id=root_id, path=str(resolved))

    def list_roots(self, user_id: str) -> list[WorkspaceRootEntry]:
        with self._lock:
            roots = self._principals.get(user_id)
            if not roots:
                return []
            return [
                WorkspaceRootEntry(root_id=root_id, path=str(path))
                for root_id, path in roots.by_id.items()
            ]

    def is_within_approved_root(self, user_id: str, candidate_path: str) -> bool:
        """The lookup function `src/execution_runtime/storage.py` must call.

        Stable signature for the other agent's integration:

            is_within_approved_root(user_id: str, candidate_path: str) -> bool

        Returns True only if `candidate_path`, resolved the same way a registered
        root is (symlinks resolved, Windows-case-folded for comparison), is equal to
        or nested beneath one of that Principal's registered roots. `storage.py`'s
        `materialize_local_run_files` (and any other place that currently trusts
        `commit.local_workspace_root` at storage.py:377-385) must call this instead
        of validating against the value the request itself supplies -- that is the
        exact defect this registry replaces.

        Never raises: an unresolvable or malformed `candidate_path` is simply not
        contained (`False`), so callers do not need a second exception-handling path
        for containment checks specifically.
        """

        try:
            resolved_candidate = Path(candidate_path).resolve(strict=False)
        except (OSError, ValueError):
            return False
        with self._lock:
            roots = self._principals.get(user_id)
            if not roots:
                return False
            return any(_is_contained(resolved_candidate, root) for root in roots.by_id.values())

    def all_roots(self) -> list[Path]:
        """Every root registered for every Principal, flattened.

        Desktop currently has exactly one Principal (`local-owner`), so this is
        that Principal's roots today. Diagnostic/introspection use only (e.g. a
        future admin surface listing every approved root); the containment check
        `src/execution_runtime/workspace_containment.py` actually calls is
        `is_within_approved_root`, not this method -- see that method's
        docstring for the stable wiring contract.
        """
        with self._lock:
            return [path for roots in self._principals.values() for path in roots.by_id.values()]


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
    principal = request.state.principal
    return WorkspaceRootListResponse(roots=_registry.list_roots(principal.user_id))
