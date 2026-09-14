"""
Workspace identity contract — an immutable identifier, portable across machines.

Workspace identity does not depend on physical paths. After renaming, moving,
or switching data-root, the workspace_id stays the same; attach restores from
workspace.json.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class WorkspaceIdentity(BaseModel):
    """
    Immutable workspace identity.

    Storage: <workspace>/.tdease/workspace.json
    Server copy: data-root/workspaces/<workspace_id>/workspace.json
    """

    workspace_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Immutable UUID (hex, no hyphens)",
        pattern=r"^[a-f0-9]{32}$",
    )
    name: str = Field(
        description="Human-readable name; renamable, not identity",
        min_length=1,
        max_length=255,
    )
    owner: Optional[str] = Field(
        default=None,
        description="Owner user_id",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Creation time (UTC)",
    )
    description: str = Field(
        default="",
        description="Free-text description",
        max_length=2000,
    )


class WorkspaceRegistration(BaseModel):
    """
    Entry in the user's local registry.

    Storage: ~/.tdease/workspaces.json (array)
    Server: data-root/workspaces/<workspace_id>/workspace.json is authoritative
    """

    workspace_id: str = Field(description="WorkspaceIdentity.workspace_id")
    local_path: str = Field(description="Local absolute path (stored client-side only)")
    name: str = Field(description="Snapshot name, kept in sync with workspace.json")
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last attach time",
    )
    server_url: Optional[str] = Field(
        default=None,
        description="Associated server URL; null = purely local",
    )


class WorkspaceAttachRequest(BaseModel):
    """Request to register / re-attach a workspace."""

    workspace_id: str
    local_path: str
    name: str
