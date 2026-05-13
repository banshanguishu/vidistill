from datetime import datetime

import pytest

from vidistill.models import (
    Chapter,
    JobState,
    Summary,
    TranscriptSegment,
    VideoMetadata,
)


def test_video_metadata_construction():
    meta = VideoMetadata(
        title="Sample Video",
        duration=1234,
        has_subtitle=True,
        url="https://youtu.be/abc",
    )
    assert meta.title == "Sample Video"
    assert meta.duration == 1234
    assert meta.has_subtitle is True


def test_transcript_segment_construction():
    seg = TranscriptSegment(start=1.5, end=4.2, text="hello world")
    assert seg.start == 1.5
    assert seg.end == 4.2
    assert seg.text == "hello world"


def test_summary_short_style():
    s = Summary(
        style="short",
        video_title="V",
        video_url="https://x",
        short_summary="three sentences here.",
        bullets=["a", "b"],
        chapters=None,
    )
    assert s.style == "short"
    assert s.chapters is None


def test_summary_chapters_style():
    s = Summary(
        style="chapters",
        video_title="V",
        video_url="https://x",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="Intro", summary="..", bullets=["x"]),
        ],
    )
    assert s.style == "chapters"
    assert len(s.chapters) == 1
    assert s.chapters[0].title == "Intro"


def test_job_state_defaults():
    now = datetime.now()
    job = JobState(
        job_id="abc",
        url="https://x",
        video_title="Sample",
        style="chapters",
        status="pending",
        progress=0,
        error=None,
        created_at=now,
    )
    assert job.status == "pending"
    assert job.progress == 0
    assert job.error is None
    assert job.video_title == "Sample"
    assert job.output_paths == {}
