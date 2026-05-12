from pathlib import Path

from weasyprint import HTML

from vidistill.models import Summary
from vidistill.renderers.html import HTML_TEMPLATE, _md
from vidistill.renderers.markdown import _to_markdown, sanitize_filename


def render_pdf(summary: Summary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(summary.video_title) + ".pdf"
    out_path = output_dir / filename

    body_html = _md.render(_to_markdown(summary))
    full_html = HTML_TEMPLATE.format(title=summary.video_title, body=body_html)

    HTML(string=full_html).write_pdf(target=str(out_path))
    return out_path
