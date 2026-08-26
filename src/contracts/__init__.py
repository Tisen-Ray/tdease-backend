"""TDEase-nexus contract layer — authoritative definitions of all entity types in the system."""

from .enums import (
    CANCELLABLE_STATUSES,
    TERMINAL_STATUSES,
    EventType,
    RunExecutionMode,
    RunStatus,
)
from .event import (
    Event,
    EventBatch,
    RunQueueRequestedData,
    RunStartedData,
    RunSubmittedData,
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
    ResultRef,
    ResultSpec,
    RunActionResponse,
    RunCommit,
    RunCreateRequest,
    RunCreateResponse,
    RunDryRunRequest,
    RunDryRunResponse,
    RunListResponse,
    RunRerunRequest,
    RunResultEntry,
    RunResultsResponse,
    RunStatusResponse,
    RunTrashEntry,
    RunTrashListResponse,
    RunWorkflowGraphResponse,
    WorkflowProjection,
)
from .tree import TreeDiff, TreeEntry, TreeManifest
from .workspace import WorkspaceAttachRequest, WorkspaceIdentity, WorkspaceRegistration

__all__ = [
    # enums
    "RunStatus", "RunExecutionMode", "EventType",
    "TERMINAL_STATUSES", "CANCELLABLE_STATUSES",
    # workspace
    "WorkspaceIdentity", "WorkspaceRegistration", "WorkspaceAttachRequest",
    # tree
    "TreeEntry", "TreeManifest", "TreeDiff",
    # run
    "RunCommit", "RunCreateRequest", "RunCreateResponse", "RunDryRunRequest", "RunDryRunResponse",
    "RunRerunRequest", "RunActionResponse", "RunStatusResponse", "RunListResponse",
    "RunTrashEntry", "RunTrashListResponse",
    "RunWorkflowGraphResponse", "WorkflowProjection",
    "PackageLock", "NodeBinding", "ResultSpec", "ResultRef", "RunResultEntry", "RunResultsResponse",
    # event
    "Event", "EventBatch", "RuntimeRef",
    "RunSubmittedData", "RunQueueRequestedData", "RunStartedData", "RunTerminatedData",
    "TaskStartedData", "TaskProgressData", "TaskSucceededData", "TaskFailedData",
    "RuntimeMessageData",
]
