"""TDEase-zero 契约层 — 系统中所有实体类型的权威定义。"""

from .enums import (
    CANCELLABLE_STATUSES,
    TERMINAL_STATUSES,
    ErrorCode,
    EventType,
    RunStatus,
)
from .errors import (
    AppError,
    blob_not_found,
    digest_mismatch,
    execution_cancelled,
    execution_invalid_workflow,
    execution_missing_input,
    execution_resource_exhausted,
    execution_runtime_internal,
    execution_task_failed,
    execution_tool_not_found,
    internal,
    invalid_request,
    not_found,
    package_digest_unresolvable,
    package_not_found,
    path_traversal,
    presigned_expired,
    quota_exceeded,
    run_idempotency_conflict,
    run_not_found,
    run_not_queued,
    upload_incomplete,
    workspace_identity_invalid,
    workspace_not_found,
)
from .event import (
    Event,
    EventBatch,
    RunQueuedData,
    RunStartedData,
    RunTerminatedData,
    RuntimeMessageData,
    RuntimeRef,
    TaskFailedData,
    TaskProgressData,
    TaskStartedData,
    TaskSucceededData,
)
from .run import (
    NodeBinding,
    PackageLock,
    RunCommit,
    RunCreateRequest,
    RunCreateResponse,
    RunDryRunRequest,
    RunDryRunResponse,
    RunActionResponse,
    RunListResponse,
    RunRerunRequest,
    RunStatusResponse,
    RunTrashEntry,
    RunTrashListResponse,
)
from .tree import TreeDiff, TreeEntry, TreeManifest
from .workspace import WorkspaceAttachRequest, WorkspaceIdentity, WorkspaceRegistration

__all__ = [
    # enums
    "RunStatus", "EventType", "ErrorCode",
    "TERMINAL_STATUSES", "CANCELLABLE_STATUSES",
    # errors
    "AppError", "internal", "not_found", "invalid_request",
    "run_not_found", "run_not_queued", "run_idempotency_conflict",
    "workspace_not_found", "workspace_identity_invalid",
    "path_traversal", "digest_mismatch", "quota_exceeded", "blob_not_found",
    "package_not_found", "package_digest_unresolvable",
    "execution_invalid_workflow", "execution_missing_input",
    "execution_tool_not_found", "execution_resource_exhausted",
    "execution_task_failed", "execution_cancelled", "execution_runtime_internal",
    "upload_incomplete", "presigned_expired",
    # workspace
    "WorkspaceIdentity", "WorkspaceRegistration", "WorkspaceAttachRequest",
    # tree
    "TreeEntry", "TreeManifest", "TreeDiff",
    # run
    "RunCommit", "RunCreateRequest", "RunCreateResponse", "RunDryRunRequest", "RunDryRunResponse",
    "RunRerunRequest", "RunActionResponse", "RunStatusResponse", "RunListResponse",
    "RunTrashEntry", "RunTrashListResponse",
    "PackageLock", "NodeBinding",
    # event
    "Event", "EventBatch", "RuntimeRef",
    "RunQueuedData", "RunStartedData", "RunTerminatedData",
    "TaskStartedData", "TaskProgressData", "TaskSucceededData", "TaskFailedData",
    "RuntimeMessageData",
]
