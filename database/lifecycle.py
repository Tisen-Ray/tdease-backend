"""Minimal database migration lifecycle."""

import logging
import os

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
    """Create database and tables if they don't exist."""
    import sqlite3

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id          TEXT PRIMARY KEY,
            user_id     TEXT,
            workspace   TEXT NOT NULL,
            snakefile   TEXT NOT NULL,
            config_json TEXT,
            status      TEXT DEFAULT 'QUEUED',
            mode        TEXT DEFAULT 'local',
            cores       INTEGER DEFAULT 4,
            pid         INTEGER,
            exit_code   INTEGER,
            error       TEXT,
            evidence_json TEXT,
            created_at  TEXT,
            started_at  TEXT,
            finished_at TEXT
        )
    """)
    conn.execute(WORKSPACE_ROOT_GRANTS_DDL)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_workspace_root_grants_user
        ON workspace_root_grants(user_id)
    """)
    conn.commit()
    conn.close()
    logger.info("Database migrated: %s", db_path)
