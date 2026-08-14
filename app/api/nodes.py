"""Read-only projection of executable node packages deployed on this server."""
from fastapi import APIRouter

from src.execution_runtime.storage import get_tools_root
from src.services.node_catalog import scan_node_catalog
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
