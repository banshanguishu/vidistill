from vidistill.models import Chapter, Summary
from vidistill.renderers.html import render_html


def _summary():
    return Summary(
        style="chapters",
        video_title="HTML 测试",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="第一章", summary="内容一", bullets=["要点 A"]),
        ],
    )


def test_render_html_writes_file_and_returns_path(tmp_path):
    out = render_html(_summary(), tmp_path)
    assert out.exists()
    assert out.suffix == ".html"


def test_render_html_includes_doctype_and_meta(tmp_path):
    out = render_html(_summary(), tmp_path)
    content = out.read_text(encoding="utf-8")
    assert content.lstrip().lower().startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in content.lower()
    assert "<title>HTML 测试</title>" in content


def test_render_html_renders_markdown_to_html(tmp_path):
    out = render_html(_summary(), tmp_path)
    content = out.read_text(encoding="utf-8")
    assert "<h1>HTML 测试</h1>" in content
    assert "<h2>" in content and "第一章" in content
    assert "<li>要点 A</li>" in content
