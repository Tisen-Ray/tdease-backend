from __future__ import annotations

import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from src.services.node_registry import (
    fetch_node_status,
    load_registry,
    parse_enrollment_string,
    registry_snapshot,
    save_registry,
    upsert_from_enrollment,
)


def make_enrollment_string(
    *,
    v: int = 1,
    url: str = "http://192.168.1.42:8731",
    node_id: str = "n_labwin2ab",
    token: str = "tok-0123456789abcdef",
    label: str | None = "lab win2",
    cert: str | None = None,
) -> str:
    payload = {"v": v, "url": url, "nodeId": node_id, "token": token}
    if label is not None:
        payload["label"] = label
    if cert is not None:
        payload["certSha256"] = cert
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return "TDEASE1-" + encoded


# ── enrollment roundtrip + upsert ────────────────────────────────────────────


def test_enrollment_roundtrip_upsert_and_persist(tmp_path) -> None:
    s = make_enrollment_string()
    parsed = parse_enrollment_string(s)
    assert parsed["nodeId"] == "n_labwin2ab"
    assert parsed["url"] == "http://192.168.1.42:8731"

    reg = upsert_from_enrollment(load_registry(tmp_path / "nodes.json"), parsed)
    # Re-pairing the same nodeId refreshes in place (url/token rotation),
    # it must not accumulate a duplicate entry.
    rotated = make_enrollment_string(url="http://192.168.1.99:8731", token="tok-rotated-0123456")
    reg = upsert_from_enrollment(reg, parse_enrollment_string(rotated))
    assert len(reg["nodes"]) == 1
    assert reg["nodes"][0]["url"] == "http://192.168.1.99:8731"

    path = tmp_path / "nodes.json"
    save_registry(path, reg)
    reloaded = load_registry(path)
    assert reloaded["nodes"][0]["nodeId"] == "n_labwin2ab"
    assert reloaded["nodes"][0]["token"] == "tok-rotated-0123456"


@pytest.mark.parametrize(
    "bad,reason",
    [
        ("http://x/whatever", "missing TDEASE1- prefix"),
        ("TDEASE1-%%%not-base64", "corrupt base64url"),
        (
            make_enrollment_string(token="short"),
            "token under 16 chars",
        ),
        (
            make_enrollment_string(url="ftp://192.168.1.42:8731"),
            "non-http(s) url",
        ),
        (
            make_enrollment_string(node_id="labwin2"),
            "nodeId without n_ prefix",
        ),
        (
            make_enrollment_string(v=2),
            "unsupported version",
        ),
    ],
)
def test_malformed_enrollment_strings_are_rejected(bad: str, reason: str) -> None:
    with pytest.raises(ValueError):
        parse_enrollment_string(bad)


# ── fetch_node_status against a real local HTTP server (stdlib) ──────────────


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/v1/health":
            self.send_response(404)
            self.end_headers()
            return
        if self.server.slow:  # type: ignore[attr-defined]
            time.sleep(2.0)
        body = json.dumps(
            {
                "node": {"id": "n_labwin2ab", "kind": "server", "protocol": 1},
                "asOf": "2026-10-25T06:00:00Z",
                "capacity": {"cpus": 8, "memoryMb": 16384, "scratchFreeMb": 4096},
                "load": {"running": 0, "queued": 0, "maxConcurrent": 1, "queueMax": 4},
                "tools": [{"id": "toppic", "version": "1.5", "isolation": "strict"}],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep pytest output clean
        pass


@pytest.fixture
def health_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.slow = False  # per-server switch read by the handler below
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    thread.join(timeout=2)


def test_fetch_node_status_success_and_bearer_header(health_server) -> None:
    seen = {}

    original = _Handler.do_GET

    def spy(self):
        seen["auth"] = self.headers.get("Authorization")
        return original(self)

    _Handler.do_GET = spy
    try:
        url = f"http://127.0.0.1:{health_server.server_port}"
        result = fetch_node_status(url, "tok-0123456789abcdef")
    finally:
        _Handler.do_GET = original

    assert result["reachable"] is True
    assert seen["auth"] == "Bearer tok-0123456789abcdef"
    assert result["status"]["capacity"]["cpus"] == 8


def test_fetch_node_status_never_raises_on_timeout(health_server) -> None:
    health_server.slow = True
    try:
        url = f"http://127.0.0.1:{health_server.server_port}"
        result = fetch_node_status(url, "tok-0123456789abcdef", timeout_seconds=0.3)
    finally:
        health_server.slow = False
    assert result["reachable"] is False
    assert result["error"]


def test_fetch_node_status_reports_unreachable_host() -> None:
    result = fetch_node_status("http://127.0.0.1:1", "tok-0123456789abcdef", timeout_seconds=0.5)
    assert result["reachable"] is False
    assert result["error"]


# ── snapshot: the local machine is always present ────────────────────────────


def test_snapshot_local_node_always_present(tmp_path, monkeypatch) -> None:
    # The local entry's tools come from the package catalog; any failure there
    # must degrade to tools=[] rather than hide the local node entirely.
    import src.services.node_registry as nr

    monkeypatch.setattr(nr, "scan_node_catalog", lambda root: ([], []))
    reg = {"nodes": []}
    snapshot = registry_snapshot(reg, {})
    assert snapshot[0]["node"] == {"id": "local", "kind": "local", "label": "This machine"}

    # With a paired server whose sample went stale+failed, the row survives
    # with the last known values and a stale flag.
    reg = upsert_from_enrollment({"nodes": []}, parse_enrollment_string(make_enrollment_string()))
    cache = {
        "n_labwin2ab": {
            "fetchedAt": time.time() - 120,
            "status": {"reachable": False, "error": "timed out"},
        }
    }
    snapshot = registry_snapshot(reg, cache)
    assert [row["node"]["id"] for row in snapshot] == ["local", "n_labwin2ab"]
    server = snapshot[1]
    assert server["stale"] is True
    assert server["reachable"] is False

    # Fresh reachable sample: capacity/load/tools carried verbatim, not stale.
    cache = {
        "n_labwin2ab": {
            "fetchedAt": time.time(),
            "status": {
                "reachable": True,
                "status": {"capacity": {"cpus": 8}, "load": {"running": 1}, "tools": []},
            },
        }
    }
    server = registry_snapshot(reg, cache)[1]
    assert server["stale"] is False
    assert server["capacity"] == {"cpus": 8}
