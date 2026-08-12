from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.backend_settings import load_backend_settings, resolve_runtime_inventory
from src.execution_runtime.execution import backend_child_env


def write_config(tmp_path, **overrides):
    value = {
        "schemaVersion": 1,
        "environment": "production",
        "deploymentMode": "remote",
        "dataRoot": "runtime",
        "server": {"host": "127.0.0.2", "port": 43123},
        "auth": {"mode": "bearer"},
        "logging": {"level": "WARNING"},
        "resources": {"reservedLogicalCpus": 3, "reservedMemoryMb": 4096},
    }
    value.update(overrides)
    target = tmp_path / "backend.json"
    target.write_text(json.dumps(value), encoding="utf-8")
    return target


def test_settings_are_frozen_from_one_json_document(tmp_path) -> None:
    config = write_config(tmp_path)
    settings = load_backend_settings(config)

    assert settings.environment == "production"
    assert settings.deployment_mode == "remote"
    assert settings.auth_mode == "bearer"
    assert settings.bootstrap_secret is None
    assert settings.bind_host == "127.0.0.2"
    assert settings.bind_port == 43123
    assert settings.log_level == logging.WARNING
    assert settings.data_root == (tmp_path / "runtime").resolve()
    assert settings.node_root == (Path(__file__).resolve().parents[1] / "nodes").resolve()
    assert settings.reserved_logical_cpus == "3"
    assert settings.reserved_memory_mb == "4096"


def test_environment_is_ignored_without_explicit_development_opt_in(tmp_path) -> None:
    config = write_config(tmp_path)
    environ = {"TDEASE_BACKEND_PORT": "54321", "TDEASE_ENV": "development"}

    production = load_backend_settings(config, environ=environ)
    development = load_backend_settings(config, allow_env_overrides=True, environ=environ)

    assert production.bind_port == 43123
    assert production.environment == "production"
    assert development.bind_port == 54321
    assert development.environment == "development"


@pytest.mark.parametrize(
    "overrides",
    [
        {"schemaVersion": 2},
        {"deploymentMode": "desktop-ish"},
        {"auth": {"mode": "maybe"}},
        {"server": {"port": "not-a-port"}},
        {"nodeRoot": ""},
    ],
)
def test_invalid_configuration_fails_at_startup(tmp_path, overrides) -> None:
    with pytest.raises(RuntimeError):
        load_backend_settings(write_config(tmp_path, **overrides))


def test_runtime_inventory_is_a_frozen_explicit_snapshot() -> None:
    inventory = resolve_runtime_inventory(
        logical_cpus=12,
        total_memory_mb=24_576,
        engine_version="9.test",
    )
    assert inventory.logical_cpus == 12
    assert inventory.total_memory_mb == 24_576
    assert inventory.engine_name == "snakemake"
    assert inventory.engine_version == "9.test"
    assert inventory.execution_profile == "desktop-local"


def test_workflow_children_receive_no_tdease_environment(monkeypatch) -> None:
    monkeypatch.setenv("TDEASE_UNKNOWN_SECRET", "must-not-leak")
    monkeypatch.setenv("PATH", "managed-path")
    child = backend_child_env()
    assert child["PATH"] == "managed-path"
    assert not any(name.startswith("TDEASE_") for name in child)
