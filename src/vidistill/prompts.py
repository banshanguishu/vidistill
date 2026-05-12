from vidistill.models import Style, TranscriptSegment


SHORT_INSTRUCTIONS = """你是一个视频内容总结助手。请阅读下面的视频转写文本，输出一段简短摘要。

要求：
- 输出严格的 JSON，且仅返回 JSON 本身（不要包裹在代码块里，不要加解释）。
- JSON 结构：
  {
    "short_summary": "3-5 句话概括视频核心内容",
    "bullets": ["要点 1", "要点 2", "..."]
  }
- bullets 5-10 条。
- 用与视频内容相同的语言（中文视频用中文回答）。
- 不要输出 chapters 字段。
"""

CHAPTERS_INSTRUCTIONS = """你是一个视频内容总结助手。请阅读下面带时间戳的视频转写文本，按视频自然的话题切分章节，输出结构化笔记。

要求：
- 输出严格的 JSON，且仅返回 JSON 本身（不要包裹在代码块里，不要加解释）。
- JSON 结构：
  {
    "chapters": [
      {
        "timestamp": <秒，浮点数>,
        "title": "章节标题",
        "summary": "本章 2-4 句话总结",
        "bullets": ["要点 1", "要点 2", "..."]
      }
    ]
  }
- 章节数 3-8 个，按时间顺序。
- 每章 bullets 3-6 条。
- 用与视频内容相同的语言（中文视频用中文回答）。
- 不要输出 short_summary 或 bullets 顶层字段。
"""


def build_prompt(
    segments: list[TranscriptSegment],
    style: Style,
    video_title: str,
) -> str:
    if style == "short":
        instructions = SHORT_INSTRUCTIONS
    elif style == "chapters":
        instructions = CHAPTERS_INSTRUCTIONS
    else:
        raise ValueError(f"Unknown style: {style}")

    transcript_lines = []
    for seg in segments:
        transcript_lines.append(f"[{seg.start:.1f}s] {seg.text}")
    transcript_block = "\n".join(transcript_lines)

    return f"""{instructions}

视频标题：{video_title}

视频转写：
{transcript_block}
"""
