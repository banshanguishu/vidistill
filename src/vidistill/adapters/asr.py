import time
from pathlib import Path
from typing import Any

import dashscope
from dashscope.audio.asr import Transcription

from vidistill.config import Config
from vidistill.exceptions import ASRError
from vidistill.models import TranscriptSegment


def transcribe(audio_path: Path, config: Config) -> list[TranscriptSegment]:
    """Transcribe an audio file using Aliyun Bailian Paraformer.

    Paraformer's batch (Transcription) API requires the audio to be reachable
    via a public URL. For our single-server use case we use the realtime API
    via the SDK helper, which accepts a local file path.
    """
    if not audio_path.exists():
        raise ASRError(f"音频文件不存在: {audio_path}")

    try:
        response = _call_paraformer(audio_path, config)
    except ASRError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ASRError(f"语音转写失败: {e}") from e

    sentences = (response.get("output") or {}).get("sentences") or []
    if not sentences:
        raise ASRError("转写结果为空，可能音频质量过差")

    segments: list[TranscriptSegment] = []
    for s in sentences:
        begin_ms = s.get("begin_time", 0) or 0
        end_ms = s.get("end_time", 0) or 0
        text = (s.get("text") or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=begin_ms / 1000.0,
                end=end_ms / 1000.0,
                text=text,
            )
        )
    return segments


def _call_paraformer(audio_path: Path, config: Config) -> dict[str, Any]:
    """Invoke Paraformer. Isolated so tests can patch it.

    Implementation note: this uses dashscope.audio.asr.Transcription.async_call
    with the local file path. The dashscope SDK uploads the file and polls
    until the job completes. Returns the final response dict.
    """
    dashscope.api_key = config.dashscope_api_key

    task = Transcription.async_call(
        model=config.paraformer_model,
        file_urls=[f"file://{audio_path.resolve()}"],
    )
    # Poll until completion
    deadline = time.time() + 25 * 60  # 25 min safety bound
    while time.time() < deadline:
        result = Transcription.fetch(task=task)
        status = result.output.task_status if hasattr(result, "output") else None
        if status in ("SUCCEEDED", "FAILED"):
            if status == "FAILED":
                raise ASRError(f"Paraformer task failed: {result.output}")
            # SDK returns a Response object; coerce to dict
            return {"output": {"sentences": result.output.sentences or []}}
        time.sleep(5)

    raise ASRError("Paraformer 转写超时（>25 分钟）")
