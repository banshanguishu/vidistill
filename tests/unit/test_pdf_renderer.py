import pytest


def _weasyprint_available():
    """Check if WeasyPrint GTK runtime is available."""
    try:
        import weasyprint
        weasyprint.HTML(string="<p>test</p>").write_pdf()  # probe
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _weasyprint_available(),
    reason="WeasyPrint GTK runtime not available (expected on Windows without GTK installed); PDF generation verified in Docker"
)


def test_render_pdf_writes_file_and_returns_path(tmp_path):
    from vidistill.models import Chapter, Summary
    from vidistill.renderers.pdf import render_pdf

    summary = Summary(
        style="chapters",
        video_title="PDF 测试",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="一章", summary="内容", bullets=["要点"]),
        ],
    )
    out = render_pdf(summary, tmp_path)
    assert out.exists()
    assert out.suffix == ".pdf"


def test_render_pdf_produces_valid_pdf_header(tmp_path):
    from vidistill.models import Chapter, Summary
    from vidistill.renderers.pdf import render_pdf

    summary = Summary(
        style="chapters",
        video_title="PDF 测试",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="一章", summary="内容", bullets=["要点"]),
        ],
    )
    out = render_pdf(summary, tmp_path)
    head = out.read_bytes()[:5]
    assert head.startswith(b"%PDF-")


def test_render_pdf_file_non_empty(tmp_path):
    from vidistill.models import Chapter, Summary
    from vidistill.renderers.pdf import render_pdf

    summary = Summary(
        style="chapters",
        video_title="PDF 测试",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="一章", summary="内容", bullets=["要点"]),
        ],
    )
    out = render_pdf(summary, tmp_path)
    assert out.stat().st_size > 1000  # at least a kilobyte
