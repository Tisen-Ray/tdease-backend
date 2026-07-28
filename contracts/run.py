"""
Run Commit — 不可变的一次运行快照。

Run 是系统中唯一有生命周期状态轴的实体。
Run commit 包含执行一次 workflow 所需的全部信息：
workspace 状态锁定、Snakefile、配置、packages、节点映射。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .enums import RunStatus
from .tree import TreeEntry, _validate_path_no_traversal


class PackageLock(BaseModel):
    """Run commit 中锁定的 package 版本。"""

    name: str = Field(description="package 名称")
    version: str = Field(description="锁定版本")
    digest: str = Field(
        description="package 内容 sha256",
        pattern=r"^[a-f0-9]{64}$",
    )


class NodeBinding(BaseModel):
    """Run commit 中锁定的服务端 Node package identity。"""

    id: str = Field(description="Node ID (e.g. topfd)", pattern=r"^[a-zA-Z0-9_.-]+$")
    version: str = Field(description="Node package version")
    digest: str = Field(
        description="完整 Node package sha256",
        pattern=r"^[a-f0-9]{64}$",
    )
    rules: list[str] = Field(default_factory=list, description="本 Run 使用的公开 rule 名")


class ResultSpec(BaseModel):
    """
    一条声明的 Published Result — 冻结进 RunCommit.result_specs。

    语义见 docs/design/CORE-ARCHITECTURE.md 3、docs/spec/WORKFLOW-RUN-CONTRACT.md 8.4：
    这是可选的 Published Result 语义元数据。未提供时，Backend 从 Snakemake 的默认
    target 声明生成中性的 workflow_output 条目；模型不会从文件名猜测语义。就绪状态是
    output 与 Run 文件清单 join (3.1)，不是独立的状态机；未就绪不代表被吞掉，必须投影为
    "declared"。
    """

    result_id: str = Field(
        description="Result 在本 Run 内的稳定标识 (如 'feature-table:sample-a')",
        pattern=r"^[a-zA-Z0-9_.:-]+$",
    )
    name: str = Field(description="展示名称")
    kind: str = Field(description="Result 种类 (如 feature_table)，用于分组与选择器")
    dimensions: dict[str, str] = Field(
        default_factory=dict,
        description="声明的维度取值 (如 {sample: sample-a})；键为稳定标识，值为字符串",
    )
    output: str = Field(description="Run-root-relative 的产物路径，用于与文件清单 join")
    _validate_output = field_validator("output")(_validate_path_no_traversal)


class WorkflowJobNode(BaseModel):
    id: int
    rule: str
    label: str
    initial_status: Literal["waiting", "up_to_date"] = "waiting"


class WorkflowJobEdge(BaseModel):
    source: int
    target: int


class WorkflowProjection(BaseModel):
    nodes: list[WorkflowJobNode] = Field(default_factory=list)
    edges: list[WorkflowJobEdge] = Field(default_factory=list)


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
    local_root_id: Optional[str] = Field(
        default=None,
        description="Desktop local materialization 使用的 Backend-issued root capability",
    )
    local_run_path: Optional[str] = Field(
        default=None,
        description="相对于已授权 Workspace root 的 Run 路径；remote 必须为空",
    )
    workspace_run_path: Optional[str] = Field(
        default=None,
        description="Client Workspace-relative Run directory used when returning selected artifacts.",
    )

    @field_validator("workspace_run_path")
    @classmethod
    def validate_workspace_run_path(cls, value: Optional[str]) -> Optional[str]:
        return _validate_path_no_traversal(value) if value is not None else None

    # Snakemake 执行参数
    snakefile: str = Field(description="Snakefile 完整内容（提交时固化）")
    config: dict = Field(
        default_factory=dict,
        description="Snakemake --config 参数",
    )
    cores: int = Field(default=4, description="CPU 核心数", ge=1, le=256)
    memory_mb: Optional[int] = Field(
        default=None,
        ge=128,
        description="Snakemake 进程树内存上限 (MB)；null 由 Backend 收紧为当前计算预算",
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

    # Published Results — 声明"答案"，见 docs/design/CORE-ARCHITECTURE.md 3
    result_specs: list[ResultSpec] = Field(
        default_factory=list,
        description=(
            "可选的 Published Result 语义元数据；为空时由 Snakemake 默认 target 声明"
            "生成中性结果。GET /api/v2/runs/{run_id}/results 将其与实际产物清单 join 后投影。"
        ),
    )

    # 元信息
    user_id: str = Field(description="提交者 user_id")
    materialization_strategy: Optional[str] = Field(
        default=None,
        description=(
            "服务端解析并记录的物化策略 (如 local_workspace_hardlink | blob_store)。"
            "调用方不得声明部署模式——见 docs/spec/CAPABILITIES.md 7 与 "
            "docs/design/REMAINING-DESIGNS.md 0.2；Backend 在 app/api/runs_v2.py "
            "中根据 commit 形状 (是否携带 local_root_id) 匹配自身启动时解析的 "
            "capabilities.materialization.strategies 来选定该值，并覆盖任何调用方提交的值。"
            "此前的 mode 字段已从调用方可提交的 commit 面中移除；调用方若仍提交 "
            "mode 会被显式拒绝 (RUN_MODE_MISMATCH)，而不是被静默忽略。"
        ),
    )
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


class RunDryRunRequest(BaseModel):
    commit: RunCommit
    inline_blobs: dict[str, str] = Field(default_factory=dict)


class RunDryRunResponse(BaseModel):
    valid: bool
    exit_code: int
    engine: Literal["tdease-workflow"] = "tdease-workflow"
    output: str
    projection: Optional[WorkflowProjection] = None


class WorkflowGraphNode(WorkflowJobNode):
    status: Literal["waiting", "up_to_date", "running", "succeeded", "failed", "cancelled"]
    wildcards: dict[str, str] = Field(default_factory=dict)


class RunWorkflowGraphResponse(BaseModel):
    run_id: str
    nodes: list[WorkflowGraphNode] = Field(default_factory=list)
    edges: list[WorkflowJobEdge] = Field(default_factory=list)


class ResultRef(BaseModel):
    """
    Published Result 的寻址引用 (docs/design/CORE-ARCHITECTURE.md 3.2)。

    digest 缺省 = 引用该 Result 的当前值 (未 pin，随 Recompute 自动更新)；
    digest 存在 = 精确指向该字节内容 (pin，用于 Evidence/溯源)。两种读法都合法，
    区别只在调用方是否携带 digest —— 本模型故不强制 digest 必填。
    """

    workspace_id: str
    run_id: str
    result_id: str
    digest: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class RunResultEntry(BaseModel):
    """
    单条 Published Result 投影 —— result_specs 中的一条声明与文件清单 join 后的结果。

    status 是 join 的结果，不是独立状态机 (CORE-ARCHITECTURE.md 3.1)：
    声明的 output 在文件清单中不存在 -> "declared"；存在 -> "ready"，携带当前 digest。
    一个声明了但从未就绪的 Result 必须出现在这里 (status="declared")，不能被静默省略；
    反过来，任何未被 result_specs 声明的文件都不会出现在这里 —— 它只是 Technical
    Artifact，只能经由 GET /api/v2/runs/{run_id}/files 访问。
    """

    result_id: str
    name: str
    kind: str
    dimensions: dict[str, str]
    output: str
    status: Literal["declared", "ready"]
    digest: Optional[str] = None
    size: Optional[int] = None
    ref: ResultRef


class RunResultsResponse(BaseModel):
    """GET /api/v2/runs/{run_id}/results 的响应体。"""

    run_id: str
    results: list[RunResultEntry]


class RunRerunRequest(BaseModel):
    mode: Literal["resume", "overwrite"] = "resume"


class RunActionResponse(BaseModel):
    run_id: str
    status: RunStatus
    action: Literal["cancel", "rerun"]
    accepted: bool = True
    mode: Optional[Literal["resume", "overwrite"]] = None


class RunTrashEntry(BaseModel):
    run_id: str
    name: str = ""
    workspace_id: str
    previous_status: RunStatus
    deleted_at: datetime
    deleted_by: str


class RunTrashListResponse(BaseModel):
    runs: list[RunTrashEntry]
    total: int


class RunStatusResponse(BaseModel):
    """
    Run 状态查询响应 — 从 run.json + events.jsonl 衍生的投影。
    不是独立存储，是每次查询时的快照视图。
    """

    run_id: str
    name: str = ""
    workspace_id: str
    workspace_run_path: Optional[str] = None
    current_revision: Optional[str] = None
    status: RunStatus
    materialization_strategy: str = Field(
        default="local_workspace_hardlink",
        description="服务端记录的物化策略，见 RunCommit.materialization_strategy。",
    )
    cores: int
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    rerun_mode: Literal["resume", "overwrite"] = "resume"
    labels: dict[str, str] = Field(default_factory=dict)
    result_file_count: int = 0
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
    has_more: bool = False


class RunCreateResponse(RunStatusResponse):
    idempotent: bool = False
