"""Read-only access to installed canonical workflow documents."""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v2/workflow-templates", tags=["workflow-templates"])


def _system_workflows() -> Path:
    # 内置 workflow 模板：TDEASE_SYSTEM_WORKFLOWS override 优先；否则
    # <dataRoot>/system/workflows（走单一解析点 get_system_root()）。
    from src.execution_runtime.storage import get_system_root
    configured = os.environ.get("TDEASE_SYSTEM_WORKFLOWS")
    return Path(configured) if configured else get_system_root() / "workflows"


@router.get("/{template_id}")
async def get_workflow_template(template_id: str):
    if not template_id.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="invalid template id")
    path = (_system_workflows() / f"{template_id}.json").resolve(strict=False)
    root = _system_workflows().resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="template path escapes system root")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"workflow template not found: {template_id}")
    return json.loads(path.read_text(encoding="utf-8-sig"))
