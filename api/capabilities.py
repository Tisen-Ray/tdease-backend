"""Backend capability discovery — `GET /api/capabilities`.

The field-level contract lives in `docs/spec/CAPABILITIES.md`; this module is the
code half of that contract and must match it field for field
(`tests/test_capabilities.py` asserts the correspondence).

Resolution happens exactly once, at import time (process startup). No request
handler in this module reads an environment variable, touches the filesystem, or
queries installed package metadata — the cached `_CAPABILITIES` instance is the only
thing ever returned. Restarting the process is the only way the document changes.

This module intentionally does not wire itself into the app: it exports `router`
only. Router registration (`app/main.py`) and the auth public-path allowlist
(`app/core/auth.py::PUBLIC_PATHS`) are owned by the agent responsible for wiring
(see `docs/spec/CAPABILITIES.md` §3): `GET /api/capabilities` must be reachable
without a Bearer token or a bootstrap deadlock results.
"""

from __future__ import annotations

import os
from importlib import metadata as importlib_metadata
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

# Bump only for a breaking change (removed/renamed/retyped field, changed field
# meaning, narrowed limit). Additive changes never bump this. See
# docs/spec/CAPABILITIES.md §5.
PROTOCOL_VERSION = 1

MaterializationStrategy = Literal["local_workspace_hardlink", "blob_store"]


class AuthCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    scheme: Literal["none", "bearer"]
    bootstrap: Literal["desktop"] | None


class MaterializationCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategies: tuple[MaterializationStrategy, ...]


class LimitsCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_cores: int
    dry_run_timeout_seconds: int
    log_tail_default_lines: int
    log_tail_max_lines: int


class EngineCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    execution_profile: str


class FeatureCapability(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_definition: bool
    published_results: bool
    native_dry_run_projection: bool
    mutable_run_title: bool
    cursor_logs: bool


class CapabilitiesResponse(BaseModel):
    """The frozen Backend capability document. See docs/spec/CAPABILITIES.md."""

    model_config = ConfigDict(frozen=True)

    protocol_version: int
    auth: AuthCapability
    materialization: MaterializationCapability
    limits: LimitsCapability
    engine: EngineCapability
    features: FeatureCapability
    multi_user: bool


def _resolve_engine_version() -> str:
    try:
        return importlib_metadata.version("snakemake")
    except importlib_metadata.PackageNotFoundError:
        return "unknown"


def _resolve_materialization_strategies() -> tuple[MaterializationStrategy, ...]:
    # Resolved once at startup, never at request time (M0 grep gate; also
    # docs/spec/CAPABILITIES.md §7, which removes this same read from
    # app/api/runs_v2.py's request handlers).
    mode = os.environ.get("TDEASE_DEPLOYMENT_MODE", "local").strip().lower()
    if mode == "local":
        return ("local_workspace_hardlink",)
    return ("blob_store",)


def _has_published_results() -> bool:
    """Derived from the contract, never declared.

    The Client branches on this flag to show or hide the Published Results panel
    (docs/spec/CAPABILITIES.md: "`false`/absent: results are only reachable as raw
    run files"). A hardcoded `True` here is not an optimistic default -- it makes
    the Client render a panel the Backend cannot fill, and it did: this returned
    `True` while `RunCommit` had no `result_specs`, there was no `/results` route,
    and the Client gateway threw `UnsupportedBackendCapabilityError`.

    Deriving it from the commit contract means the flag flips itself the moment
    Published Results actually land, and cannot drift in either direction.
    """
    from src.contracts.run import RunCommit

    return "result_specs" in RunCommit.model_fields


def _has_run_definition() -> bool:
    """Same rule as `_has_published_results`, applied to the Run definition view.

    This was the last hardcoded `True` in this document. It claimed the Backend
    could serve a Run's definition while no route existed to serve one -- the
    Client's `getRunDefinition` throws `UnsupportedBackendCapabilityError`
    unconditionally, which is the honest half of a contradiction the flag was
    telling the other half of.

    Derived from the response contract rather than the router, for the same
    reason the two helpers around it are: `app.api.runs_v2` already imports this
    module, so reaching back into it would be a circular import. A Run
    definition the Backend can serve is one it can *describe*, so the presence
    of the response model is the honest test.
    """
    import src.contracts.run as run_contracts

    return hasattr(run_contracts, "RunDefinitionResponse")


def _has_native_dry_run_projection() -> bool:
    """Same rule: true only when the dry-run response can actually carry a
    structured projection instead of engine text. Today `RunDryRunResponse` is
    `{valid, exit_code, engine, output}` -- text only -- so this is false, and the
    Client correctly renders preformatted output rather than a DAG."""
    from src.contracts.run import RunDryRunResponse

    return "projection" in RunDryRunResponse.model_fields


def _build_capabilities() -> CapabilitiesResponse:
    auth_mode = os.environ.get("TDEASE_AUTH_MODE", "local").strip().lower()
    return CapabilitiesResponse(
        protocol_version=PROTOCOL_VERSION,
        auth=AuthCapability(
            scheme="bearer" if auth_mode == "bearer" else "none",
            bootstrap="desktop" if auth_mode == "bearer" else None,
        ),
        materialization=MaterializationCapability(
            strategies=_resolve_materialization_strategies(),
        ),
        limits=LimitsCapability(
            max_cores=256,
            dry_run_timeout_seconds=300,
            log_tail_default_lines=200,
            log_tail_max_lines=10000,
        ),
        engine=EngineCapability(
            name="snakemake",
            version=_resolve_engine_version(),
            execution_profile="desktop-local",
        ),
        features=FeatureCapability(
            run_definition=_has_run_definition(),
            published_results=_has_published_results(),
            native_dry_run_projection=_has_native_dry_run_projection(),
            mutable_run_title=False,
            cursor_logs=False,
        ),
        multi_user=False,
    )


# Resolved once, at import time. Every request returns this same instance.
_CAPABILITIES: CapabilitiesResponse = _build_capabilities()


router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilitiesResponse)
async def get_capabilities() -> CapabilitiesResponse:
    """Return the frozen Backend capability document.

    Unauthenticated by design (docs/spec/CAPABILITIES.md §3): the document
    describes how to authenticate, so requiring authentication to read it would be
    a bootstrap deadlock. It carries no secret and no user data.
    """
    return _CAPABILITIES
