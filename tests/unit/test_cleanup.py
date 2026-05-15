import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vidistill.cleanup import cleanup_once
from vidistill.jobs import JobStore
from vidistill.models import JobState


async def test_cleanup_removes_terminal_jobs_older_than_7d(tmp_path: Path):
    store = JobStore(":memory:")

    old_done = JobState(
        job_id="old1", visitor_id="v", url="x", video_title="T", style="short",
        status="done", progress=100, error=None,
        created_at=datetime.now() - timedelta(days=8),
        output_paths={"md": str(tmp_path / "old1" / "x.md")},
    )
    new_done = JobState(
        job_id="new1", visitor_id="v", url="x", video_title="T", style="short",
        status="done", progress=100, error=None,
        created_at=datetime.now() - timedelta(days=1),
        output_paths={"md": str(tmp_path / "new1" / "x.md")},
    )
    old_running = JobState(
        job_id="zombie", visitor_id="v", url="x", video_title="T", style="short",
        status="fetching", progress=10, error=None,
        created_at=datetime.now() - timedelta(days=8),
    )
    store.create(old_done)
    store.create(new_done)
    store.create(old_running)
    (tmp_path / "old1").mkdir()
    (tmp_path / "old1" / "x.md").write_text("x")
    (tmp_path / "new1").mkdir()
    (tmp_path / "new1" / "x.md").write_text("x")

    removed = cleanup_once(store, tmp_path)
    assert removed == 1
    assert store.get("old1") is None
    assert not (tmp_path / "old1").exists()
    assert store.get("new1") is not None
    assert store.get("zombie") is not None  # non-terminal: untouched
