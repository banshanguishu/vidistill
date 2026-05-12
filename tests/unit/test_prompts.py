from vidistill.models import TranscriptSegment
from vidistill.prompts import build_prompt


SAMPLE_SEGMENTS = [
    TranscriptSegment(start=0.0, end=5.0, text="欢迎来到本课程"),
    TranscriptSegment(start=5.0, end=10.0, text="今天我们讲面试技巧"),
]


def test_short_style_prompt_contains_title_and_instructions():
    prompt = build_prompt(SAMPLE_SEGMENTS, style="short", video_title="Sample")
    assert "Sample" in prompt
    assert "JSON" in prompt
    assert "short_summary" in prompt
    assert "bullets" in prompt
    assert "chapters" not in prompt or "Do not" in prompt or "不要" in prompt


def test_chapters_style_prompt_contains_chapter_keys():
    prompt = build_prompt(SAMPLE_SEGMENTS, style="chapters", video_title="Sample")
    assert "Sample" in prompt
    assert "chapters" in prompt
    assert "timestamp" in prompt
    assert "title" in prompt


def test_prompt_embeds_segments():
    prompt = build_prompt(SAMPLE_SEGMENTS, style="chapters", video_title="X")
    assert "欢迎来到本课程" in prompt
    assert "今天我们讲面试技巧" in prompt


def test_prompt_includes_timestamps_in_chapters_mode():
    prompt = build_prompt(SAMPLE_SEGMENTS, style="chapters", video_title="X")
    # timestamps must be visible to the LLM so it can chapter-split
    assert "0.0" in prompt or "00:00" in prompt
