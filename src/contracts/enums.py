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


class RunExecutionMode(str, Enum):
    """How one immutable Run revision is requested for execution."""

    EXECUTE = "execute"
    CONTINUE = "continue"


class EventType(str, Enum):
    """
    事件类型 — events.jsonl 中每行的 type 字段。

    事件只增不删，按 seq 单调递增。客户端通过 Last-Event-ID 断点续传。

    产品事件（稳定 schema，UI/SSE/Agent 消费）:
      run.submitted, run.queue_requested, run.started,
      run.succeeded, run.failed, run.cancelled
      task.started, task.progress, task.succeeded, task.failed

    诊断事件（仅 human/tool 调试，不驱动状态）:
      runtime.message
    """

    # Run 级产品事件
    RUN_SUBMITTED = "run.submitted"
    RUN_QUEUE_REQUESTED = "run.queue_requested"
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
    JOB_STARTED = "job.started"
    JOB_SUCCEEDED = "job.succeeded"
    JOB_FAILED = "job.failed"
    WORKFLOW_GRAPH = "workflow.graph"

    # 诊断事件（不驱动状态）
    RUNTIME_MESSAGE = "runtime.message"


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
