"""Filesystem compatibility boundary for the embedded workflow engine."""

from __future__ import annotations

import os
import shutil
import stat
import sys
from pathlib import Path


def prepare_engine_layout(root: Path) -> Path:
    """Move legacy engine state under `.tdease/engine` and clear its old name."""
    engine_root = root / ".tdease" / "engine"
    engine_root.mkdir(parents=True, exist_ok=True)
    legacy = root / ".snakemake"
    if not legacy.exists() and not legacy.is_symlink():
        return engine_root

    if legacy.is_symlink() or _is_reparse_point(legacy):
        cleanup_engine_alias(root)
        return engine_root

    for source in legacy.iterdir():
        target = engine_root / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    shutil.rmtree(legacy)
    return engine_root


def create_engine_alias(target: Path, alias: Path) -> None:
    """Point the upstream compatibility name at the TDEase-owned engine state.

    A junction is created through `_winapi.CreateJunction` rather than
    `cmd /c mklink /J`: no shell, no argument quoting, and therefore no path
    character (space, `&`, `%`, non-ASCII) can change the outcome. Windows
    junctions need no privilege, unlike symlinks.
    """
    if sys.platform == "win32":
        import _winapi  # Windows-only; junction creation needs no privilege

        _winapi.CreateJunction(str(target), str(alias))
    else:
        os.symlink(str(target), str(alias), target_is_directory=True)


def cleanup_engine_alias(root: Path) -> None:
    """Remove the upstream compatibility name without touching engine state."""
    alias = root / ".snakemake"
    if not alias.exists() and not alias.is_symlink():
        return
    try:
        if alias.is_symlink():
            alias.unlink()
        elif sys.platform == "win32" and _is_reparse_point(alias):
            os.rmdir(alias)
        else:
            shutil.rmtree(alias)
    except OSError:
        # A forced process kill can race cleanup. The parent runtime retries.
        pass


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(os.lstat(path), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
