from datetime import datetime

import pytest

from vidistill.jobs import JobStore
from vidistill.models import JobState


def test_store_init_creates_schema():
    store = JobStore(":memory:")
    # Querying the table should not raise
    cur = store._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
    assert cur.fetchone() is not None


def _job(job_id="abc", visitor_id="v1", status="queued"):
    return JobState(
        job_id=job_id,
        visitor_id=visitor_id,
        url="https://x",
        video_title="Test",
        style="short",
        status=status,
        progress=0,
        error=None,
        created_at=datetime(2026, 5, 15, 10, 0, 0),
    )


def test_create_and_get():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    j = store.get("j1")
    assert j is not None
    assert j.job_id == "j1"
    assert j.visitor_id == "v1"
    assert j.status == "queued"


def test_get_returns_none_for_unknown():
    store = JobStore(":memory:")
    assert store.get("nope") is None


def test_update_modifies_fields():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    store.update("j1", status="fetching", progress=30)
    j = store.get("j1")
    assert j.status == "fetching"
    assert j.progress == 30


def test_update_unknown_raises():
    store = JobStore(":memory:")
    with pytest.raises(KeyError):
        store.update("nope", status="done")


def test_delete():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    store.delete("j1")
    assert store.get("j1") is None


def test_update_output_paths():
    store = JobStore(":memory:")
    store.create(_job("j1"))
    store.update("j1", output_paths={"md": "/a.md", "html": "/a.html", "pdf": None})
    j = store.get("j1")
    assert j.output_paths == {"md": "/a.md", "html": "/a.html", "pdf": None}
