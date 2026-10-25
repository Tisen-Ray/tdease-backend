from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.request import urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    with (BACKEND_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


def test_version_constant_matches_pyproject() -> None:
    """Drift guard: the single in-code constant tracks the release authority."""
    from app.version import __version__

    assert __version__ == _pyproject_version()


def test_serve_starts_api_and_worker_from_json(tmp_path: Path) -> None:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "environment": "development",
                "deploymentMode": "local",
                "dataRoot": "data",
                "server": {"host": "127.0.0.1", "port": 0},
                "auth": {"mode": "local"},
                "logging": {"level": "WARNING"},
                "resources": {},
            }
        ),
        encoding="utf-8",
    )

    process = subprocess.Popen(
        [sys.executable, "-m", "cli", "serve", "--config", str(config)],
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        ready = json.loads(process.stdout.readline())
        assert ready["type"] == "ready"
        with urlopen(f"{ready['baseUrl']}/ready", timeout=10) as response:
            assert response.status == 200
            assert json.load(response)["version"] == _pyproject_version()
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode is not None
