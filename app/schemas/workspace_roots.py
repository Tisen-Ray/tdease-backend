"""Workspace-root capability wire models — transport.

Pure Pydantic wire shapes; no behaviour. The registry and routes live in
`src/services/workspace_roots.py` and `app/api/workspace_roots.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkspaceRootRegisterRequest(BaseModel):
    path: str = Field(description="Absolute local directory path chosen through the native picker")


class WorkspaceRootEntry(BaseModel):
    root_id: str
    path: str


class WorkspaceRootListResponse(BaseModel):
    roots: list[WorkspaceRootEntry]
