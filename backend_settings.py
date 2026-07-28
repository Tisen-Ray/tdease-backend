"""Process-wide Backend configuration and runtime inventory.

Environment variables and host probes are resolved exactly once in this module.
API handlers, workers, authentication, resource isolation, and capability
discovery consume the same frozen objects instead of independently interpreting
deployment configuration.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from typing import Literal, Mapping, MutableMapping, cast

import psutil


MIB = 1024 * 1024
AuthMode = Literal["local", "bearer"]
DeploymentMode = Literal["local", "remote"]


@dataclass(frozen=True)
class BackendSettings:
    environment: str
    deployment_mode: DeploymentMode
    auth_mode: AuthMode
    bootstrap_secret: str | None = field(repr=False)
    bind_host: str
    bind_port: int
    port_file: str | None
    backend_generation: str | None
    log_level: int
    reserved_logical_cpus: str | None
    reserved_memory_mb: str | None
    dry_run_timeout_seconds: int = 300
    log_tail_default_lines: int = 200
    log_tail_max_lines: int = 10_000


@dataclass(frozen=True)
class RuntimeInventory:
    logical_cpus: int
    total_memory_mb: int
    engine_name: Literal["snakemake"]
    engine_version: str
    execution_profile: str


@dataclass(frozen=True)
class CapabilityRegistry:
    """Explicit inventory of public behaviour implemented by this release."""

    run_definition: bool = False
    published_results: bool = True
    native_dry_run_projection: bool = True
    mutable_run_title: bool = False
    cursor_logs: bool = False
    multi_user: bool = False


def _enum_setting(
    environ: Mapping[str, str],
    name: str,
    default: str,
    allowed: set[str],
) -> str:
    value = environ.get(name, default).strip().lower()
    if value not in allowed:
        choices = " or ".join(repr(item) for item in sorted(allowed))
        raise RuntimeError(f"{name} must be {choices}")
    return value


def _port_setting(raw: str | None) -> int:
    try:
        port = int(raw or "0")
    except ValueError:
        return 0
    return port if 0 <= port <= 65_535 else 0


def load_backend_settings(
    environ: MutableMapping[str, str] | None = None,
) -> BackendSettings:
    """Parse deployment settings once; callers may inject a mapping in tests."""

    source = os.environ if environ is None else environ
    auth_mode = _enum_setting(source, "TDEASE_AUTH_MODE", "local", {"local", "bearer"})
    deployment_mode = _enum_setting(
        source,
        "TDEASE_DEPLOYMENT_MODE",
        "local",
        {"local", "remote"},
    )
    log_name = source.get("TDEASE_LOG_LEVEL", "INFO").strip().upper()
    return BackendSettings(
        environment=source.get("TDEASE_ENV", "development").strip() or "development",
        deployment_mode=cast(DeploymentMode, deployment_mode),
        auth_mode=cast(AuthMode, auth_mode),
        bootstrap_secret=source.pop("TDEASE_BOOTSTRAP_SECRET", None) or None,
        bind_host=source.get("TDEASE_BACKEND_HOST", "127.0.0.1"),
        bind_port=_port_setting(source.get("TDEASE_BACKEND_PORT")),
        port_file=source.get("TDEASE_PORT_FILE") or None,
        backend_generation=source.get("TDEASE_BACKEND_GENERATION") or None,
        log_level=getattr(logging, log_name, logging.INFO),
        reserved_logical_cpus=source.get("TDEASE_RESERVED_LOGICAL_CPUS"),
        reserved_memory_mb=source.get("TDEASE_RESERVED_MEMORY_MB"),
    )


def resolve_runtime_inventory(
    *,
    logical_cpus: int | None = None,
    total_memory_mb: int | None = None,
    engine_version: str | None = None,
) -> RuntimeInventory:
    if engine_version is None:
        try:
            engine_version = importlib_metadata.version("snakemake")
        except importlib_metadata.PackageNotFoundError:
            engine_version = "unknown"
    return RuntimeInventory(
        logical_cpus=max(1, logical_cpus if logical_cpus is not None else (os.cpu_count() or 1)),
        total_memory_mb=max(
            1,
            total_memory_mb
            if total_memory_mb is not None
            else int(psutil.virtual_memory().total // MIB),
        ),
        engine_name="snakemake",
        engine_version=engine_version,
        execution_profile="desktop-local",
    )


BACKEND_SETTINGS = load_backend_settings()
RUNTIME_INVENTORY = resolve_runtime_inventory()
CAPABILITY_REGISTRY = CapabilityRegistry()
