"""Pure node placement: pick the node a run should land on.

Input snapshots follow tdease-node/schema/node-status.schema.json (possibly
with hub-stamped reachable/stale flags); error codes come from
tdease-node/schema/errors.schema.json. Zero IO, zero network: same inputs,
same decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


class Decision(TypedDict, total=False):
    node_id: str | None
    kind: str
    reason: str
    error_code: str


@dataclass(frozen=True)
class Requirement:
    tool: str | None = None
    min_version: str | None = None
    isolation: str | None = None  # "strict" | "licensed" | None
    need_disk_mb: int | None = None
    need_mem_mb: int | None = None
    pinned_node: str | None = None


def compare_versions(a: str, b: str) -> int:
    """Compare dotted versions segment by segment.

    Numeric segments compare numerically ("2.10" > "2.9"); non-numeric
    segments compare lexicographically; a missing trailing segment counts
    as 0 ("3.0.23133" < "3.1" because 0 < 1).
    """
    sa, sb = a.split("."), b.split(".")

    def cmp_seg(x: str, y: str) -> int:
        if x.isdigit() and y.isdigit():
            return (int(x) > int(y)) - (int(x) < int(y))
        return (x > y) - (x < y)

    for i in range(max(len(sa), len(sb))):
        x = sa[i] if i < len(sa) else "0"
        y = sb[i] if i < len(sb) else "0"
        c = cmp_seg(x, y)
        if c:
            return c
    return 0


def _queue_depth(node: dict[str, Any]) -> int:
    load = node.get("load", {})
    return int(load.get("running", 0)) + int(load.get("queued", 0))


def sort_candidates(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order candidates: local first, then ascending load, then stable id order."""
    return sorted(
        nodes,
        key=lambda n: (
            0 if n.get("node", {}).get("kind") == "local" else 1,
            _queue_depth(n),
            n.get("node", {}).get("id", ""),
        ),
    )


def _check(req: Requirement, node: dict[str, Any]) -> tuple[bool, str | None, str | None]:
    """Filter chain. Returns (ok, error_code, detail)."""
    nid = node.get("node", {}).get("id", "?")

    if not node.get("reachable", True) or node.get("stale", False):
        return False, "NODE_UNREACHABLE", f"{nid} unreachable or stale"

    tools = {t.get("id"): t for t in node.get("tools", [])}
    if req.tool is not None:
        t = tools.get(req.tool)
        if t is None:
            return False, "NODE_TOOL_MISSING", f"{nid} lacks tool {req.tool}"
        if req.min_version is not None and compare_versions(
            t.get("version", "0"), req.min_version
        ) < 0:
            return False, "NODE_TOOL_VERSION", (
                f"{nid} tool {req.tool} version {t.get('version', '?')} < {req.min_version}"
            )
        if req.isolation is not None and t.get("isolation") != req.isolation:
            return False, "NODE_ISOLATION", (
                f"{nid} tool {req.tool} isolation {t.get('isolation', '?')} != {req.isolation}"
            )

    cap = node.get("capacity", {})
    if req.need_disk_mb is not None and int(cap.get("scratchFreeMb", 0)) < req.need_disk_mb:
        return False, "NODE_DISK", (
            f"{nid} scratch {cap.get('scratchFreeMb', 0)}Mb < {req.need_disk_mb}Mb"
        )
    if req.need_mem_mb is not None and int(cap.get("memoryMb", 0)) < req.need_mem_mb:
        return False, "NODE_DISK", (
            f"{nid} memory {cap.get('memoryMb', 0)}Mb < {req.need_mem_mb}Mb"
        )

    return True, None, None


def _reason_ok(req: Requirement, node: dict[str, Any]) -> str:
    kind = node.get("node", {}).get("kind", "?")
    bits = [kind]
    if req.tool:
        ver = next(
            (t.get("version") for t in node.get("tools", []) if t.get("id") == req.tool),
            None,
        )
        bits.append(f"tool {req.tool} {ver}".rstrip() if ver else f"tool {req.tool} present")
    bits.append(f"queue {_queue_depth(node)}")
    return ", ".join(bits)


def place(req: Requirement, nodes: list[dict[str, Any]]) -> Decision:
    """Pick a node for a requirement; never silently reassign a pinned node."""
    if req.pinned_node:
        pinned = [n for n in nodes if n.get("node", {}).get("id") == req.pinned_node]
        if not pinned:
            return Decision(
                node_id=None,
                reason=f"pinned node {req.pinned_node} is not registered",
                error_code="NODE_UNREACHABLE",
            )
        node = pinned[0]
        ok, code, detail = _check(req, node)
        if not ok:
            return Decision(
                node_id=None,
                reason=f"pinned node {req.pinned_node} rejected: {code} ({detail})",
                error_code=code,
            )
        return Decision(
            node_id=req.pinned_node,
            kind=node.get("node", {}).get("kind", "?"),
            reason=_reason_ok(req, node),
        )

    if not nodes:
        return Decision(
            node_id=None, reason="no nodes registered", error_code="NODE_UNREACHABLE"
        )

    for node in sort_candidates(nodes):
        ok, code, detail = _check(req, node)
        if ok:
            return Decision(
                node_id=node["node"]["id"],
                kind=node["node"]["kind"],
                reason=_reason_ok(req, node),
            )
        return Decision(node_id=None, reason=detail or "", error_code=code or "NODE_UNREACHABLE")
    # unreachable: non-empty input always returns inside the loop
    raise AssertionError("unreachable")
