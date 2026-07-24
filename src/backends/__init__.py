"""
WorkspaceBackend — 三种部署模式的统一抽象。

LocalBackend:   Pure Desktop 直接 subprocess
ServerBackend:  Desktop+Server HTTP 通信
CloudBackend:   Desktop+Cloud (同 ServerBackend 协议)
"""

from src.backends.base import WorkspaceBackend, RunInfo
from src.backends.local import LocalBackend
from src.backends.http_client import ServerBackend

__all__ = [
    "WorkspaceBackend",
    "RunInfo",
    "LocalBackend",
    "ServerBackend",
]
