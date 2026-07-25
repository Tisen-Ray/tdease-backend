"""TDEase-owned workflow engine entrypoint.

The upstream engine supplies DAG and incremental execution algorithms. TDEase
owns every persistent path and every product-facing log name.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    import snakemake.cli as engine_cli
    import snakemake.shell as engine_shell
    import snakemake.workflow as engine_workflow
    from snakemake.persistence.file import FilePersistence as UpstreamFilePersistence

    class TDEaseEnginePersistence(UpstreamFilePersistence):
        def __init__(self, *args, path=None, **kwargs):
            owned = Path.cwd() / ".tdease-runtime" / "engine"
            super().__init__(*args, path=path or owned, **kwargs)

    engine_workflow.FilePersistence = TDEaseEnginePersistence

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


if __name__ == "__main__":
    raise SystemExit(main())
