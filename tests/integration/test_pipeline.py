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
    VideoMetadata,
)
from vidistill.pipeline import process_video


@pytest.fixture
def config(tmp_path):
    return Config(dashscope_api_key="test-key", output_dir=tmp_path)


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "test.db")


@pytest.fixture(autouse=True)
def mock_metadata():
    """Pipeline now fetches metadata first; mock it for all pipeline tests."""
    meta = VideoMetadata(title="Test Video", duration=300, has_subtitle=True, url="https://example/v")
    with patch("vidistill.pipeline.video.fetch_metadata", return_value=meta):
        yield


def _seed_job(store: JobStore, job_id="j1", style="chapters", title="Test Video"):
    store.create(JobState(
        job_id=job_id,
        visitor_id="",
        url="https://example/v",
        video_title=title,
        style=style,
        status="pending",
        progress=0,
        error=None,
        output_paths={},
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


def test_pipeline_subtitle_path_skips_asr(config, store, tmp_path):
    _seed_job(store)

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="字幕文本"),
        patch("vidistill.pipeline.asr.transcribe") as mock_asr,
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"
    assert job.progress == 100
    assert "md" in job.output_paths and job.output_paths["md"] is not None and Path(job.output_paths["md"]).exists()
    mock_asr.assert_not_called()


def test_pipeline_asr_fallback_path(config, store, tmp_path):
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
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"


def test_pipeline_video_fetch_error_marks_failed(config, store):
    _seed_job(store)

    with patch("vidistill.pipeline.video.fetch_subtitle", side_effect=VideoFetchError("404")):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "404" in job.error


def test_pipeline_asr_error_marks_failed(config, store, tmp_path):
    _seed_job(store)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\xff")

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value=None),
        patch("vidistill.pipeline.video.download_audio", return_value=audio),
        patch("vidistill.pipeline.asr.transcribe", side_effect=ASRError("api down")),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "api down" in job.error


def test_pipeline_llm_error_marks_failed(config, store):
    _seed_job(store)

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="text"),
        patch("vidistill.pipeline.llm.summarize", side_effect=LLMError("bad json")),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "bad json" in job.error


def test_pipeline_writes_all_three_formats(config, store, tmp_path):
    """Pipeline always attempts all three formats; md and html are mandatory,
    pdf may be None when GTK runtime is unavailable (Windows local dev)."""
    _seed_job(store)

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="text"),
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"
    # All three format keys must be present regardless of environment
    assert set(job.output_paths.keys()) == {"md", "html", "pdf"}
    # md and html must always succeed
    assert job.output_paths["md"] is not None
    assert job.output_paths["html"] is not None
    # pdf is best-effort: None on Windows without GTK, path on Docker/Linux


def test_pipeline_too_long_video_marks_failed(config, store, mock_metadata):
    """Duration check moved from POST to pipeline; too-long video → status=failed."""
    _seed_job(store)
    long_meta = VideoMetadata(title="Long", duration=3600, has_subtitle=True, url="https://example/v")

    with patch("vidistill.pipeline.video.fetch_metadata", return_value=long_meta):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "60" in job.error  # 3600s = 60 minutes
    assert "30" in job.error  # max limit


def test_pipeline_unknown_duration_enforced_after_download(config, store, tmp_path):
    """元数据 duration=0（通用提取器拿不到时长）时，用下载后 ffprobe 实测时长兜底校验
    30 分钟上限，且必须在 ASR 之前拦截（不浪费转写、立即释放 worker）。"""
    _seed_job(store)
    unknown_meta = VideoMetadata(title="Unknown", duration=0, has_subtitle=False, url="https://example/v")
    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"\xff\xfb")

    with (
        patch("vidistill.pipeline.video.fetch_metadata", return_value=unknown_meta),
        patch("vidistill.pipeline.video.fetch_subtitle", return_value=None),
        patch("vidistill.pipeline.video.download_audio", return_value=fake_audio),
        patch("vidistill.pipeline.video.probe_audio_duration", return_value=4000.0),  # > 1800s
        patch("vidistill.pipeline.asr.transcribe") as mock_asr,
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "30" in job.error          # 提到 30 分钟上限
    mock_asr.assert_not_called()      # 在 ASR 之前就拦下


def test_pipeline_unknown_duration_within_limit_proceeds(config, store, tmp_path):
    """duration=0 但实测在上限内时，正常继续走 ASR（兜底校验不误伤短视频）。"""
    _seed_job(store)
    unknown_meta = VideoMetadata(title="Unknown", duration=0, has_subtitle=False, url="https://example/v")
    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"\xff\xfb")

    with (
        patch("vidistill.pipeline.video.fetch_metadata", return_value=unknown_meta),
        patch("vidistill.pipeline.video.fetch_subtitle", return_value=None),
        patch("vidistill.pipeline.video.download_audio", return_value=fake_audio),
        patch("vidistill.pipeline.video.probe_audio_duration", return_value=120.0),  # < 1800s
        patch("vidistill.pipeline.asr.transcribe", return_value=[TranscriptSegment(0.0, 5.0, "hi")]),
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"


def test_pipeline_pdf_failure_does_not_fail_job(config, store, tmp_path):
    _seed_job(store)

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="text"),
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
        patch("vidistill.pipeline._get_renderer", side_effect=lambda fmt: (
            __import__("vidistill.renderers.markdown", fromlist=["render_markdown"]).render_markdown
            if fmt == "md"
            else __import__("vidistill.renderers.html", fromlist=["render_html"]).render_html
            if fmt == "html"
            else (_ for _ in ()).throw(OSError("GTK not found"))
        )),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"
    assert job.output_paths["pdf"] is None
    assert job.output_paths["md"] is not None
    assert job.output_paths["html"] is not None
