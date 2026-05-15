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

    def create(self, job: JobState) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT INTO jobs (
                    job_id, visitor_id, url, video_title, style, status, progress,
                    error, md_path, html_path, pdf_path, created_at, started_at, finished_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.job_id, job.visitor_id, job.url, job.video_title, job.style,
                    job.status, job.progress, job.error,
                    job.output_paths.get("md"),
                    job.output_paths.get("html"),
                    job.output_paths.get("pdf"),
                    job.created_at.isoformat(),
                    job.started_at.isoformat() if job.started_at else None,
                    job.finished_at.isoformat() if job.finished_at else None,
                ),
            )

    def get(self, job_id: str) -> Optional[JobState]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return self._row_to_job(row) if row else None

    _UPDATABLE_FIELDS = {
        "status", "progress", "error", "video_title",
        "started_at", "finished_at",
    }

    def update(self, job_id: str, **kwargs) -> None:
        output_paths = kwargs.pop("output_paths", None)
        sets = []
        vals: list = []
        for k, v in kwargs.items():
            if k not in self._UPDATABLE_FIELDS:
                raise ValueError(f"Field {k!r} is not updatable")
            if isinstance(v, datetime):
                v = v.isoformat()
            sets.append(f"{k} = ?")
            vals.append(v)
        if output_paths is not None:
            for fmt in ("md", "html", "pdf"):
                sets.append(f"{fmt}_path = ?")
                vals.append(output_paths.get(fmt))
        if not sets:
            return
        vals.append(job_id)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE jobs SET {', '.join(sets)} WHERE job_id = ?", vals
            )
            if cur.rowcount == 0:
                raise KeyError(f"Unknown job_id: {job_id}")

    def delete(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobState:
        return JobState(
            job_id=row["job_id"],
            visitor_id=row["visitor_id"],
            url=row["url"],
            video_title=row["video_title"] or "",
            style=row["style"],
            status=row["status"],
            progress=row["progress"],
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            finished_at=datetime.fromisoformat(row["finished_at"]) if row["finished_at"] else None,
            output_paths={
                "md": row["md_path"],
                "html": row["html_path"],
                "pdf": row["pdf_path"],
            },
        )
