from pathlib import Path
from typing import Optional

import yt_dlp
from yt_dlp.utils import DownloadError

from vidistill.exceptions import VideoFetchError
from vidistill.models import VideoMetadata


def fetch_metadata(url: str) -> VideoMetadata:
    """Extract video metadata without downloading."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise VideoFetchError(f"无法访问该视频：{e}") from e

    has_subtitle = bool(info.get("subtitles") or info.get("automatic_captions"))
    return VideoMetadata(
        title=info.get("title") or "未命名视频",
        duration=int(info.get("duration") or 0),
        has_subtitle=has_subtitle,
        url=info.get("webpage_url") or url,
    )


def fetch_subtitle(url: str, work_dir: Path) -> Optional[str]:
    """Try to fetch subtitle text. Returns concatenated lines or None if unavailable."""
    work_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["zh", "zh-CN", "en"],
        "subtitlesformat": "vtt",
        "outtmpl": str(work_dir / "%(id)s.%(ext)s"),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as e:
        raise VideoFetchError(f"字幕抓取失败：{e}") from e

    requested = info.get("requested_subtitles")
    if not requested:
        return None

    # Take the first available subtitle file
    for _lang, sub_info in requested.items():
        filepath = sub_info.get("filepath")
        if filepath and Path(filepath).exists():
            return _parse_vtt(Path(filepath))

    return None


def _parse_vtt(path: Path) -> str:
    """Naive VTT parser: drop timing lines and WEBVTT header, keep text."""
    text_lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("WEBVTT"):
                continue
            if "-->" in line:
                continue
            if line.isdigit():  # cue number
                continue
            text_lines.append(line)
    return "\n".join(text_lines)


def download_audio(url: str, work_dir: Path) -> Path:
    """Download audio-only stream and extract as MP3."""
    work_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "audio.%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as e:
        raise VideoFetchError(f"音频下载失败：{e}") from e

    downloads = info.get("requested_downloads") or []
    for d in downloads:
        fp = d.get("filepath")
        if fp and Path(fp).exists():
            return Path(fp)

    # Fallback: scan work_dir
    for candidate in work_dir.glob("audio.mp3"):
        return candidate

    raise VideoFetchError("音频文件下载后未找到")
