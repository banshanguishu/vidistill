from pathlib import Path

from markdown_it import MarkdownIt

from vidistill.models import Summary
from vidistill.renderers.markdown import _to_markdown, sanitize_filename


_md = MarkdownIt("commonmark", {"breaks": True, "html": False})


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", "Source Han Sans SC", "Microsoft YaHei", sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; color: #222; }}
h1 {{ border-bottom: 2px solid #eee; padding-bottom: .3rem; }}
h2 {{ margin-top: 2rem; color: #1a73e8; }}
a {{ color: #1a73e8; }}
ul {{ padding-left: 1.4rem; }}
li {{ margin: .3rem 0; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render_html(summary: Summary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(summary.video_title) + ".html"
    out_path = output_dir / filename

    md_text = _to_markdown(summary)
    body_html = _md.render(md_text)
    full = HTML_TEMPLATE.format(title=summary.video_title, body=body_html)
    out_path.write_text(full, encoding="utf-8")
    return out_path
