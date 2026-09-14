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
import json
import logging
from pathlib import Path

from pydantic import ValidationError

from src.execution_runtime.engine_contract import WorkflowEngineRequest
from src.execution_runtime.engine_layout import (
    cleanup_engine_alias,
    create_engine_alias,
    prepare_engine_layout,
)


ENGINE_REQUEST = Path(".tdease") / "engine-request.json"

# Internal or derived entries that never belong in a product-facing resource
# projection: tmpdir/_cores/_nodes are engine-injected, mem/disk and *_mib are
# human-readable duplicates snakemake expands from mem_mb/disk_mb.
_NON_DECLARED_RESOURCES = frozenset({"tmpdir", "_cores", "_nodes", "mem", "disk"})


def _declared_resources(job) -> dict:
    resources = {}
    for name, value in job.resources.items():
        value = getattr(value, "value", value)
        if name in _NON_DECLARED_RESOURCES or name.endswith("_mib"):
            continue
        if isinstance(value, (int, float, str)):
            resources[name] = value
    return resources


def _run_resource_limits(request: WorkflowEngineRequest) -> dict[str, int]:
    return {"mem_mb": request.memory_mb, "toppic_slots": 1}


def _resource_violations(jobs, limits: dict[str, int]) -> list[str]:
    """Assert the declared resource envelope fits the Run budget.

    The engine natively scales every declared integer resource down to the Run
    limits at DAG build time -- threads AND mem_mb. For threads that is the
    contract (appetite, degraded but correct); for memory it would silently
    under-provision the scheduler while the tool OOMs mid-run. This guard
    compares the RAW declaration (rule.resources, pre-clamp) against the
    Backend-capped limits and rejects before any job starts. Lambda-declared
    resources cannot be statically judged and stay under the engine's runtime
    clamp.
    """
    violations = []
    for job in jobs:
        for name, ceiling in limits.items():
            declared = job.rule.resources.get(name)
            needed = getattr(declared, "value", declared)
            if isinstance(needed, int) and needed > ceiling:
                violations.append(
                    f"rule '{job.rule.name}' needs {name}={needed} "
                    f"but this Run's budget is {name}={ceiling}"
                )
    return violations


def _projection_from_dag(dag) -> dict:
    engine_dag = dag.workflow_api._workflow.dag
    jobs = list(engine_dag.jobs)
    return {
        "nodes": [
            {
                "id": engine_dag.jobid(job),
                "rule": job.rule.name,
                "label": job.rule.name,
                "initial_status": "waiting"
                if engine_dag.needrun(job)
                else "up_to_date",
                # The engine already clamped rule threads to the Run core budget
                # (min(rule threads, cores)) when the DAG was built; projecting the
                # resolved values keeps that degradation observable, not silent.
                "threads": job.threads,
                "resources": _declared_resources(job),
            }
            for job in jobs
        ],
        "edges": [
            # Every DAG dependency keeps its edge, including the ones from
            # already-completed jobs (needrun=False). Filtering those severed
            # completed nodes from the graph on every resume: the node list
            # keeps them, so dropping their edges left them isolated.
            {"source": engine_dag.jobid(dependency), "target": engine_dag.jobid(job)}
            for job in jobs
            for dependency in engine_dag._dependencies[job]
        ],
    }


class _JobEventHandler(logging.Handler):
    def __init__(self, path: Path):
        super().__init__()
        self.path = path
        self.jobs: dict[int, tuple[str, dict]] = {}
        self.terminal: set[tuple[str, int]] = set()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        from snakemake_interface_logger_plugins.common import LogEvent

        event = getattr(record, "event", None)
        mapping = {
            LogEvent.JOB_INFO: "job.started",
            LogEvent.JOB_FINISHED: "job.succeeded",
            LogEvent.JOB_ERROR: "job.failed",
        }
        event_type = mapping.get(event) if event is not None else None
        job_id = getattr(record, "jobid", getattr(record, "job_id", None))
        rule = getattr(record, "rule_name", None)
        if event == LogEvent.JOB_INFO and job_id is not None and rule:
            self.jobs[int(job_id)] = (
                str(rule),
                getattr(record, "wildcards", None) or {},
            )
        if job_id is not None and not rule and int(job_id) in self.jobs:
            rule = self.jobs[int(job_id)][0]
        if event_type is not None and job_id is not None and rule:
            terminal_key = (event_type, int(job_id))
            if (
                event_type in {"job.succeeded", "job.failed"}
                and terminal_key in self.terminal
            ):
                return
            if event_type in {"job.succeeded", "job.failed"}:
                self.terminal.add(terminal_key)
            saved_wildcards = self.jobs.get(int(job_id), ("", {}))[1]
            payload = {
                "type": event_type,
                "job_id": int(job_id),
                "rule": str(rule),
                "wildcards": getattr(record, "wildcards", None) or saved_wildcards,
            }
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(
                    json.dumps(payload, ensure_ascii=False, default=str) + "\n"
                )
                stream.flush()


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
                resource_settings=ResourceSettings(
                    cores=request.cores,
                    resources=_run_resource_limits(request),
                ),
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
            if request.unlock_before_execute:
                dag.unlock()
            # The DAG is always built: the resource feasibility assertion and
            # the projection both read resolved per-job values off it.
            dag.workflow_api._workflow._prepare_dag(
                forceall=dag.dag_settings.forceall,
                ignore_incomplete=True,
                lock_warn_only=True,
            )
            dag.workflow_api._workflow._build_dag()
            projection = _projection_from_dag(dag)
            violations = _resource_violations(
                dag.workflow_api._workflow.dag.jobs, _run_resource_limits(request)
            )
            if violations:
                for violation in violations:
                    print(
                        f"TDEase resource budget exceeded: {violation}", file=sys.stderr
                    )
                print(
                    "Remedy: lower the node's declared resource floor "
                    "(rules.smk resources) or raise this machine's budget.",
                    file=sys.stderr,
                )
                return 1
            if request.projection_path:
                projection_target = (root / request.projection_path).resolve(
                    strict=False
                )
                projection_target.relative_to(root)
                projection_target.parent.mkdir(parents=True, exist_ok=True)
                # Atomic replace: a bare write_text killed mid-way (disk full,
                # hard kill) leaves a partial file that the dry-run route would
                # otherwise parse as a raw 500 instead of an invalid plan.
                payload = json.dumps(projection, ensure_ascii=False)
                tmp_target = projection_target.with_suffix(
                    projection_target.suffix + ".tmp"
                )
                tmp_target.write_text(payload, encoding="utf-8")
                os.replace(tmp_target, projection_target)
            if request.mode == "execute" and request.job_event_path:
                from snakemake.logging import logger as engine_logger

                event_target = (root / request.job_event_path).resolve(strict=False)
                event_target.relative_to(root)
                event_target.parent.mkdir(parents=True, exist_ok=True)
                with event_target.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps({"type": "workflow.graph", **projection}) + "\n"
                    )
                engine_logger.addHandler(_JobEventHandler(event_target))
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
