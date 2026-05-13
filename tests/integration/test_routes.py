from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_slot():
    """Reset the singleton store's slot between tests to avoid bleed-over."""
    from vidistill.main import get_store
    store = get_store()
    store.release_slot()
    yield
    store.release_slot()
    # Also clear any jobs to keep tests isolated
    with store._lock:
        store._jobs.clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from vidistill.main import build_app
    app = build_app(output_dir=tmp_path)
    return TestClient(app)


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
        patch("vidistill.routes.process_video") as mock_pipeline,
    ):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert len(body["job_id"]) > 0


def test_post_jobs_rejects_when_slot_busy(client):
    from vidistill.main import get_store
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=100, has_subtitle=True, url="https://x")
    # TestClient runs background tasks synchronously before returning, so
    # the slot is released by _runner's finally block before r2 is sent.
    # We re-acquire the slot manually to simulate a still-running job.
    store = get_store()
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.routes.process_video"),
    ):
        # first submit — succeeds and busies the slot
        r1 = client.post("/jobs", json={"url": "https://x", "style": "short"})
        assert r1.status_code == 200
        # Re-acquire slot (background task released it synchronously in TestClient)
        store.try_acquire_slot()
        # second submit — rejected because slot is busy
        r2 = client.post("/jobs", json={"url": "https://x", "style": "short"})
    assert r2.status_code == 409
    assert "正在处理" in r2.json()["detail"] or "busy" in r2.json()["detail"].lower()


def test_get_job_status(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=100, has_subtitle=True, url="https://x")
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.routes.process_video"),
    ):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    job_id = r.json()["job_id"]

    r2 = client.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["job_id"] == job_id
    assert body["status"] in ("pending", "fetching", "transcribing", "summarizing", "rendering", "done", "failed")
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
        patch("vidistill.routes.process_video"),
    ):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})
    job_id = r.json()["job_id"]

    r2 = client.get(f"/jobs/{job_id}/download/md")
    assert r2.status_code == 409


def test_download_returns_file_when_done(client, tmp_path):
    from vidistill.models import JobState, VideoMetadata
    from vidistill.main import get_store

    # Seed a done job manually
    fake_file = tmp_path / "result.md"
    fake_file.write_text("# Done", encoding="utf-8")

    store = get_store()
    store.create(JobState(
        job_id="done1",
        url="https://x",
        video_title="Done Video",
        style="short",
        status="done",
        progress=100,
        error=None,
        output_paths={"md": str(fake_file)},
        created_at=datetime.now(),
    ))

    r = client.get("/jobs/done1/download/md")
    assert r.status_code == 200
    assert r.content == b"# Done"
    assert "attachment" in r.headers.get("content-disposition", "").lower()


def test_download_returns_404_when_format_not_generated(client, tmp_path):
    from vidistill.models import JobState
    from vidistill.main import get_store

    fake_md = tmp_path / "x.md"
    fake_md.write_text("# x", encoding="utf-8")

    store = get_store()
    store.create(JobState(
        job_id="nopdf",
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
