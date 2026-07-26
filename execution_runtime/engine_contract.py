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
    targets: list[str] = Field(default_factory=list)
    rerun_mode: Literal["resume", "overwrite"] = "resume"
    rerun_incomplete: bool = True
    retries: int = Field(default=0, ge=0)
