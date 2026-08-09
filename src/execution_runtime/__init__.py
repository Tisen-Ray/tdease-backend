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
  errors.py     — ExecutionError
"""

from src.execution_runtime.runtime import (
    ExecutionResult,
    PreflightResult,
    cancel,
    execute,
    preflight,
)
from src.execution_runtime.storage import StorageLayout, get_storage, set_storage
from src.execution_runtime.events import EventEmitter
from src.execution_runtime.errors import ExecutionError
from src.execution_runtime.parser import parse_snakefile, Workflow, Rule

__all__ = [
    "preflight", "execute", "cancel",
    "PreflightResult", "ExecutionResult",
    "StorageLayout", "get_storage", "set_storage",
    "EventEmitter", "ExecutionError",
    "parse_snakefile", "Workflow", "Rule",
]
