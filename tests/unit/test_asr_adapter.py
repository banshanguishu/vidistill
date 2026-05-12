import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vidistill.adapters.asr import transcribe
from vidistill.config import Config
from vidistill.exceptions import ASRError
from vidistill.models import TranscriptSegment


@pytest.fixture
def config():
    return Config(dashscope_api_key="test-key")


def test_transcribe_parses_paraformer_response(fixtures_dir, config, tmp_path):
    response_data = json.loads((fixtures_dir / "paraformer_response.json").read_text(encoding="utf-8"))

    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"\xff\xfb")

    with patch("vidistill.adapters.asr._call_paraformer", return_value=response_data):
        segments = transcribe(audio, config)

    assert len(segments) == 3
    assert isinstance(segments[0], TranscriptSegment)
    assert segments[0].start == 0.0
    assert segments[0].end == 4.5
    assert segments[0].text == "欢迎来到本课程"
    assert segments[2].text == "首先准备好你的简历"


def test_transcribe_raises_when_api_fails(config, tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"\xff\xfb")

    with patch("vidistill.adapters.asr._call_paraformer", side_effect=RuntimeError("api down")):
        with pytest.raises(ASRError, match="语音转写失败"):
            transcribe(audio, config)


def test_transcribe_raises_when_audio_missing(config, tmp_path):
    missing = tmp_path / "nope.mp3"
    with pytest.raises(ASRError, match="音频文件不存在"):
        transcribe(missing, config)


def test_transcribe_raises_when_response_empty(config, tmp_path):
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"\xff\xfb")

    with patch("vidistill.adapters.asr._call_paraformer", return_value={"output": {"sentences": []}}):
        with pytest.raises(ASRError, match="转写结果为空"):
            transcribe(audio, config)
