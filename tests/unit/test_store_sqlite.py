from datetime import datetime, timedelta

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


def test_list_by_visitor_returns_only_own_jobs():
    store = JobStore(":memory:")
    base = datetime(2026, 5, 15, 10, 0, 0)
    store.create(_job("a", "v1"))
    j2 = _job("b", "v2")
    object.__setattr__(j2, "created_at", base + timedelta(minutes=1))
    store.create(j2)
    j3 = _job("c", "v1")
    object.__setattr__(j3, "created_at", base + timedelta(minutes=2))
    store.create(j3)

    rows = store.list_by_visitor("v1", cutoff=base - timedelta(days=1))
    ids = [j.job_id for j in rows]
    assert ids == ["c", "a"]  # DESC


def test_list_by_visitor_filters_cutoff():
    store = JobStore(":memory:")
    old = _job("old", "v1")
    object.__setattr__(old, "created_at", datetime(2026, 5, 1))
    new = _job("new", "v1")
    object.__setattr__(new, "created_at", datetime(2026, 5, 15))
    store.create(old)
    store.create(new)

    rows = store.list_by_visitor("v1", cutoff=datetime(2026, 5, 10))
    assert [j.job_id for j in rows] == ["new"]


def test_list_older_than_returns_only_terminal_jobs():
    store = JobStore(":memory:")
    base = datetime(2026, 5, 1)
    for jid, status in [("a", "done"), ("b", "queued"), ("c", "failed"), ("d", "fetching")]:
        j = _job(jid, "v1", status=status)
        object.__setattr__(j, "created_at", base)
        store.create(j)

    stale = store.list_older_than(datetime(2026, 5, 15))
    ids = sorted(j.job_id for j in stale)
    assert ids == ["a", "c"]  # done + failed (terminal), excluded: queued, fetching


def test_count_active_includes_queued_and_running():
    store = JobStore(":memory:")
    for jid, status in [("a", "queued"), ("b", "fetching"), ("c", "done"), ("d", "cancelled")]:
        store.create(_job(jid, "v1", status=status))
    assert store.count_active() == 2  # a + b


def test_queue_position_includes_running_task():
    store = JobStore(":memory:")
    base = datetime(2026, 5, 15, 10, 0, 0)
    # 1 task is running
    running = _job("r", "v1", status="fetching")
    object.__setattr__(running, "created_at", base)
    store.create(running)
    # 2 queued before "me"
    for i, jid in enumerate(["q1", "q2", "me"]):
        j = _job(jid, "v1", status="queued")
        object.__setattr__(j, "created_at", base + timedelta(minutes=i+1))
        store.create(j)
    # me has 2 queued ahead + 1 running = position 4
    assert store.queue_position("me") == 4
    # q1 has 0 queued ahead + 1 running = position 2
    assert store.queue_position("q1") == 2


def test_queue_position_none_when_no_running():
    store = JobStore(":memory:")
    j = _job("only", "v1", status="queued")
    store.create(j)
    assert store.queue_position("only") == 1


def test_create_feedback_persists_row():
    store = JobStore(":memory:")
    fb_id = store.create_feedback(
        visitor_id="v-test",
        content="无法播放某 B 站视频",
        contact="user@example.com",
    )
    assert fb_id == 1
    rows = store._conn.execute("SELECT * FROM feedback").fetchall()
    assert len(rows) == 1
    assert rows[0]["content"] == "无法播放某 B 站视频"
    assert rows[0]["contact"] == "user@example.com"
    assert rows[0]["visitor_id"] == "v-test"


def test_create_feedback_with_null_contact():
    store = JobStore(":memory:")
    fb_id = store.create_feedback(visitor_id="v-test", content="bug", contact=None)
    assert fb_id == 1
    row = store._conn.execute("SELECT * FROM feedback").fetchone()
    assert row["contact"] is None


def test_mark_zombies_failed_only_affects_in_progress():
    store = JobStore(":memory:")
    for jid, status in [
        ("a", "queued"), ("b", "pending"), ("c", "fetching"),
        ("d", "transcribing"), ("e", "summarizing"), ("f", "rendering"),
        ("g", "done"), ("h", "failed"), ("i", "cancelled"),
    ]:
        store.create(_job(jid, "v1", status=status))
    n = store.mark_zombies_failed()
    assert n == 6
    assert store.get("a").status == "failed"
    assert store.get("a").error == "服务重启时中断"
    assert store.get("g").status == "done"  # unaffected
    assert store.get("h").status == "failed"  # unchanged
