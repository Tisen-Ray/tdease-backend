"""Backend capability discovery — `GET /api/capabilities`.

The field-level contract lives in `docs/spec/CAPABILITIES.md`; this module is the
code half of that contract and must match it field for field
(`tests/test_capabilities.py` asserts the correspondence).

Resolution happens exactly once from the process-wide `BackendSettings`,
`RuntimeInventory`, `CapabilityRegistry`, and `ResourceBudget`. No request handler
reads deployment state; the cached `_CAPABILITIES` instance is the only thing ever
returned. Restarting the process is the only way the document changes.

This module intentionally does not wire itself into the app: it exports `router`
only. Router registration (`app/main.py`) and the auth public-path allowlist
(`app/auth.py::PUBLIC_PATHS`) are owned by the agent responsible for wiring
(see `docs/spec/CAPABILITIES.md` §3): `GET /api/capabilities` must be reachable
without a Bearer token or a bootstrap deadlock results.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from app.schemas.capabilities import (
    AuthCapability,
    CapabilitiesResponse,
    EngineCapability,
    FeatureCapability,
    LimitsCapability,
    MaterializationCapability,
    MaterializationStrategy,
)
from src.backend_settings import (
    BACKEND_SETTINGS,
    CAPABILITY_REGISTRY,
    RUNTIME_INVENTORY,
    BackendSettings,
    CapabilityRegistry,
    RuntimeInventory,
)
from src.execution_runtime.resource_budget import RESOURCE_BUDGET, ResourceBudget

# Bump only for a breaking change (removed/renamed/retyped field, changed field
# meaning, narrowed limit). Additive changes never bump this. See
# docs/spec/CAPABILITIES.md §5.
PROTOCOL_VERSION: Literal[3] = 3


def build_capabilities(
    settings: BackendSettings,
    inventory: RuntimeInventory,
    registry: CapabilityRegistry,
    budget: ResourceBudget,
) -> CapabilitiesResponse:
    strategies: tuple[MaterializationStrategy, ...] = (
        ("local_workspace_hardlink",)
        if settings.deployment_mode == "local"
        else ("blob_store",)
    )
    return CapabilitiesResponse(
        protocol_version=PROTOCOL_VERSION,
        auth=AuthCapability(
            scheme="bearer" if settings.auth_mode == "bearer" else "none",
            bootstrap="desktop" if settings.auth_mode == "bearer" else None,
        ),
        materialization=MaterializationCapability(strategies=strategies),
        limits=LimitsCapability(
            max_cores=budget.compute_cpus,
            max_memory_mb=budget.compute_memory_mb,
            total_logical_cpus=budget.logical_cpus,
            reserved_service_cpus=budget.reserved_service_cpus,
            total_memory_mb=budget.total_memory_mb,
            reserved_service_memory_mb=budget.reserved_service_memory_mb,
            max_concurrent_runs=budget.max_concurrent_runs,
            dry_run_timeout_seconds=settings.dry_run_timeout_seconds,
            log_tail_default_lines=settings.log_tail_default_lines,
            log_tail_max_lines=settings.log_tail_max_lines,
        ),
        engine=EngineCapability(
            name=inventory.engine_name,
            version=inventory.engine_version,
            execution_profile=inventory.execution_profile,
        ),
        features=FeatureCapability(
            run_definition=registry.run_definition,
            published_results=registry.published_results,
            native_dry_run_projection=registry.native_dry_run_projection,
            mutable_run_title=registry.mutable_run_title,
            cursor_logs=registry.cursor_logs,
        ),
        multi_user=registry.multi_user,
    )


# Resolved once at process startup. Every request returns this same instance.
_CAPABILITIES: CapabilitiesResponse = build_capabilities(
    BACKEND_SETTINGS,
    RUNTIME_INVENTORY,
    CAPABILITY_REGISTRY,
    RESOURCE_BUDGET,
)


router = APIRouter(prefix="/api/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilitiesResponse)
async def get_capabilities() -> CapabilitiesResponse:
    """Return the frozen Backend capability document.

    Unauthenticated by design (docs/spec/CAPABILITIES.md §3): the document
    describes how to authenticate, so requiring authentication to read it would be
    a bootstrap deadlock. It carries no secret and no user data.
    """
    return _CAPABILITIES
