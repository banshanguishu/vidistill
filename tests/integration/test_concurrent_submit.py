from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from vidistill.main import build_app
    app = build_app(output_dir=tmp_path)
    with TestClient(app) as c:
        yield c


def test_eleventh_submission_gets_429(client):
    from vidistill.models import JobState

    # Seed 10 active jobs directly so we don't depend on worker timing
    store = client.app.state.store
    for i in range(10):
        store.create(JobState(
            job_id=f"seed{i:02d}",
            visitor_id="v-other",
            url="https://x",
            video_title=f"Seed {i}",
            style="short",
            status="queued",
            progress=0,
            error=None,
            created_at=datetime.now(),
        ))

    from vidistill.models import VideoMetadata
    meta = VideoMetadata(title="X", duration=300, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short"})

    assert r.status_code == 429


def test_two_visitors_see_separate_my_jobs_lists(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=300, has_subtitle=True, url="https://x")
    client2 = TestClient(client.app)

    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r1 = client.post("/jobs", json={"url": "https://x", "style": "short"})
        with client2:
            r2 = client2.post("/jobs", json={"url": "https://x", "style": "short"})

            j1 = r1.json()["job_id"]
            j2 = r2.json()["job_id"]
            assert j1 != j2

            my1 = {j["job_id"] for j in client.get("/my/jobs").json()["jobs"]}
            my2 = {j["job_id"] for j in client2.get("/my/jobs").json()["jobs"]}
    assert j1 in my1
    assert j2 in my2
    assert j1 not in my2
    assert j2 not in my1
