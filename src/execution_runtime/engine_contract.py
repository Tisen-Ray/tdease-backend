"""Private contract between the TDEase runtime and its workflow engine process."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WorkflowEngineRequest(BaseModel):
    schema_version: Literal[1] = 1
    mode: Literal["execute", "dry-run"]
    snakefile: str = "Snakefile"
    config: dict = Field(default_factory=dict)
    cores: int = Field(default=1, ge=1, le=256)
    memory_mb: int = Field(default=4096, ge=1)
    targets: list[str] = Field(default_factory=list)
    rerun_mode: Literal["resume", "overwrite"] = "resume"
    rerun_incomplete: bool = True
    retries: int = Field(default=0, ge=0)
    unlock_before_execute: bool = False
    projection_path: str | None = None
    job_event_path: str | None = None
    # Fleet dispatch section; present only when a pinned remote node was
    # resolved at schedule time: {endpoint, token, tool_map, executor_dir}.
    fleet: dict | None = None
