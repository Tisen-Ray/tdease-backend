"""
TDEase Execution Runtime — the production execution engine.

Product code uses only the TDEase namespace and types; upstream dependencies stay sealed inside the private engine_runner.
Parsing, planning, scheduling, and execution algorithms were migrated in from mature implementations (by capability, not by directory).

Public entry points:
  preflight(commit) -> PreflightResult
  execute(commit, cancel_token) -> ExecutionResult
  cancel(run_id) -> bool

Internal:
  parser.py     — token-based Snakefile parsing
  execution.py  — local task execution
  storage.py    — the single file-write primitive
  events.py     — typed event emitter
  Errors — TDEaseError (src/contracts/errors.py; FAILURE-CONTRACT.md is the single authority)
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
