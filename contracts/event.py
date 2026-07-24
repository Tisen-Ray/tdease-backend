"""
Event Stream — 不可变更的事件日志。

真相来源：events.jsonl（每行一个 JSON 对象，只追加）。
SQLite 状态可从此文件重建。SSE 直接从该文件尾部流出。

所有事件含:
  schema_version, seq, timestamp, run_id, type, level, message,
  runtime_ref, data

seq 单调递增，append + fsync 后才能 SSE 发布。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from .enums import EventType


class RuntimeRef(BaseModel):
    """执行上下文引用 — 用于诊断关联，不是持久实体。"""

    task_id: Optional[str] = Field(default=None, description="Task 标识")
    step_label: Optional[str] = Field(default=None, description="人类可读步骤名")


class Event(BaseModel):
    """
    events.jsonl 中的一行。所有事件共享此结构。

    fields:
      schema_version: 事件契约版本
      seq: 单调递增序号 (same-run)
      timestamp: UTC 发生时间
      run_id: 所属 Run
      type: EventType 枚举值
      level: info | warn | error
      message: 人类可读简述
      runtime_ref: 执行上下文 (task/step)
      data: 按 type 不同的负载
    """

    schema_version: int = Field(default=1, description="Event schema version")
    run_id: str = Field(description="所属 Run")
    seq: int = Field(description="事件序号，从 1 开始，单调递增", ge=1)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC 发生时间",
    )
    type: EventType = Field(description="事件类型")
    level: str = Field(default="info", description="info | warn | error")
    message: str = Field(default="", description="人类可读简述")
    runtime_ref: Optional[RuntimeRef] = Field(default=None, description="执行上下文引用")
    data: dict[str, Any] = Field(default_factory=dict, description="按 type 不同的负载")


class EventBatch(BaseModel):
    """一次 SSE 推送的事件批次。"""

    events: list[Event] = Field(description="按 seq 升序")
    run_id: str
    last_seq: int = Field(description="本批次最大 seq → Last-Event-ID")


# --- 各产品事件 data schema ---

class RunQueuedData(BaseModel):
    idempotency_key: str
    workspace_tree_hash: str
    user_id: str
    cores: int
    workflow_steps: int = Field(default=0)


class RunStartedData(BaseModel):
    pid: int
    worker_id: str


class TaskStartedData(BaseModel):
    task_id: str
    step: str = Field(description="人类可读步骤名")
    command: str = Field(default="", description="脱敏后的命令")


class TaskProgressData(BaseModel):
    task_id: str
    done: int
    total: int
    percent: float = Field(ge=0.0, le=100.0)


class TaskSucceededData(BaseModel):
    task_id: str
    duration_seconds: float
    output_files: list[str] = Field(default_factory=list)


class TaskFailedData(BaseModel):
    task_id: str
    exit_code: int
    duration_seconds: float
    error_message: str = Field(default="")


class RunTerminatedData(BaseModel):
    exit_code: Optional[int] = Field(default=None)
    run_time_seconds: float
    total_tasks: int = Field(default=0)
    succeeded_tasks: int = Field(default=0)
    failed_tasks: int = Field(default=0)


class RuntimeMessageData(BaseModel):
    """无法结构化的诊断信息。"""
    level: str = Field(default="debug", description="debug | info | warn | error")
    message: str
    runtime_ref: Optional[RuntimeRef] = Field(default=None)
