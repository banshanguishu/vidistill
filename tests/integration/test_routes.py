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


def test_post_jobs_rejects_too_long_video(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="Long", duration=3600, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    assert r.status_code == 422
    assert "30" in r.json()["detail"] or "时长" in r.json()["detail"]


def test_post_jobs_returns_job_id_and_queues_task(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="Short", duration=300, has_subtitle=True, url="https://x")
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.queue_worker.process_video"),
    ):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert len(body["job_id"]) > 0


def test_get_job_status(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=100, has_subtitle=True, url="https://x")
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.queue_worker.process_video"),
    ):
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
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=100, has_subtitle=True, url="https://x")
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.queue_worker.process_video"),
    ):
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
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="Short", duration=300, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert body["queue_position"] == 1  # first task ever


def test_post_jobs_returns_429_when_queue_full(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=300, has_subtitle=True, url="https://x")
    # Pre-fill the queue: 10 active jobs via direct store seeding
    from vidistill.models import JobState
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

    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
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
