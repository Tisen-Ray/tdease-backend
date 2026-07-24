"""
TDEase-zero 错误类型 — 结构化错误，前端/CLI/Agent 按 code 分支。

规则：
- 每个错误有唯一的 ErrorCode
- message 供人阅读，不做程序分支依据
- details 携带机器可读的附加信息
- HTTP 状态码由 route 层映射，不在此定义
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enums import ErrorCode


@dataclass(frozen=True)
class AppError(Exception):
    """应用级错误基类。"""

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"


# --- 通用 ---

def internal(message: str = "内部错误", **details: Any) -> AppError:
    return AppError(ErrorCode.INTERNAL, message, details)


def not_found(entity: str, identifier: str) -> AppError:
    return AppError(ErrorCode.NOT_FOUND, f"{entity} 不存在: {identifier}", {"entity": entity, "identifier": identifier})


def invalid_request(message: str, **details: Any) -> AppError:
    return AppError(ErrorCode.INVALID_REQUEST, message, details)


# --- Run ---

def run_not_found(run_id: str) -> AppError:
    return AppError(ErrorCode.RUN_NOT_FOUND, f"Run 不存在: {run_id}", {"run_id": run_id})


def run_not_queued(run_id: str, current_status: str) -> AppError:
    return AppError(ErrorCode.RUN_NOT_QUEUED, f"Run {run_id} 状态为 {current_status}，不可取消", {"run_id": run_id, "current_status": current_status})


def run_idempotency_conflict(key: str, existing_run_id: str) -> AppError:
    return AppError(ErrorCode.RUN_IDEMPOTENCY_CONFLICT, f"幂等键 {key} 已存在 (run: {existing_run_id})", {"idempotency_key": key, "existing_run_id": existing_run_id})


# --- Workspace ---

def workspace_not_found(workspace_id: str) -> AppError:
    return AppError(ErrorCode.WORKSPACE_NOT_FOUND, f"Workspace 不存在: {workspace_id}", {"workspace_id": workspace_id})


def workspace_identity_invalid(path: str, reason: str) -> AppError:
    return AppError(ErrorCode.WORKSPACE_IDENTITY_INVALID, f"Workspace 身份无效 ({path}): {reason}", {"path": path, "reason": reason})


# --- 文件 ---

def path_traversal(attempted_path: str) -> AppError:
    return AppError(ErrorCode.PATH_TRAVERSAL, f"路径穿越检测: {attempted_path}", {"attempted_path": attempted_path})


def digest_mismatch(path: str, expected: str, actual: str) -> AppError:
    return AppError(ErrorCode.DIGEST_MISMATCH, f"摘要不匹配: {path}", {"path": path, "expected": expected, "actual": actual})


def quota_exceeded(user_id: str, current_bytes: int, limit_bytes: int) -> AppError:
    return AppError(ErrorCode.QUOTA_EXCEEDED, f"配额超限: 已用 {current_bytes}, 上限 {limit_bytes}", {"user_id": user_id, "current_bytes": current_bytes, "limit_bytes": limit_bytes})


def blob_not_found(blob_hash: str) -> AppError:
    return AppError(ErrorCode.BLOB_NOT_FOUND, f"Blob 不存在: {blob_hash[:16]}…", {"blob_hash": blob_hash})


# --- Package ---

def package_not_found(name: str, version: str | None = None) -> AppError:
    v = f"@{version}" if version else ""
    return AppError(ErrorCode.PACKAGE_NOT_FOUND, f"Package 不存在: {name}{v}", {"name": name, "version": version})


def package_digest_unresolvable(name: str, digest: str) -> AppError:
    return AppError(ErrorCode.PACKAGE_DIGEST_UNRESOLVABLE, f"Package {name} digest {digest[:12]}… 无法解析", {"name": name, "digest": digest})


# --- Execution Runtime ---

def execution_invalid_workflow(reason: str, **details: Any) -> AppError:
    return AppError(ErrorCode.EXECUTION_INVALID_WORKFLOW, f"工作流无效: {reason}", {"reason": reason, **details})


def execution_missing_input(file: str, task_id: str | None = None) -> AppError:
    return AppError(ErrorCode.EXECUTION_MISSING_INPUT, f"缺失输入文件: {file}", {"file": file, "task_id": task_id})


def execution_tool_not_found(tool: str) -> AppError:
    return AppError(ErrorCode.EXECUTION_TOOL_NOT_FOUND, f"工具未找到: {tool}", {"tool": tool})


def execution_resource_exhausted(resource: str, requested: Any, available: Any) -> AppError:
    return AppError(ErrorCode.EXECUTION_RESOURCE_EXHAUSTED, f"资源耗尽: {resource}", {"resource": resource, "requested": requested, "available": available})


def execution_task_failed(task_id: str, exit_code: int, reason: str = "") -> AppError:
    return AppError(ErrorCode.EXECUTION_TASK_FAILED, f"Task 失败: {task_id} (exit {exit_code})", {"task_id": task_id, "exit_code": exit_code, "reason": reason})


def execution_cancelled(run_id: str) -> AppError:
    return AppError(ErrorCode.EXECUTION_CANCELLED, f"执行已取消: {run_id}", {"run_id": run_id})


def execution_runtime_internal(message: str, **details: Any) -> AppError:
    return AppError(ErrorCode.EXECUTION_RUNTIME_INTERNAL, f"运行时内部错误: {message}", details)


# --- 传输 ---

def upload_incomplete(upload_id: str, expected_parts: int, received_parts: int) -> AppError:
    return AppError(ErrorCode.UPLOAD_INCOMPLETE, f"上传未完成", {"upload_id": upload_id, "expected_parts": expected_parts, "received_parts": received_parts})


def presigned_expired(url: str) -> AppError:
    return AppError(ErrorCode.PRESIGNED_EXPIRED, "Presigned URL 已过期", {"url_prefix": url[:80]})
