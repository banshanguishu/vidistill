import re
from pathlib import Path

from vidistill.models import Summary

ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
MAX_FILENAME_LEN = 200


def sanitize_filename(name: str) -> str:
    cleaned = ILLEGAL_FILENAME_CHARS.sub("_", name).strip()
    if len(cleaned) > MAX_FILENAME_LEN:
        cleaned = cleaned[:MAX_FILENAME_LEN]
    return cleaned or "untitled"


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    mm, ss = divmod(total, 60)
    return f"{mm:02d}:{ss:02d}"


def render_markdown(summary: Summary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(summary.video_title) + ".md"
    out_path = output_dir / filename
    out_path.write_text(_to_markdown(summary), encoding="utf-8")
    return out_path


def _to_markdown(summary: Summary) -> str:
    lines: list[str] = []
    lines.append(f"# {summary.video_title}")
    lines.append("")
    lines.append(f"来源：<{summary.video_url}>")
    lines.append("")

    if summary.style == "short":
        lines.append("## 摘要")
        lines.append("")
        lines.append(summary.short_summary or "")
        lines.append("")
        lines.append("## 要点")
        lines.append("")
        for b in summary.bullets or []:
            lines.append(f"- {b}")
        lines.append("")
    else:
        for ch in summary.chapters or []:
            lines.append(f"## [{_format_timestamp(ch.timestamp)}] {ch.title}")
            lines.append("")
            lines.append(ch.summary)
            lines.append("")
            for b in ch.bullets:
                lines.append(f"- {b}")
            lines.append("")

    return "\n".join(lines)
