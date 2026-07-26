"""
TDEase-zero 状态枚举 — 系统中唯一的生命周期字段及其辅助类型。

设计约束（FIRST-PRINCIPLES-AUDIT.md §二）：
- 整个系统有且仅有一个生命周期字段：runs.status
- 无子状态、无状态转换图
- 转换由进程生命周期驱动，非业务代码驱动
"""

from __future__ import annotations

from enum import Enum


class RunStatus(str, Enum):
    """
    Run 生命周期 — 系统中唯一的生命周期轴。

    QUEUED    → 已提交，等待 worker 领取
    RUNNING   → worker 已领取，Execution Runtime 执行中
    SUCCEEDED → 正常退出
    FAILED    → 异常退出或系统错误
    CANCELLED → 用户/系统主动取消

    状态可重建：删除 SQLite 后，扫描 events.jsonl 的最终事件即可恢复。
    """

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class EventType(str, Enum):
    """
    事件类型 — events.jsonl 中每行的 type 字段。

    事件只增不删，按 seq 单调递增。客户端通过 Last-Event-ID 断点续传。

    产品事件（稳定 schema，UI/SSE/Agent 消费）:
      run.queued, run.started, run.succeeded, run.failed, run.cancelled
      task.started, task.progress, task.succeeded, task.failed

    诊断事件（仅 human/tool 调试，不驱动状态）:
      runtime.message
    """

    # Run 级产品事件
    RUN_QUEUED = "run.queued"
    RUN_STARTED = "run.started"
    RUN_SUCCEEDED = "run.succeeded"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    RUN_ACTION = "run.action"

    # Task 级产品事件
    TASK_STARTED = "task.started"
    TASK_PROGRESS = "task.progress"
    TASK_SUCCEEDED = "task.succeeded"
    TASK_FAILED = "task.failed"

    # 诊断事件（不驱动状态）
    RUNTIME_MESSAGE = "runtime.message"


class ErrorCode(str, Enum):
    """
    错误码 — 全系统唯一枚举。

    前端/CLI/Agent 按 code 做分支，不解析 message。
    message 仅供人阅读和日志。
    """

    # --- 通用 ---
    INTERNAL = "INTERNAL"
    NOT_FOUND = "NOT_FOUND"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"

    # --- Run ---
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    RUN_NOT_QUEUED = "RUN_NOT_QUEUED"
    RUN_IDEMPOTENCY_CONFLICT = "RUN_IDEMPOTENCY_CONFLICT"

    # --- Workspace ---
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    WORKSPACE_IDENTITY_INVALID = "WORKSPACE_IDENTITY_INVALID"

    # --- 文件 ---
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    DIGEST_MISMATCH = "DIGEST_MISMATCH"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    BLOB_NOT_FOUND = "BLOB_NOT_FOUND"

    # --- Package/Node ---
    PACKAGE_NOT_FOUND = "PACKAGE_NOT_FOUND"
    PACKAGE_DIGEST_UNRESOLVABLE = "PACKAGE_DIGEST_UNRESOLVABLE"

    # --- Execution Runtime ---
    EXECUTION_INVALID_WORKFLOW = "EXECUTION_INVALID_WORKFLOW"
    EXECUTION_MISSING_INPUT = "EXECUTION_MISSING_INPUT"
    EXECUTION_AMBIGUOUS_RULE = "EXECUTION_AMBIGUOUS_RULE"
    EXECUTION_CYCLE_DETECTED = "EXECUTION_CYCLE_DETECTED"
    EXECUTION_TOOL_NOT_FOUND = "EXECUTION_TOOL_NOT_FOUND"
    EXECUTION_RESOURCE_EXHAUSTED = "EXECUTION_RESOURCE_EXHAUSTED"
    EXECUTION_TASK_FAILED = "EXECUTION_TASK_FAILED"
    EXECUTION_INCOMPLETE_OUTPUT = "EXECUTION_INCOMPLETE_OUTPUT"
    EXECUTION_CANCELLED = "EXECUTION_CANCELLED"
    EXECUTION_RUNTIME_INTERNAL = "EXECUTION_RUNTIME_INTERNAL"

    # --- 传输 ---
    UPLOAD_INCOMPLETE = "UPLOAD_INCOMPLETE"
    PRESIGNED_EXPIRED = "PRESIGNED_EXPIRED"


# 终端状态集合
TERMINAL_STATUSES: frozenset[RunStatus] = frozenset({
    RunStatus.SUCCEEDED,
    RunStatus.FAILED,
    RunStatus.CANCELLED,
})

# 可取消状态
CANCELLABLE_STATUSES: frozenset[RunStatus] = frozenset({
    RunStatus.QUEUED,
    RunStatus.RUNNING,
})
