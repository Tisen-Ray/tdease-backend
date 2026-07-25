"""TDEase-owned workflow engine entrypoint.

The upstream engine supplies DAG and incremental execution algorithms. TDEase
owns every persistent path and every product-facing log name.

Internalization of Snakemake's `.snakemake/` directory:
  Upstream hardcodes `.snakemake/` in several modules (persistence, logging,
  shell tmpdir, workflow tmpdir) with no single redirect knob. Rather than
  chase every call site, we make `.snakemake` itself a DIRECTORY JUNCTION to
  `.tdease/engine/`. Snakemake sees the path it expects and writes through it;
  physically, only `.tdease/` exists on disk.

  Windows junctions (mklink /J) do NOT require admin privileges, unlike symlinks.
  POSIX falls back to os.symlink (target_is_directory=True); if that fails
  (permissions), we let upstream create a real `.snakemake/` as a degraded mode.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    import snakemake.cli as engine_cli
    import snakemake.shell as engine_shell
    import snakemake.workflow as engine_workflow
    from snakemake.persistence.file import FilePersistence as UpstreamFilePersistence

    # One hidden dir to rule them all: .tdease/engine/ holds everything
    # upstream would have put under .snakemake/.
    engine_root = Path.cwd() / ".tdease" / "engine"
    engine_root.mkdir(parents=True, exist_ok=True)

    # Persistence already honors its `path` arg — point it at the engine root.
    class TDEaseEnginePersistence(UpstreamFilePersistence):
        def __init__(self, *args, path=None, **kwargs):
            super().__init__(*args, path=path or engine_root, **kwargs)

    engine_workflow.FilePersistence = TDEaseEnginePersistence

    # Everything else (logging, shell tmpdir, workflow tmpdir, storage) reads
    # the literal ".snakemake" relative to cwd. Make that name a junction into
    # the engine root so writes land inside .tdease/engine/ transparently.
    snakemake_dir = Path.cwd() / ".snakemake"
    if not snakemake_dir.exists():
        _junction(engine_root, snakemake_dir)

    # TDEase writes long shell commands itself through the managed process
    # boundary; prevent the upstream helper from creating a branded breadcrumb.
    engine_shell.MAX_ARG_LEN = 2**31 - 1

    original_output_settings = engine_cli.create_output_settings

    def tdease_output_settings(args, log_handler_settings):
        settings = original_output_settings(args, log_handler_settings)
        settings.enable_file_logging = False
        settings.skip_plugin_handlers = True
        settings.nocolor = True
        return settings

    engine_cli.create_output_settings = tdease_output_settings
    result = engine_cli.main()
    return int(result or 0)


def _junction(target: Path, link: Path) -> None:
    """Create `link` as a directory junction (Windows) or symlink (POSIX) to
    `target`. Raises OSError if unsupported/insufficient privileges — caller
    decides whether to fall back to upstream's real .snakemake/ dir."""
    if sys.platform == "win32":
        # mklink /J — junction, no admin needed (unlike /D symlinks).
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=True, capture_output=True,
        )
    else:
        os.symlink(str(target), str(link), target_is_directory=True)


if __name__ == "__main__":
    raise SystemExit(main())
