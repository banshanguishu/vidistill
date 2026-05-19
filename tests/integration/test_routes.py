from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_store():
    """v2: each test gets a fresh client fixture, no shared singleton."""
    yield


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from vidistill.main import build_app
    app = build_app(output_dir=tmp_path)
    with TestClient(app) as c:
        yield c


def test_get_root_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "vidistill" in r.text.lower() or "<form" in r.text.lower()


def test_post_jobs_rejects_invalid_url(client):
    r = client.post("/jobs", json={"url": "not-a-url", "style": "chapters"})
    assert r.status_code == 422


def test_post_jobs_returns_job_id_and_queues_task(client):
    with patch("vidistill.queue_worker.process_video"):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert len(body["job_id"]) > 0


def test_get_job_status(client):
    with patch("vidistill.queue_worker.process_video"):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    job_id = r.json()["job_id"]

    r2 = client.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["job_id"] == job_id
    assert body["status"] in ("queued", "pending", "fetching", "transcribing", "summarizing", "rendering", "done", "failed")
    assert "progress" in body
    assert "available_formats" in body


def test_get_unknown_job_returns_404(client):
    r = client.get("/jobs/nope")
    assert r.status_code == 404


def test_download_returns_404_for_unknown(client):
    r = client.get("/jobs/nope/download/md")
    assert r.status_code == 404


def test_download_returns_409_when_not_done(client):
    with patch("vidistill.queue_worker.process_video"):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    job_id = r.json()["job_id"]

    r2 = client.get(f"/jobs/{job_id}/download/md")
    assert r2.status_code == 409


def test_download_returns_file_when_done(client, tmp_path):
    from vidistill.models import JobState

    fake_file = tmp_path / "result.md"
    fake_file.write_text("# Done", encoding="utf-8")

    store = client.app.state.store
    store.create(JobState(
        job_id="done1",
        visitor_id="v-test",
        url="https://x",
        video_title="Done Video",
        style="short",
        status="done",
        progress=100,
        error=None,
        output_paths={"md": str(fake_file), "html": None, "pdf": None},
        created_at=datetime.now(),
    ))

    r = client.get("/jobs/done1/download/md")
    assert r.status_code == 200
    assert r.content == b"# Done"
    assert "attachment" in r.headers.get("content-disposition", "").lower()


def test_download_returns_404_when_format_not_generated(client, tmp_path):
    from vidistill.models import JobState

    fake_md = tmp_path / "x.md"
    fake_md.write_text("# x", encoding="utf-8")

    store = client.app.state.store
    store.create(JobState(
        job_id="nopdf",
        visitor_id="v-test",
        url="https://x",
        video_title="X",
        style="short",
        status="done",
        progress=100,
        error=None,
        output_paths={"md": str(fake_md), "html": None, "pdf": None},
        created_at=datetime.now(),
    ))
    r = client.get("/jobs/nopdf/download/pdf")
    assert r.status_code == 404


def test_post_jobs_returns_queue_position(client):
    with patch("vidistill.queue_worker.process_video"):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["queue_position"] == 1  # first task ever


def test_post_jobs_returns_429_when_queue_full(client):
    from vidistill.models import JobState

    # Pre-fill the queue: 10 active jobs via direct store seeding
    store = client.app.state.store
    for i in range(10):
        store.create(JobState(
            job_id=f"seed{i}",
            visitor_id="v-other",
            url="https://x",
            video_title=f"Seed {i}",
            style="short",
            status="queued",
            progress=0,
            error=None,
            created_at=datetime.now(),
        ))

    with patch("vidistill.queue_worker.process_video"):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 429
    assert "队列已满" in r.json()["detail"] or "队列" in r.json()["detail"]


def test_exception_handler_maps_vidistill_errors(client):
    from vidistill.exceptions import QueueFullError, JobNotFoundError
    from fastapi import APIRouter

    # Inject a throw-route
    router = APIRouter()

    @router.get("/_test/queue-full")
    def boom_queue():
        raise QueueFullError("队列已满（10 个）")

    @router.get("/_test/not-found")
    def boom_404():
        raise JobNotFoundError("任务不存在")

    client.app.include_router(router)

    r1 = client.get("/_test/queue-full")
    assert r1.status_code == 429
    assert "队列已满" in r1.json()["detail"]

    r2 = client.get("/_test/not-found")
    assert r2.status_code == 404


def test_get_job_returns_queue_position_for_queued(client):
    with patch("vidistill.queue_worker.process_video"):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    job_id = r.json()["job_id"]

    r2 = client.get(f"/jobs/{job_id}")
    body = r2.json()
    # status is either 'queued' (not yet picked up) or 'pending'+ (already picked)
    if body["status"] == "queued":
        assert body["queue_position"] == 1
    else:
        assert body["queue_position"] is None


def test_delete_unknown_returns_404(client):
    r = client.delete("/jobs/nope")
    assert r.status_code == 404


def test_delete_cancels_queued_job(client):
    with patch("vidistill.queue_worker.process_video"):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    job_id = r.json()["job_id"]
    # In TestClient lifespan is started, but the worker may have picked it.
    # If status is no longer 'queued', skip the success path.
    status = client.get(f"/jobs/{job_id}").json()["status"]
    if status != "queued":
        pytest.skip("worker picked task before DELETE; race-y in TestClient")

    r2 = client.delete(f"/jobs/{job_id}")
    assert r2.status_code == 200
    assert client.app.state.store.get(job_id).status == "cancelled"


def test_delete_other_visitor_returns_403(client, tmp_path):
    from vidistill.models import JobState
    client.app.state.store.create(JobState(
        job_id="not-mine",
        visitor_id="someone-else",
        url="https://x", video_title="T", style="short",
        status="queued", progress=0, error=None,
        created_at=datetime.now(),
    ))
    r = client.delete("/jobs/not-mine")
    assert r.status_code == 403


def test_delete_running_returns_409(client, tmp_path):
    from vidistill.models import JobState
    # Manually create as me, in fetching state
    # Trigger visitor_id assignment first
    client.get("/my/jobs")
    visitor_id = client.cookies.get("visitor_id")
    client.app.state.store.create(JobState(
        job_id="running",
        visitor_id=visitor_id,
        url="https://x", video_title="T", style="short",
        status="fetching", progress=20, error=None,
        created_at=datetime.now(),
    ))
    r = client.delete("/jobs/running")
    assert r.status_code == 409


def test_post_feedback_stores_row(client):
    r = client.post("/feedback", json={
        "content": "页面加载有点慢",
        "contact": "test@example.com",
    })
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # Verify in DB
    rows = client.app.state.store._conn.execute(
        "SELECT * FROM feedback"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["content"] == "页面加载有点慢"


def test_post_feedback_accepts_null_contact(client):
    r = client.post("/feedback", json={"content": "bug"})
    assert r.status_code == 200


def test_post_feedback_rejects_empty_content(client):
    r = client.post("/feedback", json={"content": ""})
    assert r.status_code == 422  # Pydantic min_length validation
