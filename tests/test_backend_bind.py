"""Backend public CLI bind contract.

The CLI no longer pre-probes a port: `_select_port` is gone because a probe
binds, closes, and then races the real bind. uvicorn binds the configured port,
`0` means the OS assigns one, and the ready line reports the port actually
bound. These tests pin the three properties the probe used to protect — no
hardcoded port, an explicit port honoured, an occupied port fails closed —
against the current surface.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

from src.backend_settings import load_backend_settings

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path: Path, port: int) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "schemaVersion": 1,
        "environment": "test",
        "deploymentMode": "local",
        "dataRoot": ".",
        "nodeRoot": str(tmp_path / "nodes"),
        "server": {"host": "127.0.0.1", "port": port},
        "auth": {"mode": "local"},
        "logging": {"level": "INFO"},
        "resources": {},
    }), encoding="utf-8")
    return path


def test_default_port_is_os_assigned(tmp_path: Path) -> None:
    assert load_backend_settings(_config(tmp_path, 0)).bind_port == 0


def test_explicit_port_is_honoured(tmp_path: Path) -> None:
    assert load_backend_settings(_config(tmp_path, 54321)).bind_port == 54321


def test_occupied_port_fails_closed(tmp_path: Path) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        occupied = int(holder.getsockname()[1])
        completed = subprocess.run(
            [sys.executable, "-m", "cli", "serve", "--config", str(_config(tmp_path, occupied))],
            cwd=BACKEND_ROOT, capture_output=True, text=True, timeout=120, check=False,
        )

    assert '"type":"ready"' not in completed.stdout, "a busy port must never report ready"
    assert completed.returncode != 0, completed.stdout + completed.stderr
