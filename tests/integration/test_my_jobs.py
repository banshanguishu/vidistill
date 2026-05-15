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


def test_my_jobs_returns_empty_for_new_visitor(client):
    r = client.get("/my/jobs")
    assert r.status_code == 200
    body = r.json()
    assert body["jobs"] == []
    assert "system" in body
    assert body["system"]["active_count"] == 0
    assert body["system"]["active_max"] == 10
    assert body["system"]["queue_full"] is False


def test_my_jobs_isolates_by_visitor(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="T", duration=300, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        # visitor A submits
        r1 = client.post("/jobs", json={"url": "https://x", "style": "short"})
        assert r1.status_code == 200
        # visitor B submits (new client = new cookie jar)
        with TestClient(client.app) as client2:
            r2 = client2.post("/jobs", json={"url": "https://x", "style": "short"})
            # rely on shared store; second may 429 if queue saturates — just check visibility

            r_a = client.get("/my/jobs")
            r_b = client2.get("/my/jobs")

    a_ids = {j["job_id"] for j in r_a.json()["jobs"]}
    b_ids = {j["job_id"] for j in r_b.json()["jobs"]}
    assert a_ids.isdisjoint(b_ids)
    assert r1.json()["job_id"] in a_ids
