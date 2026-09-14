"""
Run Commit — an immutable snapshot of a single run.

Run is the only entity in the system with a lifecycle status axis.
A Run commit contains everything needed to execute a workflow once:
locked workspace state, Snakefile, configuration, and node bindings.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .enums import RunStatus
from .tree import TreeEntry, _validate_path_no_traversal


class NodeBinding(BaseModel):
    """Server-side Node package identity locked in the run commit."""

    id: str = Field(description="Node ID (e.g. topfd)", pattern=r"^[a-zA-Z0-9_.-]+$")
    version: str = Field(description="Node package version")
    digest: str = Field(
        description="Full Node package sha256",
        pattern=r"^[a-f0-9]{64}$",
    )
    rules: list[str] = Field(
        default_factory=list, description="Public rule names used by this run"
    )


class ResultSpec(BaseModel):
    """
    A declared Published Result — frozen into RunCommit.result_specs.

    Semantics: see docs/design/CORE-ARCHITECTURE.md 3 and docs/spec/WORKFLOW-RUN.md.
    This is optional Published Result semantic metadata. When absent, the Backend
    generates a neutral workflow_output entry from Snakemake's default target
    declaration; the model never guesses semantics from file names. Readiness is
    a join between output and the Run file manifest (3.1), not a separate state
    machine; not-ready does not mean swallowed — it must be projected as
    "declared".
    """

    result_id: str = Field(
        description="Stable identifier of the Result within this Run (e.g. 'feature-table:sample-a')",
        pattern=r"^[a-zA-Z0-9_.:-]+$",
    )
    name: str = Field(description="Display name")
    kind: str = Field(
        description="Result kind (e.g. feature_table), used for grouping and selectors"
    )
    dimensions: dict[str, str] = Field(
        default_factory=dict,
        description="Declared dimension values (e.g. {sample: sample-a}); keys are stable identifiers, values are strings",
    )
    output: str = Field(
        description="Run-root-relative artifact path, used to join with the file manifest"
    )
    _validate_output = field_validator("output")(_validate_path_no_traversal)


class WorkflowJobNode(BaseModel):
    id: int
    rule: str
    label: str
    initial_status: Literal["waiting", "up_to_date"] = "waiting"


class WorkflowJobEdge(BaseModel):
    source: int
    target: int


class WorkflowProjection(BaseModel):
    nodes: list[WorkflowJobNode] = Field(default_factory=list)
    edges: list[WorkflowJobEdge] = Field(default_factory=list)


class RunCommit(BaseModel):
    """
    Immutable Run commit — submitted by frontend/CLI/Agent; the backend only
    performs mechanical validation.

    After submission the run_id is fixed and the commit content is never
    modified.
    Storage: data-root/runs/<run_id>/definitions/<definition_revision_id>.json;
    run.json is only the latest-definition pointer used by list/status views.
    """

    run_id: str = Field(
        description="Unique run identifier",
        pattern=r"^[a-zA-Z0-9_-]+$",
    )
    idempotency_key: str = Field(
        description="Client-generated idempotency key, UNIQUE constraint",
    )
    workspace_id: str = Field(description="Owning workspace")
    workspace_tree_hash: str = Field(
        description="Workspace tree hash at submission time; locks the file state",
        pattern=r"^[a-f0-9]{64}$",
    )
    workspace_files: list[TreeEntry] = Field(
        default_factory=list,
        description="Frozen client-side path→blob mapping; the server materializes the isolated run snapshot from it",
    )
    local_root_id: Optional[str] = Field(
        default=None,
        description="Backend-issued root capability used for desktop local materialization",
    )
    local_run_path: Optional[str] = Field(
        default=None,
        description="Run path relative to the authorized Workspace root; must be empty for remote",
    )
    workspace_run_path: Optional[str] = Field(
        default=None,
        description="Client Workspace-relative Run directory used when returning selected artifacts.",
    )

    @field_validator("workspace_run_path")
    @classmethod
    def validate_workspace_run_path(cls, value: Optional[str]) -> Optional[str]:
        return _validate_path_no_traversal(value) if value is not None else None

    # Snakemake execution parameters
    snakefile: str = Field(description="Full Snakefile content (frozen at submission)")
    config: dict = Field(
        default_factory=dict,
        description="Snakemake --config parameters",
    )
    # Compute envelope — Backend-owned. `_schedule_commit` injects the startup
    # compute budget; callers who send these fields are rejected by name
    # (`_reject_removed_commit_fields`). Kept on the model because the worker,
    # the engine request, and run.json all consume the injected values.
    cores: int = Field(
        default=4, description="Backend-injected CPU core budget", ge=1, le=256
    )
    memory_mb: Optional[int] = Field(
        default=None,
        ge=128,
        description="Backend-injected scheduling memory budget (MB)",
    )
    targets: list[str] = Field(
        default_factory=list,
        description="Snakemake target rules/files; empty = default target",
    )

    # Dependency locks
    nodes: list[NodeBinding] = Field(
        default_factory=list,
        description="Locked node binary mapping",
    )

    # Published Results — declared "answers"; see docs/design/CORE-ARCHITECTURE.md 3
    result_specs: list[ResultSpec] = Field(
        default_factory=list,
        description=(
            "Optional Published Result semantic metadata; when empty, neutral "
            "results are generated from the Snakemake default target declaration. "
            "GET /api/v2/runs/{run_id}/results joins these with the actual "
            "artifact manifest before projection."
        ),
    )

    # Metadata
    user_id: str = Field(description="Submitting user_id")
    materialization_strategy: Optional[str] = Field(
        default=None,
        description=(
            "Materialization strategy resolved and recorded by the server "
            "(e.g. local_workspace_hardlink | blob_store). Callers must not "
            "declare a deployment mode — see docs/spec/CAPABILITIES.md 7 and "
            "docs/STATUS.md. In app/api/runs_v2.py the Backend selects this "
            "value by matching the commit shape (whether local_root_id is "
            "present) against the capabilities.materialization.strategies "
            "resolved at startup, overriding any caller-submitted value. "
            "The former mode field has been removed from the caller-submittable "
            "commit surface; a caller that still submits mode is explicitly "
            "rejected (RUN_MODE_MISMATCH) rather than silently ignored."
        ),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Submission time (UTC)",
    )
    labels: dict[str, str] = Field(
        default_factory=dict,
        description="User-defined labels for search and grouping",
    )


class RunCreateRequest(BaseModel):
    """
    Request body for submitting a Run.

    Built by frontend/CLI/Agent; contains the full commit.
    The backend only validates, never modifies.
    """

    commit: RunCommit


class RunDryRunRequest(BaseModel):
    commit: RunCommit
    inline_blobs: dict[str, str] = Field(default_factory=dict)


class RunDryRunResponse(BaseModel):
    valid: bool
    exit_code: int
    engine: Literal["tdease-workflow"] = "tdease-workflow"
    output: str
    projection: Optional[WorkflowProjection] = None


class WorkflowGraphNode(WorkflowJobNode):
    status: Literal[
        "waiting", "up_to_date", "running", "succeeded", "failed", "cancelled"
    ]
    wildcards: dict[str, str] = Field(default_factory=dict)


class RunWorkflowGraphResponse(BaseModel):
    run_id: str
    nodes: list[WorkflowGraphNode] = Field(default_factory=list)
    edges: list[WorkflowJobEdge] = Field(default_factory=list)


class ResultRef(BaseModel):
    """
    Addressing reference to a Published Result (docs/design/CORE-ARCHITECTURE.md 3.2).

    digest absent = reference the Result's current value (unpinned, follows
    Recompute automatically); digest present = point at exactly those bytes
    (pinned, for Evidence/provenance). Both readings are legal; the only
    difference is whether the caller carries a digest — hence this model does
    not make digest required.
    """

    workspace_id: str
    run_id: str
    result_id: str
    digest: Optional[str] = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class RunResultEntry(BaseModel):
    """
    A single Published Result projection — one declared entry from result_specs
    joined against the file manifest.

    status is the outcome of that join, not a separate state machine
    (CORE-ARCHITECTURE.md 3.1): a declared output missing from the manifest ->
    "declared"; present -> "ready", carrying the current digest. A Result that
    was declared but never became ready must appear here (status="declared"),
    never be silently omitted; conversely, any file not declared in
    result_specs will never appear here — it is merely a Technical Artifact,
    reachable only via GET /api/v2/runs/{run_id}/files.
    """

    result_id: str
    name: str
    kind: str
    dimensions: dict[str, str]
    output: str
    status: Literal["declared", "ready"]
    digest: Optional[str] = None
    size: Optional[int] = None
    ref: ResultRef


class RunResultsResponse(BaseModel):
    """Response body for GET /api/v2/runs/{run_id}/results."""

    run_id: str
    results: list[RunResultEntry]
    definition_revision_id: Optional[str] = Field(
        default=None,
        description="Definition the current results manifest names -- the specs and "
        "files above belong to this revision, which may be older than the newest "
        "submitted definition.",
    )


class RunRerunRequest(BaseModel):
    mode: Literal["resume", "overwrite"] = "resume"


class RunActionResponse(BaseModel):
    run_id: str
    status: RunStatus
    action: Literal["cancel", "rerun"]
    accepted: bool = True
    mode: Optional[Literal["resume", "overwrite"]] = None


class RunTrashEntry(BaseModel):
    run_id: str
    name: str = ""
    workspace_id: str
    previous_status: RunStatus
    deleted_at: datetime
    deleted_by: str


class RunTrashListResponse(BaseModel):
    runs: list[RunTrashEntry]
    total: int


class RunStatusResponse(BaseModel):
    """
    Run status query response — a projection derived from run.json + events.jsonl.
    Not stored independently; a snapshot view computed per query.
    """

    run_id: str
    name: str = ""
    workspace_id: str
    workspace_run_path: Optional[str] = None
    current_revision: Optional[str] = None
    active_revision: Optional[str] = Field(
        default=None,
        description="Definition revision of the currently open execution range, if any.",
    )
    queued_revision: Optional[str] = Field(
        default=None,
        description="Definition revision waiting to start, if any.",
    )
    execution_count: int = Field(
        default=0,
        description="Number of started execution ranges recorded in the Journal.",
    )
    status: RunStatus
    materialization_strategy: str = Field(
        default="local_workspace_hardlink",
        description="Materialization strategy recorded by the server; see RunCommit.materialization_strategy.",
    )
    cores: int
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    rerun_mode: Literal["resume", "overwrite"] = "resume"
    labels: dict[str, str] = Field(default_factory=dict)
    result_file_count: int = 0
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    event_seq_last: int = Field(
        default=0,
        description="Last event sequence number, used for SSE Last-Event-ID",
    )


class RunListResponse(BaseModel):
    """Run list response — paginated, rebuildable."""

    runs: list[RunStatusResponse]
    total: int
    offset: int
    limit: int
    has_more: bool = False


class RunCreateResponse(RunStatusResponse):
    idempotent: bool = False
