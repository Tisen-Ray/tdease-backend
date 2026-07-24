"""
TDEase-zero Snakemake 封装层

Snakemake 是唯一的 workflow 引擎。这一层提供：
1. 程序化调用 Snakemake API 执行 workflow
2. 证据收集钩子 (evidence hooks)
3. workspace 文件系统集成

不暴露 Snakemake CLI 给外部，全部通过 Python API 调用。
"""

from src.snakemake.service import (
    run_snakemake,
    SnakemakeResult,
)
from src.snakemake.workflow_spec import (
    WorkflowSpec,
    RuleSpec,
)

__all__ = [
    "run_snakemake",
    "SnakemakeResult",
    "WorkflowSpec",
    "RuleSpec",
]
