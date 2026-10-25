"""Hub-side node registry: the machines, as opposed to the catalog's packages.

`node_catalog` answers "which node PACKAGES are deployed here"; this module
answers "which MACHINES can this Hub see" — the local Backend itself plus any
server node paired via a one-time enrollment string (tdease-node/schema/
enrollment.schema.json). The two concepts share the word "node" and nothing
else.

The registry is a plain, git-trackable JSON file under
``data/backend/config/nodes.json``. The local machine is deliberately NOT in
the file: it is not paired, it cannot be un-paired, and writing it down would
invite someone to edit it — so it is injected as a fixed entry in code.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from src.services.node_catalog import scan_node_catalog

# ── Enrollment string parsing ────────────────────────────────────────────────
# Serialized form (enrollment.schema.json): the JSON payload, base64url-encoded
# without padding, prefixed "TDEASE1-". One paste binds url+nodeId+token (+
# optional cert fingerprint / label) at once; there is no CA and no discovery.

_ENROLLMENT_PREFIX = "TDEASE1-"
_NODE_ID_RE = re.compile(r"^n_[a-z0-9]{8,16}$")
_URL_RE = re.compile(r"^https?://\S+$")
_CERT_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

# Staleness horizon for sampled status: a node never initiates contact, so the
# Hub decides when its last answer is too old to trust. Past this age the
# snapshot keeps the last known value but flags it stale.
STALE_AFTER_SECONDS = 30.0


def parse_enrollment_string(s: str) -> dict[str, Any]:
    """Parse and validate a ``TDEASE1-…`` pairing string.

    Raises ValueError with a human-readable reason on any malformed input —
    the API layer turns that reason into the 400 body, so the message IS the
    contract here.
    """
    if not isinstance(s, str) or not s.startswith(_ENROLLMENT_PREFIX):
        raise ValueError(
            f"enrollment string must start with {_ENROLLMENT_PREFIX!r}"
        )
    encoded = s[len(_ENROLLMENT_PREFIX) :]
    try:
        # validate=False keeps us liberal in what we accept (unpadded input);
        # the JSON round-trip below is the real gate.
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"enrollment payload is not valid base64url JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("enrollment payload must be a JSON object")

    if payload.get("v") != 1:
        raise ValueError(f"unsupported enrollment version: {payload.get('v')!r}")
    url = payload.get("url")
    if not isinstance(url, str) or not _URL_RE.match(url) or len(url) > 256:
        raise ValueError(f"enrollment url must be http(s) and <=256 chars: {url!r}")
    node_id = payload.get("nodeId")
    if not isinstance(node_id, str) or not _NODE_ID_RE.match(node_id):
        raise ValueError(f"enrollment nodeId must match n_[a-z0-9]{{8,16}}: {node_id!r}")
    token = payload.get("token")
    if not isinstance(token, str) or not (16 <= len(token) <= 128):
        raise ValueError("enrollment token must be 16-128 chars")
    cert = payload.get("certSha256")
    if cert is not None and (
        not isinstance(cert, str) or not _CERT_SHA256_RE.match(cert)
    ):
        raise ValueError(f"enrollment certSha256 must be 64 lowercase hex chars: {cert!r}")
    label = payload.get("label")
    if label is not None and (not isinstance(label, str) or len(label) > 64):
        raise ValueError("enrollment label must be <=64 chars")

    return {
        "v": 1,
        "url": url,
        "nodeId": node_id,
        "token": token,
        "certSha256": cert,
        "label": label,
    }


# ── Registry file ────────────────────────────────────────────────────────────


def load_registry(path: Path) -> dict[str, Any]:
    """Load ``{"nodes": [...]}``; a missing file is an empty registry, not an
    error — a fresh install has paired nothing yet and must still boot."""
    path = Path(path)
    if not path.exists():
        return {"nodes": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list):
        raise ValueError(f"registry file is malformed (expected nodes list): {path}")
    return data


def save_registry(path: Path, reg: dict[str, Any]) -> None:
    """Persist the registry; the file is git-tracked, so keep it human-readable."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def upsert_from_enrollment(reg: dict[str, Any], enrollment: dict[str, Any]) -> dict[str, Any]:
    """Insert or refresh a server node from a parsed enrollment.

    Re-pairing the same nodeId (a node whose address or token rotated) updates
    the existing entry in place rather than accumulating a duplicate — the
    nodeId is the machine's identity, not an append-only log entry.
    """
    node_id = enrollment["nodeId"]
    entry = {
        "nodeId": node_id,
        "label": enrollment.get("label"),
        "url": enrollment["url"],
        "token": enrollment["token"],
        "certSha256": enrollment.get("certSha256"),
    }
    nodes = reg.setdefault("nodes", [])
    for i, existing in enumerate(nodes):
        if existing.get("nodeId") == node_id:
            nodes[i] = entry
            break
    else:
        nodes.append(entry)
    return reg


# ── Status sampling ──────────────────────────────────────────────────────────


def fetch_node_status(
    url: str, token: str, timeout_seconds: float = 2.5
) -> dict[str, Any]:
    """GET ``<url>/v1/health`` with the node's bearer token.

    Never raises and never blocks past ``timeout_seconds``: a status plane that
    can take the Hub down with it is worse than no status plane. The node's
    answer is returned verbatim under ``status`` — the Hub stamps its own
    ``asOf`` at snapshot time and does not trust the node's clock.
    """
    try:
        request = urllib.request.Request(
            url.rstrip("/") + "/v1/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
        return {"reachable": True, "status": body}
    except Exception as exc:  # noqa: BLE001 — by contract: report, don't raise
        return {"reachable": False, "error": str(exc)}


def _local_tools() -> list[dict[str, Any]]:
    """Project the local node's tools from the deployed package catalog.

    Best-effort by design: the status plane must not fail because a package is
    malformed — that is the catalog's error to report, not a reason to hide
    the local node. Whatever the scan can't produce becomes ``tools: []``.
    """
    try:
        from src.execution_runtime.storage import get_tools_root

        nodes, _errors = scan_node_catalog(get_tools_root())
        return [
            {"id": node["id"], "version": node["version"], "isolation": "strict"}
            for node in nodes
        ]
    except Exception:
        return []


def registry_snapshot(
    reg: dict[str, Any],
    cache: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Project the unified status plane: local entry first, then every server.

    ``cache`` maps nodeId -> {"fetchedAt": epoch, "status": dict} and is owned
    by the caller (the API layer) so sampling state survives across requests
    without this module holding globals. A server entry carries the node's last
    reported status with the Hub-stamped ``asOf``; when the sample is older
    than STALE_AFTER_SECONDS the last known value is kept but flagged
    ``stale: true`` — "machine went quiet" is information, not a reason to
    drop the row.
    """
    snapshot: list[dict[str, Any]] = [
        {
            "node": {"id": "local", "kind": "local", "label": "This machine"},
            "asOf": _iso_now(),
            "tools": _local_tools(),
        }
    ]
    now = time.time()
    for entry in reg.get("nodes", []):
        node_id = entry.get("nodeId", "")
        sampled = cache.get(node_id)
        row: dict[str, Any] = {
            "node": {
                "id": node_id,
                "kind": "server",
                "label": entry.get("label"),
                "protocol": 1,
            },
            "url": entry.get("url"),
        }
        if sampled:
            age = now - sampled["fetchedAt"]
            row["asOf"] = _iso_from_epoch(sampled["fetchedAt"])
            row["reachable"] = bool(sampled["status"].get("reachable"))
            row["stale"] = age > STALE_AFTER_SECONDS and not row["reachable"]
            status = sampled["status"]
            if status.get("reachable"):
                # Carry the node's own report (capacity/load/tools) verbatim.
                for key in ("capacity", "load", "tools"):
                    if key in status.get("status", {}):
                        row[key] = status["status"][key]
            else:
                row["error"] = status.get("error")
        else:
            row["reachable"] = False
            row["stale"] = True
            row["error"] = "never sampled"
        snapshot.append(row)
    return snapshot


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iso_from_epoch(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))
