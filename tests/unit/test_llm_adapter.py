import json
from unittest.mock import MagicMock, patch

import pytest

from vidistill.adapters.llm import summarize
from vidistill.config import Config
from vidistill.exceptions import LLMError
from vidistill.models import Summary, TranscriptSegment


SEGMENTS = [
    TranscriptSegment(start=0.0, end=5.0, text="欢迎"),
    TranscriptSegment(start=5.0, end=10.0, text="今天讲面试"),
]


@pytest.fixture
def config():
    return Config(dashscope_api_key="test-key")


def _mock_chat_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_summarize_short_style(fixtures_dir, config):
    raw = (fixtures_dir / "qwen_response_short.json").read_text(encoding="utf-8")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_chat_response(raw)

    with patch("vidistill.adapters.llm.OpenAI", return_value=fake_client):
        summary = summarize(
            segments=SEGMENTS,
            style="short",
            video_title="面试技巧",
            video_url="https://x",
            config=config,
        )

    assert isinstance(summary, Summary)
    assert summary.style == "short"
    assert summary.video_title == "面试技巧"
    assert "面试技巧" in summary.short_summary
    assert len(summary.bullets) == 3
    assert summary.chapters is None


def test_summarize_chapters_style(fixtures_dir, config):
    raw = (fixtures_dir / "qwen_response_chapters.json").read_text(encoding="utf-8")
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_chat_response(raw)

    with patch("vidistill.adapters.llm.OpenAI", return_value=fake_client):
        summary = summarize(
            segments=SEGMENTS,
            style="chapters",
            video_title="面试技巧",
            video_url="https://x",
            config=config,
        )

    assert summary.style == "chapters"
    assert summary.short_summary is None
    assert summary.bullets is None
    assert len(summary.chapters) == 2
    assert summary.chapters[1].title == "简历准备"
    assert summary.chapters[1].timestamp == 120.0


def test_summarize_raises_on_invalid_json(config):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_chat_response("not json at all")

    with patch("vidistill.adapters.llm.OpenAI", return_value=fake_client):
        with pytest.raises(LLMError, match="JSON 解析失败"):
            summarize(SEGMENTS, "short", "X", "https://x", config)


def test_summarize_raises_on_api_error(config):
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("API down")

    with patch("vidistill.adapters.llm.OpenAI", return_value=fake_client):
        with pytest.raises(LLMError, match="AI 总结失败"):
            summarize(SEGMENTS, "short", "X", "https://x", config)
