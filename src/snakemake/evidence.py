"""
Snakemake 证据收集钩子 (Evidence Runtime)

在每个 job 完成后收集：
- stdout/stderr
- 输入/输出文件校验和
- 运行元数据 (rule name, duration, resources)
- 异常信息（如果有）

这些证据存储在 workspace 的 .tdease/evidence/ 目录下，
供审计和 AI 调试使用。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class JobEvidence:
    """单个 job 的证据记录。"""

    rule_name: str
    job_id: str
    start_time: float
    end_time: float
    duration_seconds: float
    success: bool
    input_files: list[dict[str, str]] = field(default_factory=list)
    output_files: list[dict[str, str]] = field(default_factory=list)
    log_files: list[str] = field(default_factory=list)
    shell_command: Optional[str] = None
    error_message: Optional[str] = None
    resources: dict[str, Any] = field(default_factory=dict)
    conda_env: Optional[str] = None
    container: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


@dataclass
class WorkflowEvidence:
    """整个 workflow 执行的证据汇总。"""

    snakefile: str
    workdir: str
    start_time: float
    end_time: float
    total_duration: float
    success: bool
    jobs: list[JobEvidence] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def save(self, path: str | Path) -> Path:
        """保存证据到 JSON 文件。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")
        return path

    def to_dict(self) -> dict[str, Any]:
        return {
            "snakefile": self.snakefile,
            "workdir": self.workdir,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration": self.total_duration,
            "success": self.success,
            "job_count": len(self.jobs),
            "jobs": [j.to_dict() for j in self.jobs],
            "config": self.config,
            "error": self.error,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


def checksum_file(path: str | Path) -> str:
    """计算文件的 SHA-256 校验和。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect_file_info(path: str | Path) -> dict[str, str]:
    """收集文件元信息。"""
    p = Path(path)
    if not p.exists():
        return {"path": str(p), "exists": False}
    stat = p.stat()
    return {
        "path": str(p),
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "checksum": checksum_file(p),
        "exists": True,
    }
