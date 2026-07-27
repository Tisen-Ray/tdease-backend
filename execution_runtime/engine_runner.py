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
import sys
from pathlib import Path

from pydantic import ValidationError

from src.execution_runtime.engine_contract import WorkflowEngineRequest
from src.execution_runtime.engine_layout import (
    cleanup_engine_alias,
    create_engine_alias,
    prepare_engine_layout,
)
from src.execution_runtime.storage import get_tools_root


ENGINE_REQUEST = Path(".tdease") / "engine-request.json"


def main() -> int:
    from snakemake.api import SnakemakeApi
    import snakemake.shell as engine_shell
    import snakemake.workflow as engine_workflow
    from snakemake.persistence.file import FilePersistence as UpstreamFilePersistence
    from snakemake.settings.types import (
        ConfigSettings,
        DAGSettings,
        ExecutionSettings,
        OutputSettings,
        ResourceSettings,
    )

    root = Path.cwd().resolve()
    request_path = root / ENGINE_REQUEST
    try:
        request = WorkflowEngineRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as exc:
        print(f"Invalid TDEase engine request: {exc}", file=sys.stderr)
        return 2

    snakefile = (root / request.snakefile).resolve(strict=False)
    try:
        snakefile.relative_to(root)
    except ValueError:
        print("Engine Snakefile escapes the Run root", file=sys.stderr)
        return 2
    if not snakefile.is_file():
        print(f"Engine Snakefile not found: {snakefile}", file=sys.stderr)
        return 2

    # Rules are copied into the isolated Run, but executables and other runtime
    # assets remain Backend-managed Node packages. Every engine process receives
    # the same resolved Backend root in Desktop and Server deployments.
    tools_root = get_tools_root().resolve()
    os.environ["TDEASE_TOOLS_ROOT"] = str(tools_root)

    # One hidden dir to rule them all: .tdease/engine/ holds everything
    # upstream would have put under .snakemake/.
    engine_root = prepare_engine_layout(root)

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
        try:
            create_engine_alias(engine_root, snakemake_dir)
        except OSError:
            # Upstream may create a temporary real directory; it is removed below.
            pass

    # TDEase writes long shell commands itself through the managed process
    # boundary; prevent the upstream helper from creating a branded breadcrumb.
    engine_shell.MAX_ARG_LEN = 2**31 - 1

    output_settings = OutputSettings(
        dryrun=request.mode == "dry-run",
        printshellcmds=True,
        nocolor=True,
        skip_plugin_handlers=True,
        enable_file_logging=False,
    )
    try:
        with SnakemakeApi(output_settings) as api:
            workflow = api.workflow(
                resource_settings=ResourceSettings(cores=request.cores),
                config_settings=ConfigSettings(config=request.config),
                snakefile=snakefile,
                workdir=root,
            )
            dag = workflow.dag(
                DAGSettings(
                    targets=frozenset(request.targets),
                    forceall=request.rerun_mode == "overwrite",
                    force_incomplete=request.rerun_incomplete,
                )
            )
            dag.execute_workflow(
                executor="dryrun" if request.mode == "dry-run" else "local",
                execution_settings=ExecutionSettings(retries=request.retries),
            )
    except Exception as exc:
        print(f"TDEase workflow engine failed: {exc}", file=sys.stderr)
        return 1
    finally:
        cleanup_engine_alias(root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
