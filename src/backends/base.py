"""
WorkspaceBackend 抽象定义。

三种模式共享这个接口。前端和 AI Agent 不关心用哪个实现。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RunInfo:
    """一次运行的状态快照。"""
    id: str
    workspace: str
    status: str          # QUEUED | RUNNING | DONE | FAILED
    mode: str            # local | server | cloud
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    created_at: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.status in ("QUEUED", "RUNNING")

    @property
    def is_done(self) -> bool:
        return self.status in ("DONE", "FAILED")


class WorkspaceBackend(ABC):
    """统一的 workspace 存储后端。"""

    @abstractmethod
    async def submit(
        self,
        workspace: str,
        snakefile: str,
        config: Optional[dict] = None,
        cores: int = 4,
    ) -> RunInfo:
        """提交一次运行。返回 RunInfo。"""
        ...

    @abstractmethod
    async def status(self, run_id: str) -> Optional[RunInfo]:
        """查询运行状态。如果 run 不存在返回 None。"""
        ...

    @abstractmethod
    async def pull(
        self,
        run_id: str,
        patterns: list[str] | None = None,
        dest: str | Path | None = None,
    ) -> list[str]:
        """拉取结果文件到本地。返回已下载的文件路径列表。"""
        ...

    @abstractmethod
    async def fetch(self, run_id: str, path: str) -> Optional[Path]:
        """按需获取单个文件。文件不存在返回 None。"""
        ...

    @abstractmethod
    async def tail_log(self, run_id: str, lines: int = 50) -> str:
        """读取最新日志行。"""
        ...

    @abstractmethod
    async def list_runs(self, workspace: str) -> list[RunInfo]:
        """列出某个 workspace 的所有历史运行。"""
        ...

    @abstractmethod
    async def cancel(self, run_id: str) -> bool:
        """取消运行（如果还在 QUEUED 或 RUNNING）。返回是否成功。"""
        ...
