"""TDEase-zero 服务层 — 执行。

Byte custody (CAS blobs, digests, path containment) is NOT here: it lives in
`src.execution_runtime.storage.StorageLayout` and
`src.execution_runtime.workspace_containment`, which are the only
implementations production reaches. A second, unreachable copy of both used to
sit in `src/services/files.py` (deleted -- REMAINING-DESIGNS.md Sec 14.2).
"""

from src.services.run_worker import execute, run_loop

__all__ = [
    "run_loop",
    "execute",
]
