"""Minimal database migration lifecycle."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

WORKSPACE_ROOT_GRANTS_DDL = """
    CREATE TABLE IF NOT EXISTS workspace_root_grants (
        root_id     TEXT PRIMARY KEY,
        user_id     TEXT NOT NULL,
        path        TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        UNIQUE(user_id, path)
    )
"""


def migrate_database(db_path: str) -> None:
    """Create or migrate the rebuildable Backend index atomically.

    API and standalone Worker processes may start at the same time.  The
    explicit write transaction serializes schema inspection and replacement so
    neither process can observe the legacy ``runs`` table halfway through the
    other's migration.
    """
    import sqlite3

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=10, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("BEGIN IMMEDIATE")
        from src.services.run_index import migrate_run_index

        migrate_run_index(conn)
        conn.execute(WORKSPACE_ROOT_GRANTS_DDL)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_workspace_root_grants_user
            ON workspace_root_grants(user_id)
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    from src.services.run_event_projector import register_projection_database

    register_projection_database(Path(db_path))
    logger.info("Database migrated: %s", db_path)
