"""Read-only projection of executable node packages deployed on this server."""
from fastapi import APIRouter

from src.execution_runtime.storage import get_storage
from src.services.node_catalog import scan_nodes
from app.core.errors import ErrorCode, TDEaseError

router = APIRouter(prefix="/api/nodes", tags=["nodes"])

# 内置计算工具位于 <dataRoot>/backend/nodes/ (TDEASE_TOOLS_ROOT)
_TOOLS_NODES = get_storage().data / "nodes"


@router.get("")
async def list_nodes():
    nodes, errors = scan_nodes(_TOOLS_NODES)
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
