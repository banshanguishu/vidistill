import json
from typing import Any

from openai import OpenAI

from vidistill.config import Config
from vidistill.exceptions import LLMError
from vidistill.models import Chapter, Style, Summary, TranscriptSegment
from vidistill.prompts import build_prompt


def summarize(
    segments: list[TranscriptSegment],
    style: Style,
    video_title: str,
    video_url: str,
    config: Config,
) -> Summary:
    prompt = build_prompt(segments, style, video_title)

    try:
        client = OpenAI(
            api_key=config.dashscope_api_key,
            base_url=config.dashscope_compatible_base_url,
        )
        response = client.chat.completions.create(
            model=config.qwen_model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
    except Exception as e:  # noqa: BLE001
        raise LLMError(f"AI 总结失败: {e}") from e

    raw = response.choices[0].message.content or ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise LLMError(f"JSON 解析失败: {e}; raw={raw[:200]}") from e

    return _build_summary(data, style, video_title, video_url)


def _build_summary(data: dict[str, Any], style: Style, title: str, url: str) -> Summary:
    if style == "short":
        return Summary(
            style="short",
            video_title=title,
            video_url=url,
            short_summary=data.get("short_summary", ""),
            bullets=list(data.get("bullets") or []),
            chapters=None,
        )

    chapters_raw = data.get("chapters") or []
    chapters = [
        Chapter(
            timestamp=float(c.get("timestamp", 0)),
            title=c.get("title", ""),
            summary=c.get("summary", ""),
            bullets=list(c.get("bullets") or []),
        )
        for c in chapters_raw
    ]
    return Summary(
        style="chapters",
        video_title=title,
        video_url=url,
        short_summary=None,
        bullets=None,
        chapters=chapters,
    )
