"""
Workspace root containment -- validate against *approved* roots, never a
caller-supplied one.

REMAINING-DESIGNS.md section 1 P0 "Workspace root registration", evidence:
`src/execution_runtime/storage.py` containment (`materialize_local_run_files`)
validated a submitted path against the root supplied in the *request*
itself. That makes the check meaningless -- a caller can approve its own
escape by naming a different root in the next request. Electron registers
the user-picked root with Backend after the native picker; Backend
(`app/core/workspace_roots.py`, owned by Track B2) stores approved roots per
Principal. This module owns the other half: validating a candidate path
against whatever that store currently approves, never against a value that
arrived in the same request as the path.

This module takes the approval check as an **injected callable** rather
than importing B2's store directly, for two reasons: `src/**` must not
depend on `app/**` (layering -- `app` depends on `src`, not the reverse),
and it means this containment rule is fully testable without B2's API
existing at import time. The default checker approves nothing -- fail
closed -- until something calls `set_approved_roots_checker()`.

What B2 supplies
----------------
`app/core/workspace_roots.py`'s `WorkspaceRootRegistry.is_within_approved_root`
already matches the callable shape this module expects exactly:

    (user_id: str, candidate_path: str) -> bool

True only if `candidate_path`, resolved and compared the same way a
registered root is (symlinks resolved, Windows case folded), is equal to or
nested beneath one of that Principal's approved roots. Never raises --
an unresolvable or malformed path is simply not contained.

Wiring required (owned by whoever assembles `app/main.py` -- not this
module, which must not import `app/**`):

    from app.core.workspace_roots import get_workspace_root_registry
    from src.execution_runtime.workspace_containment import set_approved_roots_checker

    set_approved_roots_checker(get_workspace_root_registry().is_within_approved_root)

And the one call site that currently invokes `materialize_local_run_files`
without a `user_id` (`app/api/runs_v2.py`, `local_workspace_hardlink`
branch) must start passing one -- `RunCommit.user_id` already carries it:

    storage.materialize_local_run_files(
        commit.run_id, Path(commit.local_workspace_root), commit.workspace_files,
        user_id=commit.user_id,
    )

Until both of those land, every local materialization call raises
`WORKSPACE_PATH_ESCAPE` -- the fail-closed default is deliberate, not a bug:
a caller-supplied root is no longer trusted, and no Principal has approved
anything until the registry is wired in and named.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional, Union

from src.contracts.enums import ErrorCode
from src.execution_runtime.errors import ExecutionError

PathLike = Union[Path, str]

# (user_id, candidate_path) -> bool. Matches
# app.core.workspace_roots.WorkspaceRootRegistry.is_within_approved_root exactly,
# so the real store can be wired in with zero adaptation.
ApprovedRootsChecker = Callable[[str, str], bool]


def default_no_roots_approved(user_id: str, candidate_path: str) -> bool:
    """Fail-closed default: nothing is approved until wired to a real store."""
    return False


def canonicalize(path: PathLike) -> Path:
    """Resolve symlinks and normalise case/separators for comparison.

    `Path.resolve()` follows symlinks (so a symlink inside an approved root
    that points outside it cannot be used to escape undetected) and
    normalises `..`/`.` segments and path separators. `strict=False`
    because the candidate may legitimately not exist yet (e.g. an output
    path about to be created); non-existent components still resolve
    syntactically, which is enough to normalise separators and collapse
    `..`.

    `os.path.normcase` additionally folds Windows case-insensitivity so
    two differently-cased spellings of the same directory compare equal,
    matching actual filesystem behaviour instead of a byte-for-byte string
    compare that would treat them as different roots.
    """
    resolved = Path(path).resolve(strict=False)
    return Path(os.path.normcase(str(resolved)))


def validate_root_containment(
    candidate: PathLike,
    user_id: Optional[str],
    checker: Optional[ApprovedRootsChecker] = None,
) -> Path:
    """Validate that `candidate` resolves inside a root approved for `user_id`.

    Canonicalises the candidate (symlinks resolved, case/separators
    normalised) before it is ever compared -- `..` is rejected only via
    that resolution, never by a pre-resolution string scan, since a literal
    `..` segment is not itself an escape (`workspace/sub/../sample.mzML`
    legitimately stays inside `workspace`); what matters is where the path
    actually points once resolved, including through a symlink that leads
    outside every approved root.

    `checker` defaults to whatever `set_approved_roots_checker` last wired
    in (or the fail-closed default). `user_id` of `None` or empty is never
    approved -- there is no Principal to check against.

    Returns the canonicalised candidate path on success. Raises
    `ExecutionError(ErrorCode.WORKSPACE_PATH_ESCAPE)` otherwise -- never
    trusts a root supplied alongside `candidate` in the same request; the
    only thing consulted is whatever the checker currently approves.
    """
    resolved_checker = checker if checker is not None else get_approved_roots_checker()
    canonical_candidate = canonicalize(candidate)
    if user_id and resolved_checker(user_id, str(canonical_candidate)):
        return canonical_candidate
    raise ExecutionError(
        ErrorCode.WORKSPACE_PATH_ESCAPE,
        f"路径解析到已批准的 Workspace 根目录之外: {candidate}",
        {"path": str(candidate)},
    )


_approved_roots_checker: ApprovedRootsChecker = default_no_roots_approved


def set_approved_roots_checker(checker: ApprovedRootsChecker) -> None:
    """Wire the real approved-roots check in. Called once at Backend startup."""
    global _approved_roots_checker
    _approved_roots_checker = checker


def get_approved_roots_checker() -> ApprovedRootsChecker:
    """The currently-wired checker (`default_no_roots_approved` until set)."""
    return _approved_roots_checker


def reset_approved_roots_checker() -> None:
    """Test-only: restore the fail-closed default checker."""
    global _approved_roots_checker
    _approved_roots_checker = default_no_roots_approved
