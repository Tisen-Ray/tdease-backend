"""Load the canonical Run lifecycle declaration exactly once."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_DECLARATION_PATH = Path(__file__).with_name("run_lifecycle.json")
LIFECYCLE_DECLARATION: dict[str, Any] = json.loads(
    _DECLARATION_PATH.read_text(encoding="utf-8")
)
LIFECYCLE_SCHEMA_VERSION = int(LIFECYCLE_DECLARATION["schema_version"])
