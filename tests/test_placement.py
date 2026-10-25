"""Node placement contract: pinning never reassigns, filtering is fail-closed.

Pins the semantics the run dispatch depends on: candidates are ordered
local-first then least-loaded, every rejection carries exactly one code from
errors.schema.json, and a pinned node is never silently redirected.
"""

from __future__ import annotations

from src.services.placement import Decision, Requirement, compare_versions, place, sort_candidates


def node(
    nid: str = "n_abc12345",
    kind: str = "local",
    *,
    reachable: bool = True,
    stale: bool = False,
    tools: list[dict] | None = None,
    scratch_mb: int = 100_000,
    memory_mb: int = 64_000,
    running: int = 0,
    queued: int = 0,
) -> dict:
    return {
        "node": {"id": nid, "kind": kind},
        "asOf": "2026-01-01T00:00:00Z",
        "reachable": reachable,
        "stale": stale,
        "capacity": {"cpus": 8, "memoryMb": memory_mb, "scratchFreeMb": scratch_mb},
        "load": {"running": running, "queued": queued, "maxConcurrent": 1, "queueMax": 8},
        "tools": tools if tools is not None else [],
    }


def msconvert(version: str = "3.1", isolation: str = "strict") -> dict:
    return {"id": "msconvert", "version": version, "isolation": isolation}


def test_single_candidate_is_selected_directly() -> None:
    d = place(
        Requirement(tool="msconvert", min_version="3.0"),
        [node(tools=[msconvert()])],
    )
    assert d == {
        "node_id": "n_abc12345",
        "kind": "local",
        "reason": "local, tool msconvert 3.1, queue 0",
    }


def test_local_beats_less_loaded_server() -> None:
    server = node("n_srv00001", "server", tools=[msconvert()], running=0, queued=0)
    local = node("n_abc12345", "local", tools=[msconvert()], running=2, queued=1)
    d = place(Requirement(tool="msconvert"), [server, local])
    assert d["node_id"] == "n_abc12345"
    # Same set, no local: the idle server wins.
    d2 = place(Requirement(tool="msconvert"), [server])
    assert d2["node_id"] == "n_srv00001"


def test_sort_candidates_orders_local_load_id() -> None:
    a = node("n_aaaaaaaa", "server", running=1, queued=1)
    b = node("n_bbbbbbbb", "server", running=0, queued=0)
    c = node("n_cccccccc", "local", running=5, queued=5)
    assert [n["node"]["id"] for n in sort_candidates([a, b, c])] == [
        "n_cccccccc",
        "n_bbbbbbbb",
        "n_aaaaaaaa",
    ]


def test_pinned_unreachable_never_reassigns() -> None:
    healthy = node("n_abc12345", tools=[msconvert()])
    pinned = node("n_dead00000", "server", tools=[msconvert()], reachable=False)
    d = place(Requirement(tool="msconvert", pinned_node="n_dead00000"), [healthy, pinned])
    assert d["node_id"] is None
    assert d["error_code"] == "NODE_UNREACHABLE"
    assert "n_dead00000" in d["reason"]

    missing = place(Requirement(pinned_node="n_zzz00000"), [healthy])
    assert missing["node_id"] is None
    assert missing["error_code"] == "NODE_UNREACHABLE"
    assert "not registered" in missing["reason"]


def test_filter_chain_error_codes() -> None:
    ok = node("n_ok000000", "server", tools=[msconvert()], scratch_mb=10, memory_mb=10)
    # tool missing
    d = place(Requirement(tool="msconvert"), [node("n_a0000000", "server")])
    assert (d["node_id"], d["error_code"]) == (None, "NODE_TOOL_MISSING")
    # version too low
    d = place(
        Requirement(tool="msconvert", min_version="3.1"),
        [node("n_b0000000", "server", tools=[msconvert("3.0.23133")])],
    )
    assert d["error_code"] == "NODE_TOOL_VERSION"
    # isolation mismatch: required strict, tool is licensed
    d = place(
        Requirement(tool="msconvert", isolation="strict"),
        [node("n_c0000000", "server", tools=[msconvert(isolation="licensed")])],
    )
    assert d["error_code"] == "NODE_ISOLATION"
    # disk
    d = place(Requirement(need_disk_mb=50), [node("n_d0000000", "server", scratch_mb=10)])
    assert d["error_code"] == "NODE_DISK"
    assert "scratch" in d["reason"]
    # memory — same code, reason mentions memory
    d = place(Requirement(need_mem_mb=50), [node("n_e0000000", "server", memory_mb=10)])
    assert d["error_code"] == "NODE_DISK"
    assert "memory" in d["reason"]
    # unreachable flag wins the chain
    d = place(Requirement(tool="msconvert"), [node("n_f0000000", "server", reachable=False)])
    assert d["error_code"] == "NODE_UNREACHABLE"
    assert ok  # silence unused; kept as a healthy reference


def test_empty_node_list_is_unreachable() -> None:
    d = place(Requirement(tool="msconvert"), [])
    assert d == {
        "node_id": None,
        "reason": "no nodes registered",
        "error_code": "NODE_UNREACHABLE",
    }


def test_compare_versions() -> None:
    assert compare_versions("3.0.23133", "3.1") < 0
    assert compare_versions("2.10", "2.9") > 0
    assert compare_versions("1.2.3", "1.2.3") == 0
    assert compare_versions("1.2", "1.2.0") == 0
