"""TDEaseNexus service layer — execution.

Byte custody (CAS blobs, digests, path containment) is NOT here: it lives in
`src.execution_runtime.storage.StorageLayout` and
`src.execution_runtime.workspace_containment`, which are the only
implementations production reaches. A second, unreachable copy of both used to
sit in `src/services/files.py` (deleted -- docs/STATUS.md).
"""

__all__ = [
    "run_loop",
    "execute",
]


def __getattr__(name: str):
    """Keep the package API without pre-importing the ``-m`` entry module."""
    if name in __all__:
        from importlib import import_module

        run_worker = import_module("src.services.run_worker")
        return getattr(run_worker, name)
    raise AttributeError(name)
