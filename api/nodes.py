"""Read-only projection of executable node packages deployed on this server."""
from fastapi import APIRouter, HTTPException

from src.execution_runtime.storage import get_storage
from src.services.node_catalog import scan_nodes

router = APIRouter(prefix="/api/nodes", tags=["nodes"])


@router.get("")
async def list_nodes():
    nodes, errors = scan_nodes(get_storage().data / "nodes")
    public = [{key: value for key, value in node.items() if key != "package_dir"} for node in nodes]
    return {"nodes": public, "errors": errors}


@router.get("/{node_id}")
async def get_node(node_id: str):
    result = await list_nodes()
    for node in result["nodes"]:
        if node["id"] == node_id:
            return node
    raise HTTPException(status_code=404, detail="node not found")
