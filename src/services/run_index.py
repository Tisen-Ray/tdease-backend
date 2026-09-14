"""Rebuildable SQLite acceleration for Backend Run and file queries."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from src.execution_runtime.run_projector import STATUS_BY_EVENT


RUN_INDEX_SCHEMA_VERSION = 4


class ProjectionGapError(RuntimeError):
    """The queued batch starts after an event that has not been projected."""


RUN_INDEX_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    workspace_id    TEXT NOT NULL,
    status          TEXT,
    created_at      TEXT NOT NULL,
    name            TEXT NOT NULL,
    search_text     TEXT NOT NULL,
    event_seq       INTEGER NOT NULL DEFAULT 0,
    projected_at_seq INTEGER NOT NULL DEFAULT 0,
    queued_seq      INTEGER,
    definition_revision_id TEXT,
    execution_mode TEXT,
    rerun_mode TEXT,
    progress_done   INTEGER NOT NULL DEFAULT 0,
    progress_total  INTEGER NOT NULL DEFAULT 0,
    progress_percent REAL NOT NULL DEFAULT 0,
    current_revision TEXT,
    indexed_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_owner_created
    ON runs(user_id, created_at DESC, run_id DESC);
CREATE INDEX IF NOT EXISTS idx_runs_queue
    ON runs(status, queued_seq, run_id);
CREATE INDEX IF NOT EXISTS idx_runs_workspace
    ON runs(user_id, workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS run_files (
    run_id       TEXT NOT NULL,
    revision_id  TEXT NOT NULL,
    path          TEXT NOT NULL,
    role          TEXT NOT NULL,
    size          INTEGER NOT NULL,
    mtime_ns      INTEGER,
    sha256        TEXT NOT NULL,
    indexed_at    TEXT NOT NULL,
    PRIMARY KEY (run_id, revision_id, path),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_run_files_lookup
    ON run_files(run_id, revision_id, role, path);

CREATE TABLE IF NOT EXISTS run_graph (
    run_id       TEXT PRIMARY KEY,
    graph_json   TEXT NOT NULL,
    snapshot_seq INTEGER NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS run_jobs (
    run_id       TEXT NOT NULL,
    job_id       INTEGER NOT NULL,
    rule          TEXT NOT NULL,
    status        TEXT NOT NULL,
    wildcards_json TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    event_seq     INTEGER NOT NULL,
    PRIMARY KEY (run_id, job_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_run_jobs_status ON run_jobs(run_id, status);

CREATE TABLE IF NOT EXISTS run_tasks (
    run_id       TEXT NOT NULL,
    task_id      TEXT NOT NULL,
    step          TEXT NOT NULL,
    status        TEXT NOT NULL,
    done          INTEGER NOT NULL DEFAULT 0,
    total         INTEGER NOT NULL DEFAULT 0,
    percent       REAL NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL,
    event_seq     INTEGER NOT NULL,
    PRIMARY KEY (run_id, task_id),
    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);
"""


def migrate_run_index(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS index_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    row = connection.execute(
        "SELECT value FROM index_meta WHERE key = 'run_index_schema_version'"
    ).fetchone()
    current_version = int(row[0]) if row and str(row[0]).isdigit() else None
    if current_version != RUN_INDEX_SCHEMA_VERSION:
        connection.execute("DROP TABLE IF EXISTS run_tasks")
        connection.execute("DROP TABLE IF EXISTS run_jobs")
        connection.execute("DROP TABLE IF EXISTS run_graph")
        connection.execute("DROP TABLE IF EXISTS run_files")
        connection.execute("DROP TABLE IF EXISTS runs")
    connection.executescript(RUN_INDEX_DDL)
    connection.execute(
        """
        INSERT INTO index_meta(key, value) VALUES ('run_index_schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (str(RUN_INDEX_SCHEMA_VERSION),),
    )


class RunIndex:
    def __init__(self, database: Path):
        self.database = Path(database)

    @contextmanager
    def _connect(self, timeout: float = 10.0) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=timeout)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(f"PRAGMA busy_timeout={max(1, int(timeout * 1000))}")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @property
    def dirty_path(self) -> Path:
        return self.database.with_name("run-index.dirty")

    def mark_dirty(self) -> None:
        self.dirty_path.parent.mkdir(parents=True, exist_ok=True)
        self.dirty_path.touch(exist_ok=True)

    def is_dirty(self) -> bool:
        return self.dirty_path.exists()

    def upsert_run(
        self,
        data: dict[str, Any],
        event_seq: int = 0,
        status: str | None = None,
    ) -> None:
        run_id = str(data.get("run_id", ""))
        if not run_id:
            return
        labels_value = data.get("labels")
        labels = labels_value if isinstance(labels_value, dict) else {}
        name = str(labels.get("name") or run_id)
        search_text = " ".join(
            [
                run_id,
                str(data.get("workspace_id", "")),
                *(str(value) for value in labels.values()),
            ]
        ).lower()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, user_id, workspace_id, status, created_at, name,
                    search_text, event_seq, current_revision, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    workspace_id=excluded.workspace_id,
                    status=COALESCE(excluded.status, runs.status),
                    created_at=excluded.created_at,
                    name=excluded.name,
                    search_text=excluded.search_text,
                    event_seq=MAX(runs.event_seq, excluded.event_seq),
                    current_revision=COALESCE(excluded.current_revision, runs.current_revision),
                    indexed_at=excluded.indexed_at
                """,
                (
                    run_id,
                    str(data.get("user_id", "")),
                    str(data.get("workspace_id", "")),
                    status,
                    str(data.get("created_at", now)),
                    name,
                    search_text,
                    int(event_seq),
                    data.get("current_revision"),
                    now,
                ),
            )

    def run_snapshot(self, run_id: str) -> dict[str, Any] | None:
        """Return the disposable lifecycle/list projection for one Run."""
        with self._connect(timeout=0.1) as connection:
            row = connection.execute(
                """
                SELECT status, event_seq, projected_at_seq, progress_done,
                    progress_total, progress_percent, current_revision,
                    definition_revision_id, execution_mode, rerun_mode
                FROM runs WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return dict(row) if row else None

    def project_events(self, run_id: str, events: Sequence[dict[str, Any]]) -> int:
        """Idempotently project an ordered event batch with a short DB wait.

        Event JSONL has already been fsynced before this method is called. A
        lock failure is therefore recoverable and must not stall the Worker.
        """
        if not events:
            return self.projected_at_seq(run_id)
        job_status_by_type = {
            "job.started": "running",
            "job.succeeded": "succeeded",
            "job.failed": "failed",
        }
        now = datetime.now(timezone.utc).isoformat()
        with self._connect(timeout=0.05) as connection:
            row = connection.execute(
                "SELECT projected_at_seq FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise ProjectionGapError(f"run index row not ready for {run_id}")
            checkpoint = int(row[0])
            pending = sorted(
                (event for event in events if int(event.get("seq", 0)) > checkpoint),
                key=lambda event: int(event.get("seq", 0)),
            )
            if pending and int(pending[0].get("seq", 0)) != checkpoint + 1:
                raise ProjectionGapError(
                    f"projection gap for {run_id}: checkpoint={checkpoint}, "
                    f"next={pending[0].get('seq')}"
                )
            for event in pending:
                seq = int(event.get("seq", 0))
                if seq != checkpoint + 1:
                    raise ProjectionGapError(
                        f"projection gap for {run_id}: checkpoint={checkpoint}, next={seq}"
                    )
                event_type = str(event.get("type", ""))
                raw_data = event.get("data")
                data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
                status = STATUS_BY_EVENT.get(event_type)
                if status:
                    connection.execute(
                        "UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id)
                    )
                if event_type == "run.submitted":
                    connection.execute(
                        "UPDATE runs SET definition_revision_id = ? WHERE run_id = ?",
                        (str(data.get("revision_id", "")), run_id),
                    )
                if event_type == "run.queue_requested":
                    connection.execute(
                        """
                        UPDATE runs SET definition_revision_id = ?, execution_mode = ?,
                            rerun_mode = ?, queued_seq = ? WHERE run_id = ?
                        """,
                        (
                            str(data.get("revision_id", "")),
                            str(data.get("mode", "")),
                            str(data.get("rerun_mode", "resume")),
                            seq,
                            run_id,
                        ),
                    )
                if event_type == "workflow.graph":
                    graph = {
                        "nodes": data.get("nodes", []),
                        "edges": data.get("edges", []),
                    }
                    connection.execute(
                        """
                        INSERT INTO run_graph(run_id, graph_json, snapshot_seq)
                        VALUES (?, ?, ?)
                        ON CONFLICT(run_id) DO UPDATE SET
                            graph_json=excluded.graph_json,
                            snapshot_seq=excluded.snapshot_seq
                        """,
                        (run_id, json.dumps(graph, ensure_ascii=False), seq),
                    )
                    connection.execute(
                        "DELETE FROM run_jobs WHERE run_id = ?", (run_id,)
                    )
                job_status = job_status_by_type.get(event_type)
                job_id = data.get("job_id")
                if job_status and isinstance(job_id, int):
                    connection.execute(
                        """
                        INSERT INTO run_jobs(
                            run_id, job_id, rule, status, wildcards_json, updated_at, event_seq
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(run_id, job_id) DO UPDATE SET
                            rule=excluded.rule,
                            status=excluded.status,
                            wildcards_json=excluded.wildcards_json,
                            updated_at=excluded.updated_at,
                            event_seq=excluded.event_seq
                        WHERE excluded.event_seq > run_jobs.event_seq
                        """,
                        (
                            run_id,
                            job_id,
                            str(data.get("rule", "")),
                            job_status,
                            json.dumps(data.get("wildcards", {}), ensure_ascii=False),
                            str(event.get("timestamp", now)),
                            seq,
                        ),
                    )
                task_id = data.get("task_id")
                if event_type.startswith("task.") and isinstance(task_id, str):
                    task_status = {
                        "task.started": "running",
                        "task.progress": "running",
                        "task.succeeded": "succeeded",
                        "task.failed": "failed",
                    }.get(event_type, "waiting")
                    connection.execute(
                        """
                        INSERT INTO run_tasks(
                            run_id, task_id, step, status, done, total, percent,
                            updated_at, event_seq
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(run_id, task_id) DO UPDATE SET
                            step=CASE WHEN excluded.step != '' THEN excluded.step ELSE run_tasks.step END,
                            status=excluded.status,
                            done=CASE WHEN excluded.total > 0 THEN excluded.done ELSE run_tasks.done END,
                            total=CASE WHEN excluded.total > 0 THEN excluded.total ELSE run_tasks.total END,
                            percent=CASE WHEN excluded.total > 0 THEN excluded.percent ELSE run_tasks.percent END,
                            updated_at=excluded.updated_at,
                            event_seq=excluded.event_seq
                        WHERE excluded.event_seq > run_tasks.event_seq
                        """,
                        (
                            run_id,
                            task_id,
                            str(data.get("step", "")),
                            task_status,
                            int(data.get("done", 0)),
                            int(data.get("total", 0)),
                            float(data.get("percent", 0)),
                            str(event.get("timestamp", now)),
                            seq,
                        ),
                    )
                checkpoint = seq
            graph_row = connection.execute(
                "SELECT graph_json FROM run_graph WHERE run_id = ?", (run_id,)
            ).fetchone()
            total = 0
            if graph_row:
                try:
                    total = len(json.loads(str(graph_row[0])).get("nodes", []))
                except (json.JSONDecodeError, TypeError):
                    total = 0
            done = int(
                connection.execute(
                    """
                SELECT COUNT(*) FROM run_jobs
                WHERE run_id = ? AND status IN ('succeeded', 'failed')
                """,
                    (run_id,),
                ).fetchone()[0]
            )
            percent = round(done / total * 100, 1) if total else 0.0
            connection.execute(
                """
                UPDATE runs SET event_seq = MAX(event_seq, ?), projected_at_seq = ?,
                    progress_done = ?, progress_total = ?, progress_percent = ?, indexed_at = ?
                WHERE run_id = ?
                """,
                (checkpoint, checkpoint, done, total, percent, now, run_id),
            )
        return checkpoint

    def projected_at_seq(self, run_id: str) -> int:
        with self._connect(timeout=0.05) as connection:
            row = connection.execute(
                "SELECT projected_at_seq FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return int(row[0]) if row else 0

    def graph_projection(self, run_id: str) -> dict[str, Any] | None:
        with self._connect(timeout=0.1) as connection:
            run = connection.execute(
                "SELECT status, event_seq, projected_at_seq FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            graph = connection.execute(
                "SELECT graph_json, snapshot_seq FROM run_graph WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            jobs = connection.execute(
                """
                SELECT job_id, status, wildcards_json FROM run_jobs
                WHERE run_id = ? ORDER BY job_id
                """,
                (run_id,),
            ).fetchall()
        if (
            run is None
            or graph is None
            or int(run["projected_at_seq"]) < int(run["event_seq"])
        ):
            return None
        payload = json.loads(str(graph["graph_json"]))
        payload.update(
            {
                "status": str(run["status"]),
                "event_seq": int(run["event_seq"]),
                "projected_at_seq": int(run["projected_at_seq"]),
                "jobs": [
                    {
                        "job_id": int(job["job_id"]),
                        "status": str(job["status"]),
                        "wildcards": json.loads(str(job["wildcards_json"])),
                    }
                    for job in jobs
                ],
            }
        )
        return payload

    def catch_up_run(self, storage, run_id: str) -> int:
        checkpoint = self.projected_at_seq(run_id)
        events = [
            event
            for event in storage.read_events(run_id)
            if int(event.get("seq", 0)) > checkpoint
        ]
        return self.project_events(run_id, events)

    def remove_run(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    def list_run_ids(
        self,
        user_id: str,
        offset: int,
        limit: int,
        workspace_id: str | None = None,
        statuses: Sequence[str] | None = None,
        query: str | None = None,
    ) -> tuple[list[str], int]:
        clauses = ["user_id = ?"]
        parameters: list[Any] = [user_id]
        if workspace_id:
            clauses.append("workspace_id = ?")
            parameters.append(workspace_id)
        if statuses:
            clauses.append(f"status IN ({','.join('?' for _ in statuses)})")
            parameters.extend(statuses)
        if query:
            clauses.append("search_text LIKE ?")
            parameters.append(f"%{query.lower()}%")
        where = " AND ".join(clauses)
        with self._connect() as connection:
            total = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM runs WHERE {where}", parameters
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT run_id FROM runs WHERE {where}
                ORDER BY created_at DESC, run_id DESC
                LIMIT ? OFFSET ?
                """,
                [*parameters, limit, offset],
            ).fetchall()
        return [str(row["run_id"]) for row in rows], total

    def queued_run_ids(self, limit: int = 100) -> list[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id FROM runs WHERE status = 'QUEUED'
                ORDER BY (queued_seq IS NULL), queued_seq, created_at, run_id LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [str(row["run_id"]) for row in rows]

    def replace_manifest(self, run_id: str, manifest: dict[str, Any]) -> None:
        revision_id = str(manifest.get("revision_id", ""))
        if not revision_id:
            return
        now = datetime.now(timezone.utc).isoformat()
        entries: list[tuple[Any, ...]] = []
        for role, key in (("result", "files"), ("workflow", "workflow_files")):
            manifest_values = manifest.get(key)
            values = manifest_values if isinstance(manifest_values, list) else []
            for item in values:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    continue
                entries.append(
                    (
                        run_id,
                        revision_id,
                        item["path"],
                        role,
                        int(item.get("size", 0)),
                        item.get("mtime_ns"),
                        str(item.get("sha256", "")),
                        now,
                    )
                )
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM run_files WHERE run_id = ? AND revision_id = ?",
                (run_id, revision_id),
            )
            connection.executemany(
                """
                INSERT INTO run_files (
                    run_id, revision_id, path, role, size, mtime_ns, sha256, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                entries,
            )
            connection.execute(
                "UPDATE runs SET current_revision = ?, indexed_at = ? WHERE run_id = ?",
                (revision_id, now, run_id),
            )

    def files_for_revision(self, run_id: str, revision_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT path, role, size, sha256 FROM run_files
                WHERE run_id = ? AND revision_id = ? ORDER BY path
                """,
                (run_id, revision_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def reconcile(self, storage) -> None:
        """Refresh cheap Run projections and only missing current manifests."""
        runs_root = storage.data / "runs"
        filesystem_ids: set[str] = set()
        if runs_root.is_dir():
            for directory in sorted(runs_root.iterdir()):
                if not directory.is_dir():
                    continue
                data = storage.read_json(directory / "run.json")
                if not data:
                    continue
                run_id = str(data.get("run_id", directory.name))
                filesystem_ids.add(run_id)
                self.upsert_run(data, storage.recover_seq(run_id))
                self.catch_up_run(storage, run_id)
                current = storage.read_json(directory / "results.manifest.json")
                if isinstance(current, dict):
                    revision_id = str(current.get("revision_id", ""))
                    if revision_id and not self.files_for_revision(run_id, revision_id):
                        self.replace_manifest(run_id, current)
        with self._connect() as connection:
            indexed_ids = {
                str(row[0])
                for row in connection.execute("SELECT run_id FROM runs").fetchall()
            }
            for stale in indexed_ids - filesystem_ids:
                connection.execute("DELETE FROM runs WHERE run_id = ?", (stale,))
        self.dirty_path.unlink(missing_ok=True)

    def rebuild(self, storage) -> None:
        runs_root = storage.data / "runs"
        with self._connect() as connection:
            connection.execute("DELETE FROM run_tasks")
            connection.execute("DELETE FROM run_jobs")
            connection.execute("DELETE FROM run_graph")
            connection.execute("DELETE FROM run_files")
            connection.execute("DELETE FROM runs")
        if not runs_root.is_dir():
            self.dirty_path.unlink(missing_ok=True)
            return
        for directory in sorted(runs_root.iterdir()):
            if not directory.is_dir():
                continue
            data = storage.read_json(directory / "run.json")
            if not data:
                continue
            run_id = str(data.get("run_id", directory.name))
            self.upsert_run(data, storage.recover_seq(run_id))
            self.catch_up_run(storage, run_id)
            for manifest in storage.revision_manifests(run_id):
                self.replace_manifest(run_id, manifest)
            current = storage.read_json(directory / "results.manifest.json")
            if isinstance(current, dict):
                self.replace_manifest(run_id, current)
        self.dirty_path.unlink(missing_ok=True)


def get_run_index() -> RunIndex:
    from src.execution_runtime.storage import get_storage

    storage = get_storage()
    return RunIndex(storage.data / "database" / "db.sqlite3")
