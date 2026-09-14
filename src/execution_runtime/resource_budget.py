"""Single startup-resolved CPU budget for API limits and engine isolation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.backend_settings import BACKEND_SETTINGS, RUNTIME_INVENTORY


@dataclass(frozen=True)
class ResourceBudget:
    logical_cpus: int
    reserved_service_cpus: int
    compute_cpus: int
    compute_cpu_ids: tuple[int, ...]
    total_memory_mb: int
    reserved_service_memory_mb: int
    compute_memory_mb: int
    max_concurrent_runs: Literal[1] = 1


def resolve_resource_budget(
    logical_cpus: int | None = None,
    reserved_override: str | None = None,
    total_memory_mb: int | None = None,
    reserved_memory_override: str | None = None,
) -> ResourceBudget:
    total = max(
        1,
        logical_cpus if logical_cpus is not None else RUNTIME_INVENTORY.logical_cpus,
    )
    raw_override = reserved_override
    if raw_override is None or not raw_override.strip():
        reserved = min(4, total - 1) if total > 1 else 0
    else:
        try:
            reserved = int(raw_override)
        except ValueError as exc:
            raise RuntimeError(
                "TDEASE_RESERVED_LOGICAL_CPUS must be an integer"
            ) from exc
        if reserved < 0:
            raise RuntimeError("TDEASE_RESERVED_LOGICAL_CPUS must be non-negative")

    reserved = min(reserved, total - 1) if total > 1 else 0
    compute = total - reserved

    memory_total = max(
        1,
        total_memory_mb
        if total_memory_mb is not None
        else RUNTIME_INVENTORY.total_memory_mb,
    )
    raw_memory_override = reserved_memory_override
    # Desktop runs share a machine with Electron, the API and the operating
    # system. Reserve 10 GiB by default, but never starve a smaller machine of
    # a 4 GiB workflow working set. Operators may still set an explicit
    # TDEASE_RESERVED_MEMORY_MB policy at deployment time.
    minimum_compute_memory = min(memory_total, 4096)
    if raw_memory_override is None or not raw_memory_override.strip():
        reserved_memory = 10 * 1024
    else:
        try:
            reserved_memory = int(raw_memory_override)
        except ValueError as exc:
            raise RuntimeError("TDEASE_RESERVED_MEMORY_MB must be an integer") from exc
        if reserved_memory < 0:
            raise RuntimeError("TDEASE_RESERVED_MEMORY_MB must be non-negative")
    reserved_memory = min(
        reserved_memory, max(0, memory_total - minimum_compute_memory)
    )
    compute_memory = memory_total - reserved_memory

    return ResourceBudget(
        logical_cpus=total,
        reserved_service_cpus=reserved,
        compute_cpus=compute,
        compute_cpu_ids=tuple(range(compute)),
        total_memory_mb=memory_total,
        reserved_service_memory_mb=reserved_memory,
        compute_memory_mb=compute_memory,
    )


# Both the enforcement wall and public capability document derive from the same
# startup snapshot. No consumer resolves environment or host topology itself.
RESOURCE_BUDGET = resolve_resource_budget(
    logical_cpus=RUNTIME_INVENTORY.logical_cpus,
    reserved_override=BACKEND_SETTINGS.reserved_logical_cpus,
    total_memory_mb=RUNTIME_INVENTORY.total_memory_mb,
    reserved_memory_override=BACKEND_SETTINGS.reserved_memory_mb,
)
