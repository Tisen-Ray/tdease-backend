"""Read-only projection of executable node packages deployed on this server,
plus the machine registry / unified status plane (local + paired server nodes).

Two "node" concepts, deliberately distinct:
- the catalog routes ("", "/{node_id}") project node PACKAGES (capabilities);
- /status and /enroll project MACHINES (src/services/node_registry.py).
Fixed segments are declared BEFORE /{node_id}: FastAPI matches routes in
declaration order, and a later "/status" would be eaten by node_id="status".
"""
import threading
import time

from fastapi import APIRouter
from pydantic import BaseModel

from src.execution_runtime.storage import get_tools_root
from src.services.node_catalog import scan_node_catalog
from src.services.node_registry import (
    fetch_node_status,
    load_registry,
    parse_enrollment_string,
    registry_snapshot,
    save_registry,
    upsert_from_enrollment,
)
from src.contracts.errors import ErrorCode, TDEaseError

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
async def list_nodes():
    # Resolve the tools root per request (never frozen at import) so the catalog
    # reflects the resolved Backend nodes directory, and a missing/unreadable root is
    # reported in `errors` rather than masquerading as a healthy empty catalog.
    nodes, errors = scan_node_catalog(get_tools_root())
    public = [{key: value for key, value in node.items() if key != "package_dir"} for node in nodes]
    return {"nodes": public, "errors": errors}


# ── Machine registry / unified status plane ──────────────────────────────────


def _registry_path():
    # The registry lives beside the deployment's other config under the Backend
    # data root (…/config/nodes.json), derived from the same resolved root the
    # catalog uses — never a second, drifting path source.
    return get_tools_root().parent / "config" / "nodes.json"


# Sampling cache + throttle, module-level so it survives across requests.
# Lazy refresh: a GET pays for at most one sampling round per 10s window per
# node; no background thread to supervise, leak, or keep a dead event loop busy.
_STATUS_CACHE: dict[str, dict] = {}
_STATUS_LOCK = threading.Lock()
_SAMPLE_INTERVAL_SECONDS = 10.0


def _sample_statuses(reg: dict) -> None:
    """Refresh the cache for every server node older than the throttle window."""
    now = time.time()
    for entry in reg.get("nodes", []):
        node_id = entry.get("nodeId", "")
        cached = _STATUS_CACHE.get(node_id)
        if cached and now - cached["fetchedAt"] < _SAMPLE_INTERVAL_SECONDS:
            continue
        result = fetch_node_status(entry.get("url", ""), entry.get("token", ""))
        _STATUS_CACHE[node_id] = {"fetchedAt": now, "status": result}


@router.get("/status")
async def node_status():
    reg = load_registry(_registry_path())
    with _STATUS_LOCK:
        _sample_statuses(reg)
        return {"nodes": registry_snapshot(reg, _STATUS_CACHE)}


class EnrollRequest(BaseModel):
    enrollment: str


@router.post("/enroll")
async def enroll(body: EnrollRequest):
    try:
        parsed = parse_enrollment_string(body.enrollment)
    except ValueError as exc:
        raise TDEaseError(
            code=ErrorCode.NODE_ENROLLMENT_INVALID,
            message=f"Invalid enrollment string: {exc}",
            remedy="Re-run `tdease-node enroll` on the machine to pair, and paste the printed string verbatim.",
            retryable=False,
        ) from exc
    reg = load_registry(_registry_path())
    upsert_from_enrollment(reg, parsed)
    save_registry(_registry_path(), reg)
    # Drop any cached sample for this node: its address/credential may have
    # rotated with the re-pairing, and a sample from the old pairing is worse
    # than none.
    with _STATUS_LOCK:
        _STATUS_CACHE.pop(parsed["nodeId"], None)
    token = parsed["token"]
    return {
        "node": {
            "nodeId": parsed["nodeId"],
            "kind": "server",
            "label": parsed.get("label"),
            "protocol": 1,
        },
        "url": parsed["url"],
        # Never echo the full token back — API responses end up in logs and
        # screenshots; a mask proves the pairing without re-leaking the secret.
        "token": token[:3] + "…" + token[-2:],
        "certSha256": parsed.get("certSha256"),
    }


@router.get("/{node_id}")
async def get_node(node_id: str):
    result = await list_nodes()
    for node in result["nodes"]:
        if node["id"] == node_id:
            return node
    raise TDEaseError(
        code=ErrorCode.RUN_NODE_NOT_FOUND,
        message=f"No Node package {node_id} is deployed.",
        remedy="List deployed Nodes with GET /api/nodes.",
        retryable=False,
    )
