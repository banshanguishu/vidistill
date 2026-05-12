import pytest

from vidistill.models import Chapter, Summary
from vidistill.renderers.markdown import render_markdown, sanitize_filename


def _short_summary():
    return Summary(
        style="short",
        video_title="测试视频",
        video_url="https://example/v",
        short_summary="这是简短摘要。",
        bullets=["要点 1", "要点 2"],
        chapters=None,
    )


def _chapters_summary():
    return Summary(
        style="chapters",
        video_title="测试视频",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="开场", summary="介绍。", bullets=["a", "b"]),
            Chapter(timestamp=65.0, title="正文", summary="详细内容。", bullets=["c"]),
        ],
    )


def test_render_short_writes_file_and_returns_path(tmp_path):
    out = render_markdown(_short_summary(), tmp_path)
    assert out.exists()
    assert out.suffix == ".md"
    content = out.read_text(encoding="utf-8")
    assert "# 测试视频" in content
    assert "这是简短摘要。" in content
    assert "- 要点 1" in content
    assert "https://example/v" in content


def test_render_chapters_includes_timestamps(tmp_path):
    out = render_markdown(_chapters_summary(), tmp_path)
    content = out.read_text(encoding="utf-8")
    assert "## [00:00] 开场" in content
    assert "## [01:05] 正文" in content
    assert "- a" in content
    assert "- c" in content


def test_sanitize_filename_removes_illegal_chars():
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_sanitize_filename_truncates_long_names():
    name = sanitize_filename("a" * 300)
    assert len(name) <= 200


def test_render_uses_sanitized_filename(tmp_path):
    summary = _short_summary()
    summary_with_bad_title = Summary(
        style=summary.style,
        video_title='bad/title:here?',
        video_url=summary.video_url,
        short_summary=summary.short_summary,
        bullets=summary.bullets,
        chapters=summary.chapters,
    )
    out = render_markdown(summary_with_bad_title, tmp_path)
    assert "/" not in out.name
    assert ":" not in out.name
