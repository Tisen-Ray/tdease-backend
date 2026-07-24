"""
Run 数据模型 — 极简 pydantic，不依赖 SQLModel。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel


class Run(BaseModel):
    id: str = ""
    user_id: Optional[str] = None
    workspace: str = ""
    snakefile: str = ""
    config_json: Optional[str] = None
    status: str = "QUEUED"
    mode: str = "local"
    cores: int = 4
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    evidence_json: Optional[str] = None
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class RunCreate(BaseModel):
    workspace: str
    snakefile: str
    config: Optional[dict] = None
    cores: int = 4


class RunStatus(BaseModel):
    id: str
    workspace: str
    status: str
    mode: str
    cores: int
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
