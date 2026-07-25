"""Read-only workflow template projection."""
from fastapi import APIRouter, HTTPException

from src.execution_runtime.storage import get_storage
from src.services.template_catalog import scan_templates

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
async def list_templates():
    templates, errors = scan_templates(get_storage().data / "templates")
    summaries = [{key: value for key, value in item.items() if key not in {"files", "readme"}} for item in templates]
    return {"templates": summaries, "errors": errors}


@router.get("/{template_id}")
async def get_template(template_id: str):
    templates, _ = scan_templates(get_storage().data / "templates")
    for item in templates:
        if item["id"] == template_id:
            return item
    raise HTTPException(status_code=404, detail="template not found")
