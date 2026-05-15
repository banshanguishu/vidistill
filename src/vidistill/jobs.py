import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from vidistill.models import JobState

_NON_TERMINAL = ("queued", "pending", "fetching", "transcribing", "summarizing", "rendering")
_TERMINAL = ("done", "failed", "cancelled")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id        TEXT PRIMARY KEY,
    visitor_id    TEXT NOT NULL,
    url           TEXT NOT NULL,
    video_title   TEXT,
    style         TEXT NOT NULL,
    status        TEXT NOT NULL,
    progress      INTEGER NOT NULL DEFAULT 0,
    error         TEXT,
    md_path       TEXT,
    html_path     TEXT,
    pdf_path      TEXT,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_visitor_created ON jobs(visitor_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_status          ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_created_at      ON jobs(created_at);
"""


class JobStore:
    """SQLite-backed job store. Thread-safe via a single connection + lock."""

    def __init__(self, db_path: str | Path) -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
