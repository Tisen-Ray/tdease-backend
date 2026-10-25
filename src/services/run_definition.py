"""Canonical immutable execution definition helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


_EXECUTION_FIELDS = (
    "workspace_tree_hash",
    "workspace_files",
    "snakefile",
    "config",
    "targets",
    "nodes",
    "result_specs",
)


def definition_revision_id(definition: Mapping[str, Any]) -> str:
    """Return the stable revision id for fields that change scientific execution."""
    frozen = {field: definition.get(field) for field in _EXECUTION_FIELDS}
    encoded = json.dumps(
        frozen,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "def-" + hashlib.sha256(encoded).hexdigest()[:24]


def freeze_definition(data: Mapping[str, Any]) -> dict[str, Any]:
    """Create the Backend's immutable Run definition record."""
    frozen = dict(data)
    forbidden = {
        "status",
        "pid",
        "engine_pid",
        "exit_code",
        "error",
        "started_at",
        "finished_at",
        "projected_at_seq",
        "current_revision",
        "rerun_mode",
        "mode",
        "local_workspace_root",
    }
    for field in forbidden:
        frozen.pop(field, None)
    frozen["definition_revision_id"] = definition_revision_id(frozen)
    return frozen
