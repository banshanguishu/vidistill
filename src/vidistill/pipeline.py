import logging
import time
from pathlib import Path
from typing import Callable

from vidistill.adapters import asr, llm, video
from vidistill.config import Config
from vidistill.exceptions import VideoTooLongError, VidistillError
from vidistill.jobs import JobStore
from vidistill.models import Style, TranscriptSegment
from vidistill.renderers import html as html_renderer
from vidistill.renderers import markdown as md_renderer

logger = logging.getLogger(__name__)


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
    store: JobStore,
    config: Config,
) -> None:
    """Run the full pipeline and update job state at each phase."""
    job_dir = config.output_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    logger.info("[job=%s] pipeline START style=%s url=%s", job_id, style, url)

    try:
        store.update(job_id, status="fetching", progress=5)

        logger.info("[job=%s] STEP=fetch_metadata url=%s", job_id, url)
        meta = video.fetch_metadata(url, cookies_file=config.ytdlp_cookies_file)
        if meta.duration > config.max_video_duration_seconds:
            minutes = meta.duration // 60
            raise VideoTooLongError(
                f"视频时长 {minutes} 分钟，超过 30 分钟上限",
                duration=meta.duration,
            )
        store.update(job_id, video_title=meta.title, progress=10)

        logger.info("[job=%s] STEP=fetch_subtitle url=%s", job_id, url)
        subtitle = video.fetch_subtitle(url, job_dir, cookies_file=config.ytdlp_cookies_file)
        if subtitle:
            logger.info("[job=%s] subtitle FOUND chars=%d (skip ASR)", job_id, len(subtitle))
            segments = [TranscriptSegment(start=0.0, end=0.0, text=subtitle)]
            store.update(job_id, progress=50)
        else:
            logger.info("[job=%s] subtitle NOT FOUND, falling back to ASR", job_id)
            logger.info("[job=%s] STEP=download_audio url=%s", job_id, url)
            audio_path = video.download_audio(url, job_dir, cookies_file=config.ytdlp_cookies_file)
            audio_size = audio_path.stat().st_size if audio_path.exists() else 0
            logger.info("[job=%s] audio downloaded path=%s size_bytes=%d", job_id, audio_path, audio_size)

            # 元数据未给出时长（duration=0，如 yt-dlp 通用提取器/登录墙站点）时，用下载后
            # 实测时长兜底校验上限，在昂贵的 ASR 之前拦下超长视频，避免长期占住单 worker。
            if meta.duration == 0:
                probed = video.probe_audio_duration(audio_path)
                logger.info("[job=%s] meta duration=0, probed audio duration=%.0fs", job_id, probed)
                if probed > config.max_video_duration_seconds:
                    minutes = int(probed // 60)
                    raise VideoTooLongError(
                        f"视频时长 {minutes} 分钟（下载后实测），超过 30 分钟上限",
                        duration=int(probed),
                    )

            store.update(job_id, status="transcribing", progress=30)
            logger.info("[job=%s] STEP=transcribe model=%s", job_id, config.paraformer_model)
            asr_started = time.monotonic()
            segments = asr.transcribe(audio_path, config)
            logger.info(
                "[job=%s] transcribe DONE segments=%d duration=%.1fs",
                job_id, len(segments), time.monotonic() - asr_started,
            )
            store.update(job_id, progress=60)

        store.update(job_id, status="summarizing", progress=70)
        existing = store.get(job_id)
        title = existing.video_title if existing else url
        logger.info(
            "[job=%s] STEP=summarize style=%s segments=%d model=%s title=%r",
            job_id, style, len(segments), config.qwen_model, title,
        )
        llm_started = time.monotonic()
        summary = llm.summarize(
            segments=segments,
            style=style,
            video_title=title,
            video_url=url,
            config=config,
        )
        logger.info(
            "[job=%s] summarize DONE duration=%.1fs",
            job_id, time.monotonic() - llm_started,
        )
        store.update(job_id, progress=90)

        store.update(job_id, status="rendering", progress=95)
        logger.info("[job=%s] STEP=render formats=md,html,pdf", job_id)
        output_paths: dict[str, str | None] = {}

        # md and html are mandatory — failures here fail the task
        for fmt_name in ("md", "html"):
            render = _get_renderer(fmt_name)
            output_paths[fmt_name] = str(render(summary, job_dir))

        # pdf is best-effort: missing GTK runtime on Windows shouldn't fail the job
        try:
            render = _get_renderer("pdf")
            output_paths["pdf"] = str(render(summary, job_dir))
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "[job=%s] PDF rendering SKIPPED (best-effort): %s: %s",
                job_id, type(e).__name__, e,
            )
            output_paths["pdf"] = None

        rendered_formats = [fmt for fmt, p in output_paths.items() if p]
        logger.info(
            "[job=%s] render DONE formats=%s (pdf=%s)",
            job_id, rendered_formats, "ok" if output_paths.get("pdf") else "skipped",
        )

        store.update(
            job_id,
            status="done",
            progress=100,
            output_paths=output_paths,
        )
        logger.info(
            "[job=%s] pipeline DONE total_duration=%.1fs",
            job_id, time.monotonic() - started,
        )
    except VidistillError as e:
        logger.error(
            "[job=%s] pipeline FAILED type=%s message=%s",
            job_id, type(e).__name__, e, exc_info=True,
        )
        store.update(job_id, status="failed", error=str(e))
    except Exception as e:  # noqa: BLE001
        logger.exception("[job=%s] pipeline UNEXPECTED ERROR", job_id)
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
