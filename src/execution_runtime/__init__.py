"""
TDEase Execution Runtime — 产品执行引擎。

产品代码只使用 TDEase namespace 和类型；上游依赖封闭在私有 engine_runner。
解析、规划、调度、执行算法从成熟实现中迁入（按能力，不按目录）。

公开入口:
  preflight(commit) -> PreflightResult
  execute(commit, cancel_token) -> ExecutionResult
  cancel(run_id) -> bool

内部:
  parser.py     — Snakefile token-based 解析
  execution.py  — 本地任务执行
  storage.py    — 唯一文件写入原语
  events.py     — typed event emitter
  错误 — TDEaseError（src/contracts/errors.py，FAILURE-CONTRACT.md 单一权威）
"""

from src.execution_runtime.events import EventEmitter
from src.execution_runtime.parser import Rule, Workflow, parse_snakefile
from src.execution_runtime.runtime import (
    ExecutionResult,
    PreflightResult,
    cancel,
    execute,
    preflight,
)
from src.execution_runtime.storage import StorageLayout, get_storage, set_storage

__all__ = [
    "EventEmitter",
    "ExecutionResult",
    "PreflightResult",
    "Rule",
    "StorageLayout",
    "Workflow",
    "cancel",
    "execute",
    "get_storage",
    "parse_snakefile",
    "preflight",
    "set_storage",
]
