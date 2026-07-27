"""
Workspace 身份契约 — 不可变标识，可跨机器搬运。

工作区身份不依赖物理路径。重命名、移动、换 data-root 后
workspace_id 不变，attach 时按 workspace.json 恢复。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class WorkspaceIdentity(BaseModel):
    """
    workspace 不可变身份。

    存储位置: <workspace>/.tdease/workspace.json
    服务端副本: data-root/workspaces/<workspace_id>/workspace.json
    """

    workspace_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="不可变 UUID（hex，无连字符）",
        pattern=r"^[a-f0-9]{32}$",
    )
    name: str = Field(
        description="人类可读名称，可重命名，非身份",
        min_length=1,
        max_length=255,
    )
    owner: Optional[str] = Field(
        default=None,
        description="所有者 user_id",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="创建时间（UTC）",
    )
    description: str = Field(
        default="",
        description="自由文本描述",
        max_length=2000,
    )


class WorkspaceRegistration(BaseModel):
    """
    用户本地注册表条目。

    存储位置: ~/.tdease/workspaces.json (数组)
    服务端: data-root/workspaces/<workspace_id>/workspace.json 为权威来源
    """

    workspace_id: str = Field(description="WorkspaceIdentity.workspace_id")
    local_path: str = Field(description="本地绝对路径（仅用户端存储）")
    name: str = Field(description="快照名称，与 workspace.json 同步")
    last_seen: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="最后一次 attach 时间",
    )
    server_url: Optional[str] = Field(
        default=None,
        description="关联的服务端 URL, null = 纯本地",
    )


class WorkspaceAttachRequest(BaseModel):
    """注册/重新挂载 workspace 的请求。"""

    workspace_id: str
    local_path: str
    name: str
