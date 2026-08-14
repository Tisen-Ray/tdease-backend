"""Capability-discovery wire models — transport.

Pure Pydantic wire shapes; no behaviour. The field-level contract lives in
`docs/spec/CAPABILITIES.md`; resolution and the frozen `_CAPABILITIES` singleton
live in `app/api/capabilities.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

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
    max_memory_mb: int
    total_logical_cpus: int
    reserved_service_cpus: int
    total_memory_mb: int
    reserved_service_memory_mb: int
    max_concurrent_runs: Literal[1]
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

    protocol_version: Literal[3]
    auth: AuthCapability
    materialization: MaterializationCapability
    limits: LimitsCapability
    engine: EngineCapability
    features: FeatureCapability
    multi_user: bool
