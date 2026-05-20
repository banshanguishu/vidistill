import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vidistill.adapters.video import (
    fetch_metadata,
    fetch_subtitle,
    download_audio,
)
from vidistill.exceptions import VideoFetchError


def _load_fixture(fixtures_dir, name):
    with open(fixtures_dir / name) as f:
        return json.load(f)


def test_fetch_metadata_parses_yt_dlp_output(fixtures_dir):
    data = _load_fixture(fixtures_dir, "yt_dlp_metadata_youtube.json")

    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.return_value = data

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        meta = fetch_metadata("https://youtu.be/dQw4w9WgXcQ")

    assert meta.title == "Sample YouTube Video"
    assert meta.duration == 213
    assert meta.has_subtitle is True
    assert meta.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_fetch_metadata_detects_no_subtitle(fixtures_dir):
    data = _load_fixture(fixtures_dir, "yt_dlp_metadata_no_subs.json")
    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.return_value = data

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        meta = fetch_metadata("https://example/no-subs")

    assert meta.has_subtitle is False


def test_fetch_metadata_raises_video_fetch_error_on_yt_dlp_failure():
    from yt_dlp.utils import DownloadError

    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.side_effect = DownloadError("Video unavailable")

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        with pytest.raises(VideoFetchError, match="视频不存在"):
            fetch_metadata("https://example/broken")


def test_fetch_metadata_maps_network_timeout_to_friendly_message():
    from yt_dlp.utils import DownloadError

    raw = (
        "ERROR: [youtube] abc: Unable to download API page: "
        "Connection to www.youtube.com timed out. (connect timeout=20.0)"
    )
    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.side_effect = DownloadError(raw)

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        with pytest.raises(VideoFetchError, match="网络连接超时"):
            fetch_metadata("https://www.youtube.com/watch?v=abc")


def test_fetch_metadata_falls_back_to_truncated_raw_on_unknown_error():
    from yt_dlp.utils import DownloadError

    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.side_effect = DownloadError("weird unexpected thing")

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        with pytest.raises(VideoFetchError, match="weird unexpected thing"):
            fetch_metadata("https://example/unknown")


def test_fetch_subtitle_returns_text_when_available(tmp_path):
    """fetch_subtitle should return concatenated subtitle text or None."""
    sample_vtt = tmp_path / "sub.en.vtt"
    sample_vtt.write_text(
        "WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nHello world\n\n"
        "00:00:05.000 --> 00:00:10.000\nSecond line\n"
    )

    fake_ydl = MagicMock()
    fake_info = {
        "title": "X",
        "requested_subtitles": {"en": {"filepath": str(sample_vtt)}},
    }
    fake_ydl.__enter__.return_value.extract_info.return_value = fake_info

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        text = fetch_subtitle("https://example/has-subs", tmp_path)

    assert text is not None
    assert "Hello world" in text
    assert "Second line" in text


def test_fetch_subtitle_returns_none_when_no_subs(tmp_path):
    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.return_value = {"title": "X", "requested_subtitles": None}

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        text = fetch_subtitle("https://example/no-subs", tmp_path)

    assert text is None


def test_download_audio_returns_mp3_path(tmp_path):
    raw = tmp_path / "audio_raw.mp3"
    raw.write_bytes(b"\xff\xfb\x10\x00")  # fake mp3 header
    expected = tmp_path / "audio.mp3"

    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.return_value = {
        "title": "X",
        "requested_downloads": [{"filepath": str(raw)}],
    }

    def fake_resample(in_path, out_path):
        out_path.write_bytes(b"resampled-mp3-bytes")

    with (
        patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl),
        patch("vidistill.adapters.video._resample_to_16k_mono", side_effect=fake_resample),
    ):
        path = download_audio("https://example/x", tmp_path)

    assert path == expected
    assert path.exists()
    assert not raw.exists()  # raw file should have been cleaned up
