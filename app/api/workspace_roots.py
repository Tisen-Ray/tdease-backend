"""Workspace-root capability HTTP surface — transport.

Wire schemas and routes only. The durable registry and root canonicalisation live
in `src/services/workspace_roots.py` (domain); this module constructs the wire
models from the registry's plain return values and raises the failure-contract
`TDEaseError` for the transport-level rejections.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.workspace_roots import (
    WorkspaceRootEntry,
    WorkspaceRootListResponse,
    WorkspaceRootRegisterRequest,
)
from src.contracts.errors import ErrorCode, TDEaseError
from src.services.workspace_roots import get_workspace_root_registry

router = APIRouter(prefix="/api/workspace-roots", tags=["workspace-roots"])


@router.post("", response_model=WorkspaceRootEntry, status_code=201)
async def register_workspace_root(body: WorkspaceRootRegisterRequest, request: Request) -> WorkspaceRootEntry:
    """Electron calls this once per launch, immediately after the native directory
    picker returns a path, before any Run commit may reference it."""

    principal = request.state.principal
    root_id, path = get_workspace_root_registry().register(principal.user_id, body.path)
    return WorkspaceRootEntry(root_id=root_id, path=path)


@router.get("", response_model=WorkspaceRootListResponse)
async def list_workspace_roots(request: Request) -> WorkspaceRootListResponse:
    from app.api.capabilities import _CAPABILITIES

    if "local_workspace_hardlink" not in _CAPABILITIES.materialization.strategies:
        # The requested materialization strategy is not among this Backend's resolved
        # capabilities -- the same `run`-domain code the Run submission path uses for
        # an identical shape mismatch (RUN_MODE_MISMATCH, run domain -> 409).
        raise TDEaseError(
            code=ErrorCode.RUN_MODE_MISMATCH,
            message="This Backend does not expose Client-local filesystem materialization.",
            remedy="Upload the Run manifest blobs using the blob_store strategy.",
            retryable=False,
        )
    principal = request.state.principal
    return WorkspaceRootListResponse(
        roots=[WorkspaceRootEntry(root_id=root_id, path=path)
               for root_id, path in get_workspace_root_registry().list_roots(principal.user_id)]
    )


@router.delete("/{root_id}", status_code=204)
async def revoke_workspace_root(root_id: str, request: Request) -> None:
    principal = request.state.principal
    if not get_workspace_root_registry().revoke(principal.user_id, root_id):
        # A root_id that resolves to no registered Workspace for this Principal is
        # indistinguishable from an absent one (WORKSPACE_NOT_FOUND, 404).
        raise TDEaseError(
            code=ErrorCode.WORKSPACE_NOT_FOUND,
            message="The Workspace root capability does not exist.",
            remedy="Attach the Workspace again before running it.",
            retryable=False,
        )
