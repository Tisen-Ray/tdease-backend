"""Single startup-resolved CPU budget for API limits and engine isolation."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceBudget:
    logical_cpus: int
    reserved_service_cpus: int
    compute_cpus: int
    compute_cpu_ids: tuple[int, ...]


def resolve_resource_budget(
    logical_cpus: int | None = None,
    reserved_override: str | None = None,
) -> ResourceBudget:
    total = max(1, logical_cpus if logical_cpus is not None else (os.cpu_count() or 1))
    raw_override = (
        reserved_override
        if reserved_override is not None
        else os.environ.get("TDEASE_RESERVED_LOGICAL_CPUS")
    )
    if raw_override is None or not raw_override.strip():
        reserved = min(4, total - 1) if total > 1 else 0
    else:
        try:
            reserved = int(raw_override)
        except ValueError as exc:
            raise RuntimeError("TDEASE_RESERVED_LOGICAL_CPUS must be an integer") from exc
        if reserved < 0:
            raise RuntimeError("TDEASE_RESERVED_LOGICAL_CPUS must be non-negative")

    reserved = min(reserved, total - 1) if total > 1 else 0
    compute = total - reserved
    return ResourceBudget(
        logical_cpus=total,
        reserved_service_cpus=reserved,
        compute_cpus=compute,
        compute_cpu_ids=tuple(range(compute)),
    )


# Environment and host topology are deployment settings. Freeze both at startup.
RESOURCE_BUDGET = resolve_resource_budget()
