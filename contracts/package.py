"""
Package 契约 — 可复用工具/节点的声明式定义。

Package = rules.smk + bin/ + metadata。
无 manifest 文件，目录名即 package 名，内容 sha256 即版本。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PackageBinary(BaseModel):
    """package 内一个平台的二进制文件。"""

    platform: str = Field(description="平台标识: linux-x64 | win-x64 | darwin-arm64")
    relative_path: str = Field(description="相对于 package 根目录的路径")
    sha256: str = Field(
        description="二进制 sha256",
        pattern=r"^[a-f0-9]{64}$",
    )


class PackageDefinition(BaseModel):
    """
    Package 完整定义 — 客户端索引和服务端校验共享此结构。

    存储: assets/packages/<name>/ 或 data-root/packages/<name>/
    无 package.yaml 或其他 manifest 文件。
    以下字段由索引器扫描后生成，不经人手写。
    """

    name: str = Field(
        description="package 名称 = 目录名",
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_-]*$",
    )
    digest: str = Field(
        description="整个 package 目录的 sha256（所有文件排序后联合 hash）",
        pattern=r"^[a-f0-9]{64}$",
    )
    version: str = Field(
        default="0.1.0",
        description="语义版本号",
        pattern=r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$",
    )

    # 核心文件
    rules_smk: str = Field(
        description="Snakemake rule 片段内容（include 时加载）",
    )
    bin: list[PackageBinary] = Field(
        default_factory=list,
        description="各平台二进制文件列表",
    )

    # 元数据
    description: str = Field(default="", description="人类可读描述")
    homepage: Optional[str] = Field(default=None, description="项目主页")
    license: Optional[str] = Field(default=None, description="SPDX license identifier")
    dependencies: list[str] = Field(
        default_factory=list,
        description="依赖的 package 名称列表",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="搜索标签",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
    )


class PackageIndex(BaseModel):
    """客户端 package 索引 — 来自 GET /api/packages 或本地扫描。"""

    packages: list[PackageDefinition] = Field(description="可用 package 列表")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.utcnow(),
    )
    server_url: Optional[str] = Field(default=None, description="索引来源 URL")
