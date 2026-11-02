"""
The failure contract, as code — domain half.

Sole implementation of `docs/spec/FAILURE-CONTRACT.md`. Every fact this module
encodes (envelope shape, the closed `code` enumeration, the domain -> HTTP status
table, the redaction rule) is owned by that document; this module must not drift
from it without the document changing first.

This is the `src/` (domain) half: it encodes the contract and the `TDEaseError`
exception itself, and it must not import FastAPI — `src/` never imports `app/`
and never imports FastAPI (docs/design/THREE-REPOSITORY-ARCHITECTURE.md §4.1).
The FastAPI wiring that turns a raised `TDEaseError` into the envelope on the
wire lives in `app/errors.py` (transport). Raise sites in `src/**` and `app/**`
both raise this single error type; a raise site never picks a `domain` or an
`http_status` — both are derived from `code` here.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

__all__ = [
    "ErrorCode",
    "ErrorDomain",
    "TDEaseError",
    "http_status_for",
    "redact",
]


# ---------------------------------------------------------------------------
# §2 — Domains
# ---------------------------------------------------------------------------


class ErrorDomain(str, Enum):
    """The six closed domains of FAILURE-CONTRACT.md §2."""

    WORKSPACE = "workspace"
    RUN = "run"
    ENGINE = "engine"
    AGENT = "agent"
    BACKEND = "backend"
    ENVIRONMENT = "environment"


# ---------------------------------------------------------------------------
# §3 — The closed `code` enumeration
# ---------------------------------------------------------------------------


class ErrorCode(str, Enum):
    """
    The closed, versioned error code enumeration of FAILURE-CONTRACT.md §3.

    New members are additive. An existing member's domain and meaning never
    change; see `CODE_DOMAIN` immediately below, which is exhaustive over this
    enum and is asserted so in the code (a forgotten mapping fails at import,
    not as a runtime `KeyError`).
    """

    # -- workspace (§3.1) --
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"
    WORKSPACE_IDENTITY_INVALID = "WORKSPACE_IDENTITY_INVALID"
    WORKSPACE_PATH_ESCAPE = "WORKSPACE_PATH_ESCAPE"
    WORKSPACE_FILE_NOT_FOUND = "WORKSPACE_FILE_NOT_FOUND"
    WORKSPACE_DIGEST_MISMATCH = "WORKSPACE_DIGEST_MISMATCH"
    WORKSPACE_BLOB_NOT_FOUND = "WORKSPACE_BLOB_NOT_FOUND"
    WORKSPACE_QUOTA_EXCEEDED = "WORKSPACE_QUOTA_EXCEEDED"

    # -- run (§3.2) --
    RUN_NOT_FOUND = "RUN_NOT_FOUND"
    RUN_NOT_QUEUED = "RUN_NOT_QUEUED"
    RUN_NOT_TERMINAL = "RUN_NOT_TERMINAL"
    RUN_IDEMPOTENCY_CONFLICT = "RUN_IDEMPOTENCY_CONFLICT"
    RUN_PLAN_INVALID = "RUN_PLAN_INVALID"
    RUN_PLAN_STALE = "RUN_PLAN_STALE"
    RUN_MODE_MISMATCH = "RUN_MODE_MISMATCH"
    RUN_DRY_RUN_UNAVAILABLE = "RUN_DRY_RUN_UNAVAILABLE"
    RUN_FILE_NOT_FOUND = "RUN_FILE_NOT_FOUND"
    RUN_TRASH_NOT_FOUND = "RUN_TRASH_NOT_FOUND"
    RUN_NODE_NOT_FOUND = "RUN_NODE_NOT_FOUND"
    RUN_TEMPLATE_NOT_FOUND = "RUN_TEMPLATE_NOT_FOUND"
    RUN_TEMPLATE_ID_INVALID = "RUN_TEMPLATE_ID_INVALID"

    # -- engine (§3.3) --
    ENGINE_INVALID_WORKFLOW = "ENGINE_INVALID_WORKFLOW"
    ENGINE_MISSING_INPUT = "ENGINE_MISSING_INPUT"
    ENGINE_AMBIGUOUS_RULE = "ENGINE_AMBIGUOUS_RULE"
    ENGINE_CYCLE_DETECTED = "ENGINE_CYCLE_DETECTED"
    ENGINE_TOOL_NOT_FOUND = "ENGINE_TOOL_NOT_FOUND"
    ENGINE_RESOURCE_EXHAUSTED = "ENGINE_RESOURCE_EXHAUSTED"
    ENGINE_TASK_FAILED = "ENGINE_TASK_FAILED"
    ENGINE_INCOMPLETE_OUTPUT = "ENGINE_INCOMPLETE_OUTPUT"
    ENGINE_CANCELLED = "ENGINE_CANCELLED"
    ENGINE_RUNTIME_INTERNAL = "ENGINE_RUNTIME_INTERNAL"

    # -- agent (§3.4) --
    AGENT_TOOL_NOT_REGISTERED = "AGENT_TOOL_NOT_REGISTERED"
    AGENT_OUTPUT_CONTRACT_VIOLATION = "AGENT_OUTPUT_CONTRACT_VIOLATION"
    AGENT_IDENTITY_FORGED = "AGENT_IDENTITY_FORGED"
    AGENT_PROMPT_SNAPSHOT_MISSING = "AGENT_PROMPT_SNAPSHOT_MISSING"

    # -- backend (§3.5) --
    BACKEND_INTERNAL = "BACKEND_INTERNAL"
    BACKEND_PACKAGE_NOT_FOUND = "BACKEND_PACKAGE_NOT_FOUND"
    BACKEND_PACKAGE_DIGEST_UNRESOLVABLE = "BACKEND_PACKAGE_DIGEST_UNRESOLVABLE"
    BACKEND_UPLOAD_INCOMPLETE = "BACKEND_UPLOAD_INCOMPLETE"
    BACKEND_PRESIGNED_EXPIRED = "BACKEND_PRESIGNED_EXPIRED"
    # Hub-side node pairing: a malformed enrollment string is a caller error
    # against the Hub's own registry, not a Run fault and not a package fault.

    # -- environment (§3.6) --
    # The four AUTH_* codes are environment-domain because a Desktop launch that
    # cannot authenticate is a broken environment, not a malformed request and not
    # a Backend fault. They were emitted on the wire by app/auth.py before
    # they existed here, which is precisely the drift a closed enumeration exists
    # to prevent.
    AUTH_BOOTSTRAP_SECRET_MISSING = "AUTH_BOOTSTRAP_SECRET_MISSING"
    AUTH_BOOTSTRAP_SECRET_INVALID = "AUTH_BOOTSTRAP_SECRET_INVALID"
    AUTH_BOOTSTRAP_UNAVAILABLE = "AUTH_BOOTSTRAP_UNAVAILABLE"
    AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID"
    AUTH_ORIGIN_FORBIDDEN = "AUTH_ORIGIN_FORBIDDEN"
    AUTH_SCOPE_DENIED = "AUTH_SCOPE_DENIED"
    ENVIRONMENT_BOOTSTRAP_UNAVAILABLE = "ENVIRONMENT_BOOTSTRAP_UNAVAILABLE"
    ENVIRONMENT_UNAUTHORIZED = "ENVIRONMENT_UNAUTHORIZED"
    ENVIRONMENT_DEPENDENCY_MISSING = "ENVIRONMENT_DEPENDENCY_MISSING"
    ENVIRONMENT_PORT_UNAVAILABLE = "ENVIRONMENT_PORT_UNAVAILABLE"
    ENVIRONMENT_DISK_UNAVAILABLE = "ENVIRONMENT_DISK_UNAVAILABLE"


# `domain` is derived from `code`, never chosen independently at a raise site
# (FAILURE-CONTRACT.md §1.1). This map is exhaustive over `ErrorCode`; the
# contract is asserted so in the code (a forgotten mapping fails at import,
# not as a runtime `KeyError`).
CODE_DOMAIN: dict[ErrorCode, ErrorDomain] = {
    # workspace
    ErrorCode.WORKSPACE_NOT_FOUND: ErrorDomain.WORKSPACE,
    ErrorCode.WORKSPACE_IDENTITY_INVALID: ErrorDomain.WORKSPACE,
    ErrorCode.WORKSPACE_PATH_ESCAPE: ErrorDomain.WORKSPACE,
    ErrorCode.WORKSPACE_FILE_NOT_FOUND: ErrorDomain.WORKSPACE,
    ErrorCode.WORKSPACE_DIGEST_MISMATCH: ErrorDomain.WORKSPACE,
    ErrorCode.WORKSPACE_BLOB_NOT_FOUND: ErrorDomain.WORKSPACE,
    ErrorCode.WORKSPACE_QUOTA_EXCEEDED: ErrorDomain.WORKSPACE,
    # run
    ErrorCode.RUN_NOT_FOUND: ErrorDomain.RUN,
    ErrorCode.RUN_NOT_QUEUED: ErrorDomain.RUN,
    ErrorCode.RUN_NOT_TERMINAL: ErrorDomain.RUN,
    ErrorCode.RUN_IDEMPOTENCY_CONFLICT: ErrorDomain.RUN,
    ErrorCode.RUN_PLAN_INVALID: ErrorDomain.RUN,
    ErrorCode.RUN_PLAN_STALE: ErrorDomain.RUN,
    ErrorCode.RUN_MODE_MISMATCH: ErrorDomain.RUN,
    ErrorCode.RUN_DRY_RUN_UNAVAILABLE: ErrorDomain.RUN,
    ErrorCode.RUN_FILE_NOT_FOUND: ErrorDomain.RUN,
    ErrorCode.RUN_TRASH_NOT_FOUND: ErrorDomain.RUN,
    ErrorCode.RUN_NODE_NOT_FOUND: ErrorDomain.RUN,
    ErrorCode.RUN_TEMPLATE_NOT_FOUND: ErrorDomain.RUN,
    ErrorCode.RUN_TEMPLATE_ID_INVALID: ErrorDomain.RUN,
    # engine
    ErrorCode.ENGINE_INVALID_WORKFLOW: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_MISSING_INPUT: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_AMBIGUOUS_RULE: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_CYCLE_DETECTED: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_TOOL_NOT_FOUND: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_RESOURCE_EXHAUSTED: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_TASK_FAILED: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_INCOMPLETE_OUTPUT: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_CANCELLED: ErrorDomain.ENGINE,
    ErrorCode.ENGINE_RUNTIME_INTERNAL: ErrorDomain.ENGINE,
    # agent
    ErrorCode.AGENT_TOOL_NOT_REGISTERED: ErrorDomain.AGENT,
    ErrorCode.AGENT_OUTPUT_CONTRACT_VIOLATION: ErrorDomain.AGENT,
    ErrorCode.AGENT_IDENTITY_FORGED: ErrorDomain.AGENT,
    ErrorCode.AGENT_PROMPT_SNAPSHOT_MISSING: ErrorDomain.AGENT,
    # backend
    ErrorCode.BACKEND_INTERNAL: ErrorDomain.BACKEND,
    ErrorCode.BACKEND_PACKAGE_NOT_FOUND: ErrorDomain.BACKEND,
    ErrorCode.BACKEND_PACKAGE_DIGEST_UNRESOLVABLE: ErrorDomain.BACKEND,
    ErrorCode.BACKEND_UPLOAD_INCOMPLETE: ErrorDomain.BACKEND,
    ErrorCode.BACKEND_PRESIGNED_EXPIRED: ErrorDomain.BACKEND,
    # environment
    ErrorCode.AUTH_BOOTSTRAP_SECRET_MISSING: ErrorDomain.ENVIRONMENT,
    ErrorCode.AUTH_BOOTSTRAP_SECRET_INVALID: ErrorDomain.ENVIRONMENT,
    ErrorCode.AUTH_BOOTSTRAP_UNAVAILABLE: ErrorDomain.ENVIRONMENT,
    ErrorCode.AUTH_TOKEN_INVALID: ErrorDomain.ENVIRONMENT,
    ErrorCode.AUTH_ORIGIN_FORBIDDEN: ErrorDomain.ENVIRONMENT,
    ErrorCode.AUTH_SCOPE_DENIED: ErrorDomain.ENVIRONMENT,
    ErrorCode.ENVIRONMENT_BOOTSTRAP_UNAVAILABLE: ErrorDomain.ENVIRONMENT,
    ErrorCode.ENVIRONMENT_UNAUTHORIZED: ErrorDomain.ENVIRONMENT,
    ErrorCode.ENVIRONMENT_DEPENDENCY_MISSING: ErrorDomain.ENVIRONMENT,
    ErrorCode.ENVIRONMENT_PORT_UNAVAILABLE: ErrorDomain.ENVIRONMENT,
    ErrorCode.ENVIRONMENT_DISK_UNAVAILABLE: ErrorDomain.ENVIRONMENT,
}


# ---------------------------------------------------------------------------
# §4 — http_status is derived from domain, not chosen per raise site
# ---------------------------------------------------------------------------

# §6: `engine` maps to a 200-family status because a workflow failure is a
# successful observation of a Run, never a product error. See FAILURE-CONTRACT.md
# §4 and §6 for the full reasoning behind every row here.
DOMAIN_HTTP_STATUS: dict[ErrorDomain, int] = {
    ErrorDomain.WORKSPACE: 400,
    ErrorDomain.RUN: 409,
    ErrorDomain.ENGINE: 200,
    ErrorDomain.AGENT: 422,
    ErrorDomain.BACKEND: 500,
    ErrorDomain.ENVIRONMENT: 503,
}


# A closed, per-code override of the domain default above.
#
# FAILURE-CONTRACT.md section 4 originally read "this table is the only place
# http_status is decided". That held the right invariant for the wrong reason: the
# invariant worth keeping is that **a raise site cannot pick a status**, and a
# per-code table keeps that just as strictly as a per-domain one. What a per-domain
# table cannot express is that one domain carries several distinct transport
# meanings that HTTP already distinguishes and that every HTTP client already
# branches on:
#
#   - The `environment` domain contains the authentication failures. A 503 for a
#     bad Bearer token is not a taste question: 401 with a WWW-Authenticate header
#     is what makes a token challenge a token challenge, and no client's auth-retry
#     path fires on 503. A one-shot bootstrap secret that was already consumed is
#     410 Gone for the same reason -- it genuinely will not come back.
#   - The `run` domain collapses "this Run does not exist" with "this Run conflicts
#     with what you asked". Serving 409 for an unknown run_id would also erase the
#     deliberate information-hiding property that another Principal's Run is
#     indistinguishable from an absent one (see _owned_run in app/api/runs_v2.py):
#     404 is what both must return.
#   - The `workspace` domain collapses "fix your request" with "you may not reach
#     that path". A containment rejection is 403; it is not something the caller
#     can correct by editing a field.
#
# Every other code takes its domain's status. Adding a code still never lets a
# raise site choose -- it only joins this table or the domain default.
CODE_HTTP_STATUS: dict[ErrorCode, int] = {
    # environment -- protocol-mandated auth statuses
    ErrorCode.AUTH_BOOTSTRAP_SECRET_MISSING: 401,
    ErrorCode.AUTH_BOOTSTRAP_SECRET_INVALID: 401,
    ErrorCode.AUTH_TOKEN_INVALID: 401,
    ErrorCode.AUTH_BOOTSTRAP_UNAVAILABLE: 410,
    ErrorCode.AUTH_ORIGIN_FORBIDDEN: 403,
    ErrorCode.AUTH_SCOPE_DENIED: 403,
    # absent, not conflicting
    ErrorCode.RUN_NOT_FOUND: 404,
    ErrorCode.RUN_FILE_NOT_FOUND: 404,
    ErrorCode.RUN_TRASH_NOT_FOUND: 404,
    ErrorCode.RUN_NODE_NOT_FOUND: 404,
    ErrorCode.RUN_TEMPLATE_NOT_FOUND: 404,
    ErrorCode.WORKSPACE_NOT_FOUND: 404,
    ErrorCode.WORKSPACE_FILE_NOT_FOUND: 404,
    ErrorCode.WORKSPACE_BLOB_NOT_FOUND: 404,
    # forbidden, not correctable by editing the request
    ErrorCode.WORKSPACE_PATH_ESCAPE: 403,
    # bad pairing payload — correctable by re-running enroll on the node
}


def http_status_for(code: ErrorCode) -> int:
    """The one place a status is resolved: per-code override, else domain default."""

    return CODE_HTTP_STATUS.get(code, DOMAIN_HTTP_STATUS[CODE_DOMAIN[code]])


# ---------------------------------------------------------------------------
# §5 — Redaction, applied at construction
# ---------------------------------------------------------------------------

_SECRET_KEY_PATTERN = re.compile(
    r"token|secret|key|password|authorization", re.IGNORECASE
)

# Windows drive-letter absolute path (`C:\...` / `C:/...`), UNC share
# (`\\host\share\...`), or a POSIX-style leading `/`.
_ABSOLUTE_PATH_PATTERN = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\[^\\]+\\|/)")

_REDACTED_VALUE = "[redacted]"
_REDACTED_PATH_VALUE = "[redacted-path]"


def _looks_like_absolute_path(value: str) -> bool:
    return bool(_ABSOLUTE_PATH_PATTERN.match(value))


def _is_within_workspace(value: str, workspace_root: str) -> bool:
    normalized_value = value.replace("\\", "/").rstrip("/")
    normalized_root = workspace_root.replace("\\", "/").rstrip("/")
    return normalized_value == normalized_root or normalized_value.startswith(
        normalized_root + "/"
    )


def redact(
    details: dict[str, Any] | None, workspace_root: str | None = None
) -> dict[str, Any] | None:
    """
    Apply the FAILURE-CONTRACT.md §5 redaction rule to a `details` mapping.

    Two independent rules, applied recursively over dicts and lists:

    1. Key-based: a mapping key whose name contains (case-insensitively) one of
       `token`, `secret`, `key`, `password` or `authorization` has its value
       replaced, regardless of the value's own shape.
    2. Shape-based: a string value that looks like an absolute filesystem path
       is replaced unless it falls inside `workspace_root` (when given). With no
       `workspace_root`, every absolute-path-shaped string is redacted — a
       `details` object should only ever carry Workspace-relative paths, so an
       absolute path's mere presence is the anomaly.

    Returns `None` unchanged (so `TDEaseError` can omit an absent `details`
    entirely from the envelope per §1.2).
    """

    if details is None:
        return None
    return _redact_value(details, workspace_root)  # type: ignore[return-value]


def _redact_value(value: Any, workspace_root: str | None) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _SECRET_KEY_PATTERN.search(key):
                redacted[key] = _REDACTED_VALUE
            else:
                redacted[key] = _redact_value(item, workspace_root)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item, workspace_root) for item in value]
    if isinstance(value, str) and _looks_like_absolute_path(value):
        if workspace_root and _is_within_workspace(value, workspace_root):
            return value
        return _REDACTED_PATH_VALUE
    return value


# ---------------------------------------------------------------------------
# §1 — The envelope
# ---------------------------------------------------------------------------


class TDEaseError(Exception):
    """
    The one error shape of FAILURE-CONTRACT.md §1.

    `domain` and `http_status` are derived from `code` (via `CODE_DOMAIN` and
    `DOMAIN_HTTP_STATUS`) and are never accepted as constructor arguments — a
    raise site cannot cause a code to disagree with its registered domain, and
    cannot pick a status per call site (§4).

    `message`, `remedy`, `retryable`, `details` and `cause` are supplied by the
    raise site: `retryable` is a real boolean decided from domain semantics, not
    inferred from `http_status` (two errors sharing a domain, even the same
    status, may disagree on whether they are retryable).

    `details` is redacted in `__init__`, before any other code can observe it
    (§5) — a value never constructed cannot leak through a log path someone
    forgot about.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        remedy: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
        cause: dict[str, Any] | None = None,
        workspace_root: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.domain = CODE_DOMAIN[code]
        self.http_status = http_status_for(code)
        self.message = message
        self.remedy = remedy
        self.retryable = bool(retryable)
        self.details = redact(details, workspace_root)
        # cause is redacted on the same terms as details. It was not, and the only
        # reason that had not leaked yet is that no raise site populated it -- a
        # guarantee that holds only until the first one does.
        self.cause = redact(cause, workspace_root)

    def to_envelope(self) -> dict[str, Any]:
        """Produce the exact JSON of FAILURE-CONTRACT.md §1."""

        error: dict[str, Any] = {
            "code": self.code.value,
            "domain": self.domain.value,
            "message": self.message,
            "remedy": self.remedy,
            "retryable": self.retryable,
        }
        if self.details is not None:
            error["details"] = self.details
        if self.cause is not None:
            error["cause"] = self.cause
        return {"error": error}

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"
