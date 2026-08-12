"""Process-wide Backend configuration frozen from one JSON document."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Literal, Mapping, cast

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
    backend_generation: str | None
    log_level: int
    data_root: Path
    node_root: Path
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
    run_definition: bool = False
    published_results: bool = True
    native_dry_run_projection: bool = True
    mutable_run_title: bool = False
    cursor_logs: bool = False
    multi_user: bool = False


def _enum(value: object, name: str, default: str, allowed: set[str]) -> str:
    resolved = str(value if value is not None else default).strip().lower()
    if resolved not in allowed:
        choices = " or ".join(repr(item) for item in sorted(allowed))
        raise RuntimeError(f"{name} must be {choices}")
    return resolved


def _port(value: object) -> int:
    try:
        port = int(value if value is not None else 0)
    except (TypeError, ValueError):
        raise RuntimeError("server.port must be an integer") from None
    if not 0 <= port <= 65_535:
        raise RuntimeError("server.port must be between 0 and 65535")
    return port


def _object(value: object, name: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RuntimeError(f"{name} must be an object")
    return value


def _read_config(config_path: str | Path | None) -> tuple[Mapping[str, Any], Path]:
    if config_path is None:
        root = Path(__file__).resolve().parents[1] / "data" / "backend"
        return {}, root.resolve()
    source = Path(config_path).expanduser().resolve()
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuntimeError(f"Backend config not found: {source}") from None
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Backend config is invalid JSON: {source}: {exc}") from None
    if not isinstance(raw, dict):
        raise RuntimeError("Backend config root must be an object")
    if raw.get("schemaVersion") != 1:
        raise RuntimeError("Backend config schemaVersion must be 1")
    data_root_value = raw.get("dataRoot", ".")
    if not isinstance(data_root_value, str) or not data_root_value.strip():
        raise RuntimeError("dataRoot must be a non-empty path string")
    data_root = (source.parent / data_root_value).resolve()
    return raw, data_root


def load_backend_settings(
    config_path: str | Path | None = None,
    *,
    allow_env_overrides: bool = False,
    environ: Mapping[str, str] | None = None,
) -> BackendSettings:
    raw, data_root = _read_config(config_path)
    configured_node_root = raw.get("nodeRoot")
    if configured_node_root is None:
        node_root = Path(__file__).resolve().parents[1] / "nodes"
    elif isinstance(configured_node_root, str) and configured_node_root.strip():
        config_base = Path(config_path).expanduser().resolve().parent if config_path else Path.cwd()
        node_root = (config_base / configured_node_root).resolve()
    else:
        raise RuntimeError("nodeRoot must be a non-empty path string")
    server = _object(raw.get("server"), "server")
    auth = _object(raw.get("auth"), "auth")
    resources = _object(raw.get("resources"), "resources")
    logging_config = _object(raw.get("logging"), "logging")

    environment = str(raw.get("environment", "development")).strip() or "development"
    deployment = raw.get("deploymentMode", "local")
    auth_mode = auth.get("mode", "local")
    host = str(server.get("host", "127.0.0.1")).strip()
    port: object = server.get("port", 0)
    log_name = str(logging_config.get("level", "INFO")).strip().upper()
    reserved_cpus = resources.get("reservedLogicalCpus")
    reserved_memory = resources.get("reservedMemoryMb")

    source = os.environ if environ is None else environ
    if allow_env_overrides:
        environment = source.get("TDEASE_ENV", environment)
        deployment = source.get("TDEASE_DEPLOYMENT_MODE", str(deployment))
        auth_mode = source.get("TDEASE_AUTH_MODE", str(auth_mode))
        host = source.get("TDEASE_BACKEND_HOST", host)
        port = source.get("TDEASE_BACKEND_PORT", port)
        log_name = source.get("TDEASE_LOG_LEVEL", log_name).strip().upper()
        reserved_cpus = source.get("TDEASE_RESERVED_LOGICAL_CPUS", reserved_cpus)
        reserved_memory = source.get("TDEASE_RESERVED_MEMORY_MB", reserved_memory)

    return BackendSettings(
        environment=environment,
        deployment_mode=cast(DeploymentMode, _enum(deployment, "deploymentMode", "local", {"local", "remote"})),
        auth_mode=cast(AuthMode, _enum(auth_mode, "auth.mode", "local", {"local", "bearer"})),
        bootstrap_secret=None,
        bind_host=host or "127.0.0.1",
        bind_port=_port(port),
        backend_generation=None,
        log_level=getattr(logging, log_name, logging.INFO),
        data_root=data_root,
        node_root=node_root,
        reserved_logical_cpus=None if reserved_cpus is None else str(reserved_cpus),
        reserved_memory_mb=None if reserved_memory is None else str(reserved_memory),
    )


def configure_backend(
    config_path: str | Path,
    *,
    allow_env_overrides: bool = False,
) -> BackendSettings:
    global BACKEND_SETTINGS
    BACKEND_SETTINGS = load_backend_settings(
        config_path,
        allow_env_overrides=allow_env_overrides,
    )
    return BACKEND_SETTINGS


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
        total_memory_mb=max(1, total_memory_mb if total_memory_mb is not None else int(psutil.virtual_memory().total // MIB)),
        engine_name="snakemake",
        engine_version=engine_version,
        execution_profile="desktop-local",
    )


BACKEND_SETTINGS = load_backend_settings()
RUNTIME_INVENTORY = resolve_runtime_inventory()
CAPABILITY_REGISTRY = CapabilityRegistry()
