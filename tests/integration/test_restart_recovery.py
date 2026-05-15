from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vidistill.jobs import JobStore
from vidistill.models import JobState


def test_zombie_inprogress_jobs_marked_failed_at_startup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    # Step 1: build first app, seed an in-progress job, close
    db_path = tmp_path / "vidistill.db"
    store1 = JobStore(db_path)
    store1.create(JobState(
        job_id="zombie",
        visitor_id="v",
        url="https://x",
        video_title="T",
        style="short",
        status="fetching",
        progress=30,
        error=None,
        created_at=datetime.now() - timedelta(hours=1),
    ))
    store1._conn.close()

    # Step 2: rebuild app — startup must mark "fetching" as "failed"
    from vidistill.main import build_app
    app = build_app(output_dir=tmp_path)
    j = app.state.store.get("zombie")
    assert j.status == "failed"
    assert j.error == "服务重启时中断"
