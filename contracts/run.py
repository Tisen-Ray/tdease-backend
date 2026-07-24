"""
Run Commit — 不可变的一次运行快照。

Run 是系统中唯一有生命周期状态轴的实体。
Run commit 包含执行一次 workflow 所需的全部信息：
workspace 状态锁定、Snakefile、配置、packages、节点映射。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from .enums import RunStatus
from .tree import TreeEntry


class PackageLock(BaseModel):
    """Run commit 中锁定的 package 版本。"""

    name: str = Field(description="package 名称")
    version: str = Field(description="锁定版本")
    digest: str = Field(
        description="package 内容 sha256",
        pattern=r"^[a-f0-9]{64}$",
    )


class NodeBinding(BaseModel):
    """Run commit 中锁定的节点二进制路径。"""

    name: str = Field(description="节点名称 (e.g. msconvert)")
    binary_path: str = Field(description="服务端解析后的绝对路径")
    binary_digest: str = Field(
        description="二进制 sha256",
        pattern=r"^[a-f0-9]{64}$",
    )


class RunCommit(BaseModel):
    """
    不可变 Run commit — 前端/CLI/Agent 提交，后端只做机械校验。

    提交后 run_id 固定，commit 内容永不修改。
    存储位置: data-root/runs/<run_id>/run.json
    """

    run_id: str = Field(
        description="运行唯一标识",
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    idempotency_key: str = Field(
        description="客户端生成的幂等键，UNIQUE 约束",
    )
    workspace_id: str = Field(description="所属 workspace")
    workspace_tree_hash: str = Field(
        description="提交时刻的 workspace tree hash，锁定文件状态",
        pattern=r"^[a-f0-9]{64}$",
    )
    workspace_files: list[TreeEntry] = Field(
        default_factory=list,
        description="客户端冻结的 path→blob 映射；服务端据此物化隔离运行快照",
    )

    # Snakemake 执行参数
    snakefile: str = Field(description="Snakefile 完整内容（提交时固化）")
    config: dict = Field(
        default_factory=dict,
        description="Snakemake --config 参数",
    )
    cores: int = Field(default=4, description="CPU 核心数", ge=1, le=256)
    memory_mb: Optional[int] = Field(
        default=None,
        description="内存上限 (MB)，null = 不限制",
    )
    targets: list[str] = Field(
        default_factory=list,
        description="Snakemake target rules/files，空 = 默认 target",
    )

    # 依赖锁定
    packages: list[PackageLock] = Field(
        default_factory=list,
        description="锁定的 package 列表",
    )
    nodes: list[NodeBinding] = Field(
        default_factory=list,
        description="锁定的节点二进制映射",
    )

    # 元信息
    user_id: str = Field(description="提交者 user_id")
    mode: str = Field(default="local", description="执行模式: local | remote")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="提交时间 (UTC)",
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description="用户自定义标签，用于搜索和分组",
    )


class RunCreateRequest(BaseModel):
    """
    提交 Run 的请求体。

    由前端/CLI/Agent 构建，包含完整 commit。
    后端只校验，不修改。
    """

    commit: RunCommit


class RunStatusResponse(BaseModel):
    """
    Run 状态查询响应 — 从 run.json + events.jsonl 衍生的投影。
    不是独立存储，是每次查询时的快照视图。
    """

    run_id: str
    workspace_id: str
    status: RunStatus
    mode: str
    cores: int
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    event_seq_last: int = Field(
        default=0,
        description="当前最后事件序号，用于 SSE Last-Event-ID",
    )


class RunListResponse(BaseModel):
    """Run 列表响应 — 分页、可重建。"""

    runs: list[RunStatusResponse]
    total: int
    offset: int
    limit: int
