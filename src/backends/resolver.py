"""
Backend 自动选择器 — 根据环境自动决定用哪个后端。
"""

from __future__ import annotations

import os
from typing import Optional

from src.backends.base import WorkspaceBackend


def resolve_backend(
    server_url: Optional[str] = None,
    token: Optional[str] = None,
) -> WorkspaceBackend:
    """根据配置或环境变量自动选择后端。

    优先级:
    1. 显式传入的 server_url
    2. TDEASE_SERVER 环境变量
    3. ~/.tdease/config.yaml 中的 server 字段
    4. 默认 LocalBackend (Pure Desktop)
    """
    url = (
        server_url
        or os.getenv("TDEASE_SERVER")
        or _read_config_server()
    )

    if url:
        from src.backends.http_client import ServerBackend
        return ServerBackend(base_url=url, token=token)

    from src.backends.local import LocalBackend
    return LocalBackend()


def _read_config_server() -> Optional[str]:
    """从 ~/.tdease/config.yaml 读取 server 地址。"""
    import sys
    if "yaml" not in sys.modules:
        try:
            import yaml
        except ImportError:
            return None
    else:
        import yaml

    config_path = Path.home() / ".tdease" / "config.yaml"
    if not config_path.exists():
        return None
    try:
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("server") if isinstance(cfg, dict) else None
    except Exception:
        return None


# used in _read_config_server
from pathlib import Path
