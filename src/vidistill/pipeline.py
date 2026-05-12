from pathlib import Path
from typing import Callable

from vidistill.adapters import asr, llm, video
from vidistill.config import Config
from vidistill.exceptions import VidistillError
from vidistill.jobs import JobStore
from vidistill.models import Format, Style, TranscriptSegment
from vidistill.renderers import html as html_renderer
from vidistill.renderers import markdown as md_renderer


def _get_renderer(fmt: str) -> Callable:
    """Return the renderer callable for the given format.

    PDF renderer is imported lazily to avoid loading WeasyPrint (and its GTK
    native libraries) unless a PDF is actually requested.
    """
    if fmt == "md":
        return md_renderer.render_markdown
    if fmt == "html":
        return html_renderer.render_html
    if fmt == "pdf":
        from vidistill.renderers import pdf as pdf_renderer  # noqa: PLC0415
        return pdf_renderer.render_pdf
    raise ValueError(f"Unknown format: {fmt}")


def process_video(
    job_id: str,
    url: str,
    style: Style,
    fmt: Format,
    store: JobStore,
    config: Config,
) -> None:
    """Run the full pipeline and update job state at each phase."""
    job_dir = config.output_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        store.update(job_id, status="fetching", progress=10)

        subtitle = video.fetch_subtitle(url, job_dir)
        if subtitle:
            segments = [TranscriptSegment(start=0.0, end=0.0, text=subtitle)]
            store.update(job_id, progress=50)
        else:
            audio_path = video.download_audio(url, job_dir)
            store.update(job_id, status="transcribing", progress=30)
            segments = asr.transcribe(audio_path, config)
            store.update(job_id, progress=60)

        store.update(job_id, status="summarizing", progress=70)
        existing = store.get(job_id)
        title = existing.video_title if existing else url
        summary = llm.summarize(
            segments=segments,
            style=style,
            video_title=title,
            video_url=url,
            config=config,
        )
        store.update(job_id, progress=90)

        store.update(job_id, status="rendering", progress=95)
        render = _get_renderer(fmt)
        out_path = render(summary, job_dir)

        store.update(
            job_id,
            status="done",
            progress=100,
            output_path=str(out_path),
        )
    except VidistillError as e:
        store.update(job_id, status="failed", error=str(e))
    except Exception as e:  # noqa: BLE001
        store.update(job_id, status="failed", error=f"未预期错误: {e}")
    finally:
        _cleanup_intermediate(job_dir)


def _cleanup_intermediate(job_dir: Path) -> None:
    """Delete intermediate files (audio, subtitle) but keep the rendered output."""
    if not job_dir.exists():
        return
    for f in job_dir.iterdir():
        suffix = f.suffix.lower()
        if suffix in (".mp3", ".m4a", ".webm", ".vtt", ".srt"):
            try:
                f.unlink()
            except OSError:
                pass
