"""The single node-binding seam.

Every path that hands a Run definition to the engine — the Backend dry-run and
the worker's execution — resolves node bindings through ``engine_config`` so
``config["nodes"]`` injection has exactly one implementation. Bound node
packages stay in the Backend catalog; the engine reaches them through absolute
paths and nothing tool-related is ever written under the Run directory
(docs/spec/WORKFLOW-RUN.md).
"""

from __future__ import annotations

from src.contracts import RunCommit
from src.contracts.errors import ErrorCode, TDEaseError
from src.execution_runtime.storage import get_tools_root


def engine_config(commit: RunCommit) -> dict:
    """Resolve a commit's node bindings into the engine's config.

    Raises TDEaseError(RUN_NODE_NOT_FOUND) when a bound id is not in the
    catalog — the same structured failure for dry-run and execution, whether
    the catalog changed after submit or not.
    """
    from src.services.node_catalog import bound_node_paths, resolve_bindings

    try:
        resolved = resolve_bindings(get_tools_root(), commit.nodes)
    except ValueError as exc:
        raise TDEaseError(
            code=ErrorCode.RUN_NODE_NOT_FOUND,
            message=f"The Run node bindings could not be resolved: {exc}",
            remedy="Correct the node bindings on the commit, or install the missing node package.",
            retryable=False,
        ) from exc
    bound_paths = bound_node_paths(resolved)
    if not bound_paths:
        return dict(commit.config)
    return {**commit.config, "nodes": bound_paths}
