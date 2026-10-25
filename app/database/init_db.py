"""Minimal database initialization."""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def check_database_health(db_path: str) -> dict:
    """Simple SQLite health check."""
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("SELECT 1")
        conn.close()
        return {"healthy": True, "path": db_path}
    except Exception as e:
        return {"healthy": False, "error": str(e)}
