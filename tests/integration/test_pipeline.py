from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from vidistill.config import Config
from vidistill.exceptions import ASRError, LLMError, VideoFetchError
from vidistill.jobs import JobStore
from vidistill.models import (
    Chapter,
    JobState,
    Summary,
    TranscriptSegment,
)
from vidistill.pipeline import process_video


@pytest.fixture
def config(tmp_path):
    return Config(dashscope_api_key="test-key", output_dir=tmp_path)


def _seed_job(store: JobStore, job_id="j1", style="chapters", fmt="md"):
    store.create(JobState(
        job_id=job_id,
        url="https://example/v",
        style=style,
        format=fmt,
        status="pending",
        progress=0,
        error=None,
        output_path=None,
        created_at=datetime.now(),
    ))


def _fake_summary(style="chapters"):
    if style == "short":
        return Summary(
            style="short",
            video_title="T",
            video_url="https://example/v",
            short_summary="x",
            bullets=["a"],
            chapters=None,
        )
    return Summary(
        style="chapters",
        video_title="T",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[Chapter(timestamp=0.0, title="c1", summary="s", bullets=["b"])],
    )


def test_pipeline_subtitle_path_skips_asr(config, tmp_path):
    store = JobStore()
    _seed_job(store)

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="字幕文本"),
        patch("vidistill.pipeline.asr.transcribe") as mock_asr,
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"
    assert job.progress == 100
    assert job.output_path is not None
    assert Path(job.output_path).exists()
    mock_asr.assert_not_called()


def test_pipeline_asr_fallback_path(config, tmp_path):
    store = JobStore()
    _seed_job(store)

    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"\xff\xfb")

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value=None),
        patch("vidistill.pipeline.video.download_audio", return_value=fake_audio),
        patch("vidistill.pipeline.asr.transcribe", return_value=[
            TranscriptSegment(0.0, 5.0, "hi")
        ]),
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"


def test_pipeline_video_fetch_error_marks_failed(config):
    store = JobStore()
    _seed_job(store)

    with patch("vidistill.pipeline.video.fetch_subtitle", side_effect=VideoFetchError("404")):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "404" in job.error


def test_pipeline_asr_error_marks_failed(config, tmp_path):
    store = JobStore()
    _seed_job(store)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\xff")

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value=None),
        patch("vidistill.pipeline.video.download_audio", return_value=audio),
        patch("vidistill.pipeline.asr.transcribe", side_effect=ASRError("api down")),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "api down" in job.error


def test_pipeline_llm_error_marks_failed(config):
    store = JobStore()
    _seed_job(store)

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="text"),
        patch("vidistill.pipeline.llm.summarize", side_effect=LLMError("bad json")),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "bad json" in job.error


def test_pipeline_writes_format_specific_file(config, tmp_path):
    store = JobStore()
    _seed_job(store, fmt="html")

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="text"),
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="html", store=store, config=config)

    job = store.get("j1")
    assert job.output_path.endswith(".html")
