import re
import subprocess
from pathlib import Path
from typing import Optional

import yt_dlp
from yt_dlp.utils import DownloadError

from vidistill.exceptions import VideoFetchError
from vidistill.models import VideoMetadata

_ANSI_ESCAPE = re.compile(r"\x1b\[\d+(?:;\d+)*m")


def _clean(msg: str) -> str:
    """Strip ANSI color escapes from yt-dlp error messages."""
    return _ANSI_ESCAPE.sub("", msg).strip()


# Map yt-dlp / urllib3 error keywords to short, user-friendly Chinese messages.
# Order matters: video-specific patterns first, then network, then HTTP, then generic.
_FRIENDLY_PATTERNS: list[tuple[str, str]] = [
    # 视频本身的问题
    ("private video", "这是私密视频，无法访问"),
    ("members-only", "这是会员专属视频，无法访问"),
    ("video unavailable", "视频不存在、已被删除或在当前地区不可用"),
    ("sign in to confirm your age", "视频需要登录确认年龄，无法处理"),
    # 网络问题
    ("network is unreachable", "服务器网络不可达，请检查出口网络或代理配置"),
    ("name or service not known", "域名解析失败，请检查 DNS 或代理配置"),
    ("failed to resolve", "域名解析失败，请检查 DNS 或代理配置"),
    ("nodename nor servname", "域名解析失败，请检查 DNS 或代理配置"),
    ("connection refused", "连接被拒绝，视频站点不可达"),
    ("timed out", "网络连接超时，服务器可能无法访问该视频站点（请配置代理或稍后重试）"),
    ("read timeout", "网络读取超时，请稍后重试"),
    # HTTP 错误
    ("http error 403", "视频站点拒绝访问（403），可能需要更新 cookies 或代理"),
    ("http error 404", "视频不存在或已被删除"),
]


def _friendly_message(action: str, raw_error: str) -> str:
    """Translate a raw yt-dlp / network error into a short Chinese message.

    `action` is the high-level operation that failed (e.g. "无法访问该视频"),
    used as the prefix. Falls back to a truncated raw message when no pattern
    matches, so we still have something to read.
    """
    text = _clean(raw_error)
    lower = text.lower()
    for keyword, friendly in _FRIENDLY_PATTERNS:
        if keyword in lower:
            return f"{action}：{friendly}"
    snippet = text[:200]
    return f"{action}：{snippet}"


def fetch_metadata(url: str) -> VideoMetadata:
    """Extract video metadata without downloading."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise VideoFetchError(_friendly_message("无法访问该视频", str(e))) from e

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
        raise VideoFetchError(_friendly_message("字幕抓取失败", str(e))) from e

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
    """Download audio-only stream, extract as MP3, then resample to 16kHz mono.

    Two-step process:
    1. yt-dlp downloads + extracts mp3 (any sample rate, often stereo)
    2. We call ffmpeg explicitly to produce 16kHz mono mp3 required by
       paraformer-realtime-v2. yt-dlp's postprocessor_args is unreliable
       across versions, so we do this ourselves.
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "audio_raw.%(ext)s"),
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
        raise VideoFetchError(_friendly_message("音频下载失败", str(e))) from e

    raw_path: Optional[Path] = None
    downloads = info.get("requested_downloads") or []
    for d in downloads:
        fp = d.get("filepath")
        if fp and Path(fp).exists():
            raw_path = Path(fp)
            break
    if raw_path is None:
        for candidate in work_dir.glob("audio_raw.*"):
            raw_path = candidate
            break
    if raw_path is None:
        raise VideoFetchError("音频文件下载后未找到")

    resampled = work_dir / "audio.mp3"
    _resample_to_16k_mono(raw_path, resampled)

    try:
        if raw_path != resampled:
            raw_path.unlink()
    except OSError:
        pass

    return resampled


def _resample_to_16k_mono(input_path: Path, output_path: Path) -> None:
    """Run ffmpeg to produce a 16kHz mono mp3. Isolated so tests can patch it."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-i", str(input_path),
                "-ac", "1", "-ar", "16000",
                "-acodec", "libmp3lame", "-b:a", "64k",
                str(output_path),
            ],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        raise VideoFetchError(f"音频重采样失败：{stderr}") from e
    except FileNotFoundError as e:
        raise VideoFetchError("ffmpeg 未安装或不在 PATH 中") from e
