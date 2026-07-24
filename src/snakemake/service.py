"""
Snakemake 执行服务 — 薄封装。

内部直接调用 src/snakemake/ (内化的引擎源码)，不依赖外部 snakemake 包。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SnakemakeResult:
    """一次 Snakemake 执行的结果。"""

    success: bool
    updated_files: list[str] = field(default_factory=list)
    failed_jobs: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    error: Optional[str] = None
    evidence: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.success


def run_snakemake(
    snakefile: str | Path,
    workdir: str | Path,
    cores: int = 4,
    config: dict[str, Any] | None = None,
    verbose: bool = False,
) -> SnakemakeResult:
    """通过内化 Snakemake API 执行 workflow。

    Parameters
    ----------
    snakefile : str | Path
        Snakefile 路径。
    workdir : str | Path
        工作目录。
    cores : int
        并行核心数。
    config : dict | None
        传递给 Snakefile 的 config 字典。
    verbose : bool
        是否输出详细日志。
    """
    start = time.perf_counter()
    snakefile = Path(snakefile)
    workdir = Path(workdir)

    if not snakefile.exists():
        return SnakemakeResult(success=False, error=f"Snakefile not found: {snakefile}")

    try:
        # 使用内化引擎 — import 来自 src/snakemake/api.py
        from snakemake.api import SnakemakeApi
        from snakemake.settings.types import (
            ConfigSettings,
            DAGSettings,
            ExecutionSettings,
            OutputSettings,
            ResourceSettings,
        )
    except ImportError as e:
        return SnakemakeResult(success=False, error=f"Snakemake engine import failed: {e}")

    updated_files: list[str] = []

    try:
        output_settings = OutputSettings(verbose=verbose, quiet=not verbose)
        with SnakemakeApi(output_settings=output_settings) as api:
            dag_api = api.workflow(
                snakefile=snakefile,
                workdir=workdir,
                resource_settings=ResourceSettings(cores=cores),
                config_settings=ConfigSettings(config=config or {}),
            ).dag(dag_settings=DAGSettings())

            dag_api.execute_workflow(
                executor="local",
                execution_settings=ExecutionSettings(keep_logger=True),
                updated_files=updated_files,
            )

        elapsed = time.perf_counter() - start
        return SnakemakeResult(
            success=True,
            updated_files=updated_files,
            duration_seconds=elapsed,
        )
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.exception("Snakemake execution failed")
        return SnakemakeResult(success=False, error=str(e), duration_seconds=elapsed)
