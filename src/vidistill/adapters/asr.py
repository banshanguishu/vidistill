from pathlib import Path
from typing import Any

import dashscope
from dashscope.audio.asr import Recognition

from vidistill.config import Config
from vidistill.exceptions import ASRError
from vidistill.models import TranscriptSegment


def transcribe(audio_path: Path, config: Config) -> list[TranscriptSegment]:
    """Transcribe an audio file using Aliyun Bailian Paraformer realtime API.

    Uses the realtime model (paraformer-realtime-v2) which accepts local
    file paths directly. The batch model would require a public HTTPS URL.
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
    """Invoke Paraformer realtime via DashScope SDK with a local file.

    The Recognition class streams the local file in chunks; the server
    returns aggregated sentences via result.get_sentence().
    """
    dashscope.api_key = config.dashscope_api_key

    recognition = Recognition(
        model=config.paraformer_model,
        format="mp3",
        sample_rate=16000,
        callback=None,
    )
    result = recognition.call(str(audio_path))

    status_code = getattr(result, "status_code", None)
    if status_code is not None and status_code != 200:
        msg = getattr(result, "message", "unknown")
        raise ASRError(f"Paraformer 调用失败 ({status_code}): {msg}")

    raw_sentences = result.get_sentence() if hasattr(result, "get_sentence") else []
    if not raw_sentences:
        return {"output": {"sentences": []}}

    return {
        "output": {
            "sentences": [
                {
                    "begin_time": s.get("begin_time", 0) if isinstance(s, dict) else 0,
                    "end_time": s.get("end_time", 0) if isinstance(s, dict) else 0,
                    "text": s.get("text", "") if isinstance(s, dict) else "",
                }
                for s in raw_sentences
            ]
        }
    }
