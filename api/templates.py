"""Read-only workflow template projection."""
from fastapi import APIRouter, HTTPException

from src.execution_runtime.storage import get_system_root
from src.services.template_catalog import scan_templates

router = APIRouter(prefix="/api/templates", tags=["templates"])

# Templates live directly under <systemRoot>/templates/<id>/ (one dir per
# template: template.json + Snakefile + config.yaml). No "builtin" subdir —
# the flat layout matches node packages under <dataRoot>/nodes/<id>/.
_TEMPLATES_ROOT = lambda: get_system_root() / "templates"


@router.get("")
async def list_templates():
    templates, errors = scan_templates(_TEMPLATES_ROOT())
    summaries = [{key: value for key, value in item.items() if key not in {"files", "readme"}} for item in templates]
    return {"templates": summaries, "errors": errors}


@router.get("/{template_id}")
async def get_template(template_id: str):
    templates, _ = scan_templates(_TEMPLATES_ROOT())
    for item in templates:
        if item["id"] == template_id:
            return item
    raise HTTPException(status_code=404, detail="template not found")
