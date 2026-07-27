"""
Execution Runtime errors — TDEase-native typed errors.

Internal code throws these directly. No upstream exception translation.
All errors carry TDEase ErrorCode values from src.contracts.enums.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.contracts.enums import ErrorCode


@dataclass
class ExecutionError(Exception):
    """Execution Runtime 错误基类 — 直接映射到 TDEase ErrorCode。

    Exceptions cannot be frozen: Python and ASGI middleware assign traceback
    metadata while propagating them. A frozen dataclass turns that normal
    operation into FrozenInstanceError and masks the actual failure.
    """

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


def invalid_workflow(reason: str, **details: Any) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_INVALID_WORKFLOW, f"无效工作流: {reason}", {"reason": reason, **details})


def missing_input(file: str, task_id: str | None = None) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_MISSING_INPUT, f"缺失输入: {file}", {"file": file, "task_id": task_id})


def ambiguous_rule(name: str, matches: int) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_AMBIGUOUS_RULE, f"规则歧义: {name} ({matches} matches)", {"rule": name, "matches": matches})


def cycle_detected(cycle: list[str]) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_CYCLE_DETECTED, f"检测到循环依赖: {' → '.join(cycle)}", {"cycle": cycle})


def tool_not_found(tool: str) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_TOOL_NOT_FOUND, f"工具未找到: {tool}", {"tool": tool})


def resource_exhausted(resource: str, requested: Any, available: Any) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_RESOURCE_EXHAUSTED, f"资源耗尽: {resource}", {"resource": resource, "requested": requested, "available": available})


def task_failed(task_id: str, exit_code: int, reason: str = "") -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_TASK_FAILED, f"Task 失败: {task_id} (exit {exit_code})", {"task_id": task_id, "exit_code": exit_code, "reason": reason})


def incomplete_output(task_id: str, expected: list[str], actual: list[str]) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_INCOMPLETE_OUTPUT, f"输出不完整: {task_id}", {"task_id": task_id, "expected": expected, "actual": actual})


def cancelled(run_id: str) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_CANCELLED, f"执行已取消: {run_id}", {"run_id": run_id})


def runtime_internal(message: str, **details: Any) -> ExecutionError:
    return ExecutionError(ErrorCode.EXECUTION_RUNTIME_INTERNAL, f"运行时内部错误: {message}", details)
