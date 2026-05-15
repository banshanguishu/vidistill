# vidistill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-container web app that accepts a video URL, extracts content via subtitle/ASR, summarizes via LLM, and outputs Markdown/HTML/PDF for download.

**Architecture:** Single Python process (FastAPI) with `BackgroundTasks` for async pipeline. Adapters isolate external services (yt-dlp, Aliyun Bailian Paraformer, Aliyun Bailian Qwen). Renderers produce three output formats from a single `Summary` dataclass. In-memory `JobStore` with a thread lock — no database, single concurrent task. Jinja2 + Alpine.js frontend served from the same FastAPI process.

**Tech Stack:** Python 3.12, Poetry, FastAPI, Jinja2, Alpine.js, yt-dlp, openai SDK (compatible-mode for Qwen), dashscope SDK (Paraformer), markdown-it-py, WeasyPrint, ffmpeg (system), Docker.

**Reference spec:** `docs/superpowers/specs/2026-05-12-vidistill-design.md`

---

## Pre-Task Environment Checklist

Before starting, the executing engineer/agent must verify:

- [ ] Python 3.12 installed (`python --version`)
- [ ] Poetry installed (`poetry --version` ≥ 1.7)
- [ ] **ffmpeg installed locally** on Windows: `winget install ffmpeg` then verify `ffmpeg -version`
- [ ] `DASHSCOPE_API_KEY` available (user will set in `.env`)
- [ ] Working directory: `D:\DBC Projects\vidistill`

---

## Task 0: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `README.md`
- Create: `src/vidistill/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Initialize git**

```bash
git init
git branch -M main
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[tool.poetry]
name = "vidistill"
version = "0.1.0"
description = "Web tool: video URL -> AI summary -> Markdown/HTML/PDF"
authors = ["libo.gou <libo.gou@dreambigcareer.com>"]
readme = "README.md"
packages = [{include = "vidistill", from = "src"}]

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.115"
uvicorn = {extras = ["standard"], version = "^0.32"}
jinja2 = "^3.1"
python-multipart = "^0.0.9"
python-dotenv = "^1.0"
yt-dlp = "^2024.11.4"
openai = "^1.55"
dashscope = "^1.20"
"markdown-it-py" = "^3.0"
weasyprint = "^63"

[tool.poetry.group.dev.dependencies]
pytest = "^8.3"
pytest-asyncio = "^0.24"
pytest-mock = "^3.14"
httpx = "^0.27"

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
testpaths = ["tests"]

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.env
.pytest_cache/
.coverage
htmlcov/
dist/
build/
/tmp/
*.log
.idea/
.vscode/
```

- [ ] **Step 4: Create `.env.example`**

```
DASHSCOPE_API_KEY=sk-xxx-your-key-here
```

- [ ] **Step 5: Create `README.md`**

```markdown
# vidistill

Video URL -> AI summary -> Markdown / HTML / PDF.

## Local Development

1. `winget install ffmpeg` (one-time, Windows)
2. `poetry install`
3. `cp .env.example .env` and fill in `DASHSCOPE_API_KEY`
4. `poetry run uvicorn vidistill.main:app --reload --port 8000`
5. Open `http://localhost:8000`

## Testing

```bash
poetry run pytest
```
```

- [ ] **Step 6: Create empty package & test init files**

```bash
mkdir -p src/vidistill tests/unit tests/integration tests/fixtures
```

Create empty files:
- `src/vidistill/__init__.py` (empty)
- `tests/__init__.py` (empty)
- `tests/unit/__init__.py` (empty)
- `tests/integration/__init__.py` (empty)

- [ ] **Step 7: Create `tests/conftest.py`**

```python
import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def fake_env(monkeypatch, tmp_path):
    """Provide test env vars so config.load_config() never fails in tests."""
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
```

- [ ] **Step 8: Install dependencies**

Run: `poetry install`
Expected: success, `.venv` created, `poetry.lock` generated.

- [ ] **Step 9: Verify pytest discovers nothing yet**

Run: `poetry run pytest`
Expected: "no tests ran" (exit code 5) — confirms test discovery works.

- [ ] **Step 10: Commit**

```bash
git add .
git commit -m "chore: project scaffolding with poetry"
```

---

## Task 1: Configuration Module

**Files:**
- Create: `src/vidistill/config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_config.py`:

```python
import os
import pytest

from vidistill.config import load_config, Config


def test_load_config_returns_config_with_api_key(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-123")
    config = load_config()
    assert isinstance(config, Config)
    assert config.dashscope_api_key == "sk-test-123"


def test_load_config_uses_default_values(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test-123")
    config = load_config()
    assert config.qwen_model == "qwen-plus"
    assert config.paraformer_model == "paraformer-v2"
    assert config.max_video_duration_seconds == 1800
    assert config.pipeline_timeout_seconds == 1800
    assert config.min_free_disk_mb == 500
    assert config.dashscope_compatible_base_url.startswith("https://dashscope.aliyuncs.com")


def test_load_config_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DASHSCOPE_API_KEY"):
        load_config()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_config.py -v`
Expected: ImportError / ModuleNotFoundError on `vidistill.config`.

- [ ] **Step 3: Implement `src/vidistill/config.py`**

```python
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    dashscope_api_key: str
    dashscope_compatible_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    paraformer_model: str = "paraformer-v2"
    output_dir: Path = field(default_factory=lambda: Path("/tmp/vidistill"))
    max_video_duration_seconds: int = 1800
    pipeline_timeout_seconds: int = 1800
    min_free_disk_mb: int = 500


def load_config() -> Config:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY environment variable is required. "
            "Copy .env.example to .env and fill it in."
        )
    return Config(dashscope_api_key=api_key)
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/config.py tests/unit/test_config.py
git commit -m "feat(config): env-var loader with fail-fast on missing key"
```

---

## Task 2: Data Models

**Files:**
- Create: `src/vidistill/models.py`
- Create: `tests/unit/test_models.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_models.py`:

```python
from datetime import datetime

import pytest

from vidistill.models import (
    Chapter,
    JobState,
    Summary,
    TranscriptSegment,
    VideoMetadata,
)


def test_video_metadata_construction():
    meta = VideoMetadata(
        title="Sample Video",
        duration=1234,
        has_subtitle=True,
        url="https://youtu.be/abc",
    )
    assert meta.title == "Sample Video"
    assert meta.duration == 1234
    assert meta.has_subtitle is True


def test_transcript_segment_construction():
    seg = TranscriptSegment(start=1.5, end=4.2, text="hello world")
    assert seg.start == 1.5
    assert seg.end == 4.2
    assert seg.text == "hello world"


def test_summary_short_style():
    s = Summary(
        style="short",
        video_title="V",
        video_url="https://x",
        short_summary="three sentences here.",
        bullets=["a", "b"],
        chapters=None,
    )
    assert s.style == "short"
    assert s.chapters is None


def test_summary_chapters_style():
    s = Summary(
        style="chapters",
        video_title="V",
        video_url="https://x",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="Intro", summary="..", bullets=["x"]),
        ],
    )
    assert s.style == "chapters"
    assert len(s.chapters) == 1
    assert s.chapters[0].title == "Intro"


def test_job_state_defaults():
    now = datetime.now()
    job = JobState(
        job_id="abc",
        url="https://x",
        style="chapters",
        format="md",
        status="pending",
        progress=0,
        error=None,
        output_path=None,
        created_at=now,
    )
    assert job.status == "pending"
    assert job.progress == 0
    assert job.error is None
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_models.py -v`
Expected: ImportError on `vidistill.models`.

- [ ] **Step 3: Implement `src/vidistill/models.py`**

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional

Style = Literal["short", "chapters"]
Format = Literal["md", "html", "pdf"]
JobStatus = Literal[
    "pending",
    "fetching",
    "transcribing",
    "summarizing",
    "rendering",
    "done",
    "failed",
]


@dataclass(frozen=True)
class VideoMetadata:
    title: str
    duration: int
    has_subtitle: bool
    url: str


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Chapter:
    timestamp: float
    title: str
    summary: str
    bullets: list[str]


@dataclass(frozen=True)
class Summary:
    style: Style
    video_title: str
    video_url: str
    short_summary: Optional[str]
    bullets: Optional[list[str]]
    chapters: Optional[list[Chapter]]


@dataclass
class JobState:
    job_id: str
    url: str
    style: Style
    format: Format
    status: JobStatus
    progress: int
    error: Optional[str]
    output_path: Optional[str]
    created_at: datetime
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_models.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/models.py tests/unit/test_models.py
git commit -m "feat(models): data contracts for video, transcript, summary, job"
```

---

## Task 3: Custom Exceptions

**Files:**
- Create: `src/vidistill/exceptions.py`
- Create: `tests/unit/test_exceptions.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_exceptions.py`:

```python
import pytest

from vidistill.exceptions import (
    ASRError,
    LLMError,
    RenderError,
    VideoFetchError,
    VideoTooLongError,
    VidistillError,
)


def test_hierarchy():
    assert issubclass(VideoFetchError, VidistillError)
    assert issubclass(ASRError, VidistillError)
    assert issubclass(LLMError, VidistillError)
    assert issubclass(RenderError, VidistillError)
    assert issubclass(VideoTooLongError, VideoFetchError)


def test_exception_message():
    err = VideoFetchError("video deleted")
    assert str(err) == "video deleted"


def test_video_too_long_carries_duration():
    err = VideoTooLongError("3000 seconds exceeds limit", duration=3000)
    assert err.duration == 3000
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_exceptions.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/vidistill/exceptions.py`**

```python
class VidistillError(Exception):
    """Base exception for all vidistill domain errors."""


class VideoFetchError(VidistillError):
    """Failure fetching video metadata, subtitle, or audio."""


class VideoTooLongError(VideoFetchError):
    """Video duration exceeds configured maximum."""

    def __init__(self, message: str, duration: int):
        super().__init__(message)
        self.duration = duration


class ASRError(VidistillError):
    """Failure transcribing audio."""


class LLMError(VidistillError):
    """Failure summarizing transcript."""


class RenderError(VidistillError):
    """Failure rendering final output file."""
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_exceptions.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/exceptions.py tests/unit/test_exceptions.py
git commit -m "feat(exceptions): domain exception hierarchy"
```

---

## Task 4: Prompts Module

**Files:**
- Create: `src/vidistill/prompts.py`
- Create: `tests/unit/test_prompts.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_prompts.py`:

```python
from vidistill.models import TranscriptSegment
from vidistill.prompts import build_prompt


SAMPLE_SEGMENTS = [
    TranscriptSegment(start=0.0, end=5.0, text="欢迎来到本课程"),
    TranscriptSegment(start=5.0, end=10.0, text="今天我们讲面试技巧"),
]


def test_short_style_prompt_contains_title_and_instructions():
    prompt = build_prompt(SAMPLE_SEGMENTS, style="short", video_title="Sample")
    assert "Sample" in prompt
    assert "JSON" in prompt
    assert "short_summary" in prompt
    assert "bullets" in prompt
    assert "chapters" not in prompt or "Do not" in prompt or "不要" in prompt


def test_chapters_style_prompt_contains_chapter_keys():
    prompt = build_prompt(SAMPLE_SEGMENTS, style="chapters", video_title="Sample")
    assert "Sample" in prompt
    assert "chapters" in prompt
    assert "timestamp" in prompt
    assert "title" in prompt


def test_prompt_embeds_segments():
    prompt = build_prompt(SAMPLE_SEGMENTS, style="chapters", video_title="X")
    assert "欢迎来到本课程" in prompt
    assert "今天我们讲面试技巧" in prompt


def test_prompt_includes_timestamps_in_chapters_mode():
    prompt = build_prompt(SAMPLE_SEGMENTS, style="chapters", video_title="X")
    # timestamps must be visible to the LLM so it can chapter-split
    assert "0.0" in prompt or "00:00" in prompt
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_prompts.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/vidistill/prompts.py`**

```python
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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_prompts.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/prompts.py tests/unit/test_prompts.py
git commit -m "feat(prompts): A (short) and B (chapters) prompt templates"
```

---

## Task 5: Video Adapter (yt-dlp)

**Files:**
- Create: `src/vidistill/adapters/__init__.py` (empty)
- Create: `src/vidistill/adapters/video.py`
- Create: `tests/unit/test_video_adapter.py`
- Create: `tests/fixtures/yt_dlp_metadata_youtube.json`

- [ ] **Step 1: Create empty `__init__.py`**

```bash
touch src/vidistill/adapters/__init__.py
```
(On Windows PowerShell: `New-Item -ItemType File src/vidistill/adapters/__init__.py`)

- [ ] **Step 2: Create fixture `tests/fixtures/yt_dlp_metadata_youtube.json`**

```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Sample YouTube Video",
  "duration": 213,
  "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "subtitles": {},
  "automatic_captions": {
    "en": [{"url": "http://example/sub.vtt", "ext": "vtt"}]
  }
}
```

Also create `tests/fixtures/yt_dlp_metadata_no_subs.json`:

```json
{
  "id": "noSubVideo",
  "title": "No Subs Available",
  "duration": 600,
  "webpage_url": "https://example/no-subs",
  "subtitles": {},
  "automatic_captions": {}
}
```

Also create `tests/fixtures/yt_dlp_metadata_too_long.json`:

```json
{
  "id": "tooLong",
  "title": "Three Hour Documentary",
  "duration": 10800,
  "webpage_url": "https://example/long",
  "subtitles": {},
  "automatic_captions": {"en": [{"url": "x", "ext": "vtt"}]}
}
```

- [ ] **Step 3: Write failing tests**

Create `tests/unit/test_video_adapter.py`:

```python
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
    fake_ydl.__enter__.return_value.extract_info.side_effect = DownloadError("video unavailable")

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        with pytest.raises(VideoFetchError, match="video unavailable"):
            fetch_metadata("https://example/broken")


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
    expected = tmp_path / "audio.mp3"
    expected.write_bytes(b"\xff\xfb\x10\x00")  # fake mp3 header

    fake_ydl = MagicMock()
    fake_ydl.__enter__.return_value.extract_info.return_value = {
        "title": "X",
        "requested_downloads": [{"filepath": str(expected)}],
    }

    with patch("vidistill.adapters.video.yt_dlp.YoutubeDL", return_value=fake_ydl):
        path = download_audio("https://example/x", tmp_path)

    assert path == expected
    assert path.exists()
```

- [ ] **Step 4: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_video_adapter.py -v`
Expected: ImportError.

- [ ] **Step 5: Implement `src/vidistill/adapters/video.py`**

```python
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
```

- [ ] **Step 6: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_video_adapter.py -v`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add src/vidistill/adapters/__init__.py src/vidistill/adapters/video.py tests/unit/test_video_adapter.py tests/fixtures/yt_dlp_metadata_*.json
git commit -m "feat(adapters/video): yt-dlp wrapper for metadata, subtitle, audio"
```

---

## Task 6: ASR Adapter (Aliyun Paraformer)

**Files:**
- Create: `src/vidistill/adapters/asr.py`
- Create: `tests/unit/test_asr_adapter.py`
- Create: `tests/fixtures/paraformer_response.json`

- [ ] **Step 1: Create fixture `tests/fixtures/paraformer_response.json`**

```json
{
  "output": {
    "sentences": [
      {"begin_time": 0, "end_time": 4500, "text": "欢迎来到本课程"},
      {"begin_time": 4500, "end_time": 9800, "text": "今天我们讲面试技巧"},
      {"begin_time": 9800, "end_time": 15300, "text": "首先准备好你的简历"}
    ]
  }
}
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_asr_adapter.py`:

```python
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
    response_data = json.loads((fixtures_dir / "paraformer_response.json").read_text())

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
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_asr_adapter.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/vidistill/adapters/asr.py`**

```python
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
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_asr_adapter.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/vidistill/adapters/asr.py tests/unit/test_asr_adapter.py tests/fixtures/paraformer_response.json
git commit -m "feat(adapters/asr): Paraformer wrapper with response parsing"
```

> **Note:** The `_call_paraformer` function is the contract boundary tests mock. The actual dashscope SDK call inside may need adjustment after testing against the live API (Paraformer's batch API specifics evolved across SDK versions). The contract — input `audio_path + config`, output `{"output": {"sentences": [...]}}` — is stable and what the rest of the system depends on.

---

## Task 7: LLM Adapter (Qwen via OpenAI-compatible)

**Files:**
- Create: `src/vidistill/adapters/llm.py`
- Create: `tests/unit/test_llm_adapter.py`
- Create: `tests/fixtures/qwen_response_short.json`
- Create: `tests/fixtures/qwen_response_chapters.json`

- [ ] **Step 1: Create fixtures**

`tests/fixtures/qwen_response_short.json`:

```json
{
  "short_summary": "这是一个关于面试技巧的视频，讲解了简历准备、面试问答和后续跟进三个核心环节。",
  "bullets": [
    "简历要简洁、有针对性",
    "STAR 法则回答行为问题",
    "面试后 24 小时内发感谢邮件"
  ]
}
```

`tests/fixtures/qwen_response_chapters.json`:

```json
{
  "chapters": [
    {
      "timestamp": 0.0,
      "title": "开场介绍",
      "summary": "讲师介绍课程目标。",
      "bullets": ["讲师背景", "课程结构"]
    },
    {
      "timestamp": 120.0,
      "title": "简历准备",
      "summary": "如何写出有针对性的简历。",
      "bullets": ["关键词匹配", "成就量化"]
    }
  ]
}
```

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_llm_adapter.py`:

```python
import json
from unittest.mock import MagicMock, patch

import pytest

from vidistill.adapters.llm import summarize
from vidistill.config import Config
from vidistill.exceptions import LLMError
from vidistill.models import Summary, TranscriptSegment


SEGMENTS = [
    TranscriptSegment(start=0.0, end=5.0, text="欢迎"),
    TranscriptSegment(start=5.0, end=10.0, text="今天讲面试"),
]


@pytest.fixture
def config():
    return Config(dashscope_api_key="test-key")


def _mock_chat_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_summarize_short_style(fixtures_dir, config):
    raw = (fixtures_dir / "qwen_response_short.json").read_text()
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_chat_response(raw)

    with patch("vidistill.adapters.llm.OpenAI", return_value=fake_client):
        summary = summarize(
            segments=SEGMENTS,
            style="short",
            video_title="面试技巧",
            video_url="https://x",
            config=config,
        )

    assert isinstance(summary, Summary)
    assert summary.style == "short"
    assert summary.video_title == "面试技巧"
    assert "面试技巧" in summary.short_summary
    assert len(summary.bullets) == 3
    assert summary.chapters is None


def test_summarize_chapters_style(fixtures_dir, config):
    raw = (fixtures_dir / "qwen_response_chapters.json").read_text()
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_chat_response(raw)

    with patch("vidistill.adapters.llm.OpenAI", return_value=fake_client):
        summary = summarize(
            segments=SEGMENTS,
            style="chapters",
            video_title="面试技巧",
            video_url="https://x",
            config=config,
        )

    assert summary.style == "chapters"
    assert summary.short_summary is None
    assert summary.bullets is None
    assert len(summary.chapters) == 2
    assert summary.chapters[1].title == "简历准备"
    assert summary.chapters[1].timestamp == 120.0


def test_summarize_raises_on_invalid_json(config):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _mock_chat_response("not json at all")

    with patch("vidistill.adapters.llm.OpenAI", return_value=fake_client):
        with pytest.raises(LLMError, match="JSON 解析失败"):
            summarize(SEGMENTS, "short", "X", "https://x", config)


def test_summarize_raises_on_api_error(config):
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RuntimeError("API down")

    with patch("vidistill.adapters.llm.OpenAI", return_value=fake_client):
        with pytest.raises(LLMError, match="AI 总结失败"):
            summarize(SEGMENTS, "short", "X", "https://x", config)
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_llm_adapter.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/vidistill/adapters/llm.py`**

```python
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
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_llm_adapter.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add src/vidistill/adapters/llm.py tests/unit/test_llm_adapter.py tests/fixtures/qwen_response_*.json
git commit -m "feat(adapters/llm): Qwen wrapper with JSON response parsing"
```

---

## Task 8: Markdown Renderer

**Files:**
- Create: `src/vidistill/renderers/__init__.py` (empty)
- Create: `src/vidistill/renderers/markdown.py`
- Create: `tests/unit/test_markdown_renderer.py`

- [ ] **Step 1: Create empty `__init__.py`**

Create `src/vidistill/renderers/__init__.py` (empty file).

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_markdown_renderer.py`:

```python
import pytest

from vidistill.models import Chapter, Summary
from vidistill.renderers.markdown import render_markdown, sanitize_filename


def _short_summary():
    return Summary(
        style="short",
        video_title="测试视频",
        video_url="https://example/v",
        short_summary="这是简短摘要。",
        bullets=["要点 1", "要点 2"],
        chapters=None,
    )


def _chapters_summary():
    return Summary(
        style="chapters",
        video_title="测试视频",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="开场", summary="介绍。", bullets=["a", "b"]),
            Chapter(timestamp=65.0, title="正文", summary="详细内容。", bullets=["c"]),
        ],
    )


def test_render_short_writes_file_and_returns_path(tmp_path):
    out = render_markdown(_short_summary(), tmp_path)
    assert out.exists()
    assert out.suffix == ".md"
    content = out.read_text(encoding="utf-8")
    assert "# 测试视频" in content
    assert "这是简短摘要。" in content
    assert "- 要点 1" in content
    assert "https://example/v" in content


def test_render_chapters_includes_timestamps(tmp_path):
    out = render_markdown(_chapters_summary(), tmp_path)
    content = out.read_text(encoding="utf-8")
    assert "## [00:00] 开场" in content
    assert "## [01:05] 正文" in content
    assert "- a" in content
    assert "- c" in content


def test_sanitize_filename_removes_illegal_chars():
    assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"


def test_sanitize_filename_truncates_long_names():
    name = sanitize_filename("a" * 300)
    assert len(name) <= 200


def test_render_uses_sanitized_filename(tmp_path):
    summary = _short_summary()
    summary_with_bad_title = Summary(
        style=summary.style,
        video_title='bad/title:here?',
        video_url=summary.video_url,
        short_summary=summary.short_summary,
        bullets=summary.bullets,
        chapters=summary.chapters,
    )
    out = render_markdown(summary_with_bad_title, tmp_path)
    assert "/" not in out.name
    assert ":" not in out.name
```

- [ ] **Step 3: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_markdown_renderer.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/vidistill/renderers/markdown.py`**

```python
import re
from pathlib import Path

from vidistill.models import Summary

ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
MAX_FILENAME_LEN = 200


def sanitize_filename(name: str) -> str:
    cleaned = ILLEGAL_FILENAME_CHARS.sub("_", name).strip()
    if len(cleaned) > MAX_FILENAME_LEN:
        cleaned = cleaned[:MAX_FILENAME_LEN]
    return cleaned or "untitled"


def _format_timestamp(seconds: float) -> str:
    total = int(seconds)
    mm, ss = divmod(total, 60)
    return f"{mm:02d}:{ss:02d}"


def render_markdown(summary: Summary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(summary.video_title) + ".md"
    out_path = output_dir / filename
    out_path.write_text(_to_markdown(summary), encoding="utf-8")
    return out_path


def _to_markdown(summary: Summary) -> str:
    lines: list[str] = []
    lines.append(f"# {summary.video_title}")
    lines.append("")
    lines.append(f"来源：<{summary.video_url}>")
    lines.append("")

    if summary.style == "short":
        lines.append("## 摘要")
        lines.append("")
        lines.append(summary.short_summary or "")
        lines.append("")
        lines.append("## 要点")
        lines.append("")
        for b in summary.bullets or []:
            lines.append(f"- {b}")
        lines.append("")
    else:
        for ch in summary.chapters or []:
            lines.append(f"## [{_format_timestamp(ch.timestamp)}] {ch.title}")
            lines.append("")
            lines.append(ch.summary)
            lines.append("")
            for b in ch.bullets:
                lines.append(f"- {b}")
            lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 5: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_markdown_renderer.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add src/vidistill/renderers/__init__.py src/vidistill/renderers/markdown.py tests/unit/test_markdown_renderer.py
git commit -m "feat(renderers/markdown): Summary -> Markdown with filename sanitize"
```

---

## Task 9: HTML Renderer

**Files:**
- Create: `src/vidistill/renderers/html.py`
- Create: `tests/unit/test_html_renderer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_html_renderer.py`:

```python
from vidistill.models import Chapter, Summary
from vidistill.renderers.html import render_html


def _summary():
    return Summary(
        style="chapters",
        video_title="HTML 测试",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="第一章", summary="内容一", bullets=["要点 A"]),
        ],
    )


def test_render_html_writes_file_and_returns_path(tmp_path):
    out = render_html(_summary(), tmp_path)
    assert out.exists()
    assert out.suffix == ".html"


def test_render_html_includes_doctype_and_meta(tmp_path):
    out = render_html(_summary(), tmp_path)
    content = out.read_text(encoding="utf-8")
    assert content.lstrip().lower().startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in content.lower()
    assert "<title>HTML 测试</title>" in content


def test_render_html_renders_markdown_to_html(tmp_path):
    out = render_html(_summary(), tmp_path)
    content = out.read_text(encoding="utf-8")
    assert "<h1>HTML 测试</h1>" in content
    assert "<h2>" in content and "第一章" in content
    assert "<li>要点 A</li>" in content
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_html_renderer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/vidistill/renderers/html.py`**

```python
from pathlib import Path

from markdown_it import MarkdownIt

from vidistill.models import Summary
from vidistill.renderers.markdown import _to_markdown, sanitize_filename


_md = MarkdownIt("commonmark", {"breaks": True, "html": False})


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", "Source Han Sans SC", "Microsoft YaHei", sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; color: #222; }}
h1 {{ border-bottom: 2px solid #eee; padding-bottom: .3rem; }}
h2 {{ margin-top: 2rem; color: #1a73e8; }}
a {{ color: #1a73e8; }}
ul {{ padding-left: 1.4rem; }}
li {{ margin: .3rem 0; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def render_html(summary: Summary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(summary.video_title) + ".html"
    out_path = output_dir / filename

    md_text = _to_markdown(summary)
    body_html = _md.render(md_text)
    full = HTML_TEMPLATE.format(title=summary.video_title, body=body_html)
    out_path.write_text(full, encoding="utf-8")
    return out_path
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_html_renderer.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/renderers/html.py tests/unit/test_html_renderer.py
git commit -m "feat(renderers/html): Summary -> HTML via markdown-it-py"
```

---

## Task 10: PDF Renderer

**Files:**
- Create: `src/vidistill/renderers/pdf.py`
- Create: `tests/unit/test_pdf_renderer.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_pdf_renderer.py`:

```python
import pytest

from vidistill.models import Chapter, Summary
from vidistill.renderers.pdf import render_pdf


def _summary():
    return Summary(
        style="chapters",
        video_title="PDF 测试",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[
            Chapter(timestamp=0.0, title="一章", summary="内容", bullets=["要点"]),
        ],
    )


def test_render_pdf_writes_file_and_returns_path(tmp_path):
    out = render_pdf(_summary(), tmp_path)
    assert out.exists()
    assert out.suffix == ".pdf"


def test_render_pdf_produces_valid_pdf_header(tmp_path):
    out = render_pdf(_summary(), tmp_path)
    head = out.read_bytes()[:5]
    assert head.startswith(b"%PDF-")


def test_render_pdf_file_non_empty(tmp_path):
    out = render_pdf(_summary(), tmp_path)
    assert out.stat().st_size > 1000  # at least a kilobyte
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_pdf_renderer.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/vidistill/renderers/pdf.py`**

```python
from pathlib import Path

from weasyprint import HTML

from vidistill.models import Summary
from vidistill.renderers.html import HTML_TEMPLATE, _md
from vidistill.renderers.markdown import _to_markdown, sanitize_filename


def render_pdf(summary: Summary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = sanitize_filename(summary.video_title) + ".pdf"
    out_path = output_dir / filename

    body_html = _md.render(_to_markdown(summary))
    full_html = HTML_TEMPLATE.format(title=summary.video_title, body=body_html)

    HTML(string=full_html).write_pdf(target=str(out_path))
    return out_path
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_pdf_renderer.py -v`
Expected: 3 passed.

> **Windows note:** WeasyPrint on Windows requires GTK runtime. If `pip install weasyprint` fails or PDF generation crashes, install GTK from the WeasyPrint docs OR run this test under the Docker container only. CI on Linux works out of the box.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/renderers/pdf.py tests/unit/test_pdf_renderer.py
git commit -m "feat(renderers/pdf): Summary -> PDF via WeasyPrint"
```

---

## Task 11: Job Store

**Files:**
- Create: `src/vidistill/jobs.py`
- Create: `tests/unit/test_jobs.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_jobs.py`:

```python
import threading
from datetime import datetime

import pytest

from vidistill.jobs import JobStore, SingleSlotBusyError
from vidistill.models import JobState


def _job(job_id="abc"):
    return JobState(
        job_id=job_id,
        url="https://x",
        style="short",
        format="md",
        status="pending",
        progress=0,
        error=None,
        output_path=None,
        created_at=datetime.now(),
    )


def test_create_and_get():
    store = JobStore()
    store.create(_job("j1"))
    fetched = store.get("j1")
    assert fetched is not None
    assert fetched.job_id == "j1"


def test_get_returns_none_for_unknown():
    store = JobStore()
    assert store.get("nope") is None


def test_update_modifies_fields():
    store = JobStore()
    store.create(_job("j1"))
    store.update("j1", status="transcribing", progress=30)
    j = store.get("j1")
    assert j.status == "transcribing"
    assert j.progress == 30


def test_update_unknown_raises():
    store = JobStore()
    with pytest.raises(KeyError):
        store.update("nope", status="done")


def test_concurrent_updates_are_safe():
    store = JobStore()
    store.create(_job("j1"))

    def worker(p):
        for _ in range(100):
            store.update("j1", progress=p)

    threads = [threading.Thread(target=worker, args=(p,)) for p in (10, 50, 90)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = store.get("j1")
    assert final.progress in (10, 50, 90)


def test_single_slot_acquire_and_release():
    store = JobStore()
    with store.acquire_slot():
        with pytest.raises(SingleSlotBusyError):
            with store.acquire_slot():
                pass

    # after release, can acquire again
    with store.acquire_slot():
        pass
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/unit/test_jobs.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/vidistill/jobs.py`**

```python
import threading
from contextlib import contextmanager
from dataclasses import replace
from typing import Optional

from vidistill.models import JobState


class SingleSlotBusyError(RuntimeError):
    """Another task is already running."""


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._slot = threading.Lock()
        self._slot_busy = False

    def create(self, job: JobState) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Optional[JobState]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown job_id: {job_id}")
            self._jobs[job_id] = replace(self._jobs[job_id], **kwargs)

    @contextmanager
    def acquire_slot(self):
        with self._lock:
            if self._slot_busy:
                raise SingleSlotBusyError("Another task is already in progress")
            self._slot_busy = True
        try:
            yield
        finally:
            with self._lock:
                self._slot_busy = False
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `poetry run pytest tests/unit/test_jobs.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/jobs.py tests/unit/test_jobs.py
git commit -m "feat(jobs): thread-safe in-memory job store with single-slot gate"
```

---

## Task 12: Pipeline Orchestrator

**Files:**
- Create: `src/vidistill/pipeline.py`
- Create: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Write failing tests**

Create `tests/integration/test_pipeline.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from vidistill.config import Config
from vidistill.exceptions import ASRError, LLMError, VideoFetchError
from vidistill.jobs import JobStore
from vidistill.models import (
    Chapter,
    JobState,
    Summary,
    TranscriptSegment,
)
from vidistill.pipeline import process_video


@pytest.fixture
def config(tmp_path):
    return Config(dashscope_api_key="test-key", output_dir=tmp_path)


def _seed_job(store: JobStore, job_id="j1", style="chapters", fmt="md"):
    store.create(JobState(
        job_id=job_id,
        url="https://example/v",
        style=style,
        format=fmt,
        status="pending",
        progress=0,
        error=None,
        output_path=None,
        created_at=datetime.now(),
    ))


def _fake_summary(style="chapters"):
    if style == "short":
        return Summary(
            style="short",
            video_title="T",
            video_url="https://example/v",
            short_summary="x",
            bullets=["a"],
            chapters=None,
        )
    return Summary(
        style="chapters",
        video_title="T",
        video_url="https://example/v",
        short_summary=None,
        bullets=None,
        chapters=[Chapter(timestamp=0.0, title="c1", summary="s", bullets=["b"])],
    )


def test_pipeline_subtitle_path_skips_asr(config, tmp_path):
    store = JobStore()
    _seed_job(store)

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="字幕文本"),
        patch("vidistill.pipeline.asr.transcribe") as mock_asr,
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"
    assert job.progress == 100
    assert job.output_path is not None
    assert Path(job.output_path).exists()
    mock_asr.assert_not_called()


def test_pipeline_asr_fallback_path(config, tmp_path):
    store = JobStore()
    _seed_job(store)

    fake_audio = tmp_path / "audio.mp3"
    fake_audio.write_bytes(b"\xff\xfb")

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value=None),
        patch("vidistill.pipeline.video.download_audio", return_value=fake_audio),
        patch("vidistill.pipeline.asr.transcribe", return_value=[
            TranscriptSegment(0.0, 5.0, "hi")
        ]),
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "done"


def test_pipeline_video_fetch_error_marks_failed(config):
    store = JobStore()
    _seed_job(store)

    with patch("vidistill.pipeline.video.fetch_subtitle", side_effect=VideoFetchError("404")):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "404" in job.error


def test_pipeline_asr_error_marks_failed(config, tmp_path):
    store = JobStore()
    _seed_job(store)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\xff")

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value=None),
        patch("vidistill.pipeline.video.download_audio", return_value=audio),
        patch("vidistill.pipeline.asr.transcribe", side_effect=ASRError("api down")),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "api down" in job.error


def test_pipeline_llm_error_marks_failed(config):
    store = JobStore()
    _seed_job(store)

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="text"),
        patch("vidistill.pipeline.llm.summarize", side_effect=LLMError("bad json")),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="md", store=store, config=config)

    job = store.get("j1")
    assert job.status == "failed"
    assert "bad json" in job.error


def test_pipeline_writes_format_specific_file(config, tmp_path):
    store = JobStore()
    _seed_job(store, fmt="html")

    with (
        patch("vidistill.pipeline.video.fetch_subtitle", return_value="text"),
        patch("vidistill.pipeline.llm.summarize", return_value=_fake_summary()),
    ):
        process_video(job_id="j1", url="https://example/v", style="chapters",
                      fmt="html", store=store, config=config)

    job = store.get("j1")
    assert job.output_path.endswith(".html")
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/integration/test_pipeline.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/vidistill/pipeline.py`**

```python
import shutil
from pathlib import Path

from vidistill.adapters import asr, llm, video
from vidistill.config import Config
from vidistill.exceptions import VidistillError
from vidistill.jobs import JobStore
from vidistill.models import Format, Style, TranscriptSegment
from vidistill.renderers import html as html_renderer
from vidistill.renderers import markdown as md_renderer
from vidistill.renderers import pdf as pdf_renderer


_RENDERERS = {
    "md": md_renderer.render_markdown,
    "html": html_renderer.render_html,
    "pdf": pdf_renderer.render_pdf,
}


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
        summary = llm.summarize(
            segments=segments,
            style=style,
            video_title=_resolve_title(store, job_id, url),
            video_url=url,
            config=config,
        )
        store.update(job_id, progress=90)

        store.update(job_id, status="rendering", progress=95)
        render = _RENDERERS[fmt]
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


def _resolve_title(store: JobStore, job_id: str, url: str) -> str:
    """Pull title from job metadata if present, else fall back to URL."""
    job = store.get(job_id)
    if job and getattr(job, "video_title", None):
        return job.video_title  # not currently set; placeholder for future
    return url


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
```

- [ ] **Step 4: Run tests, verify they pass**

Run: `poetry run pytest tests/integration/test_pipeline.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/pipeline.py tests/integration/test_pipeline.py
git commit -m "feat(pipeline): orchestration with subtitle/ASR branching and cleanup"
```

> **Note:** `_resolve_title` is a placeholder — Task 13 (routes) will store `video_title` on `JobState` at job creation time and Task 12 will read it from there. The current Task 12 implementation falls back to URL, which test cases tolerate. Revisit when implementing routes.

---

## Task 13: Add `video_title` to JobState and Update Pipeline

**Files:**
- Modify: `src/vidistill/models.py`
- Modify: `src/vidistill/pipeline.py`
- Modify: `tests/unit/test_models.py`
- Modify: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Add `video_title` field to `JobState`**

Edit `src/vidistill/models.py`, change the `JobState` dataclass to include `video_title`:

```python
@dataclass
class JobState:
    job_id: str
    url: str
    video_title: str
    style: Style
    format: Format
    status: JobStatus
    progress: int
    error: Optional[str]
    output_path: Optional[str]
    created_at: datetime
```

- [ ] **Step 2: Update existing model test to use the new field**

In `tests/unit/test_models.py`, update `test_job_state_defaults`:

```python
def test_job_state_defaults():
    now = datetime.now()
    job = JobState(
        job_id="abc",
        url="https://x",
        video_title="Sample",
        style="chapters",
        format="md",
        status="pending",
        progress=0,
        error=None,
        output_path=None,
        created_at=now,
    )
    assert job.status == "pending"
    assert job.progress == 0
    assert job.error is None
    assert job.video_title == "Sample"
```

- [ ] **Step 3: Update pipeline to use the new field**

Edit `src/vidistill/pipeline.py`, replace the `_resolve_title` block with a direct read:

```python
        existing = store.get(job_id)
        title = existing.video_title if existing else url

        summary = llm.summarize(
            segments=segments,
            style=style,
            video_title=title,
            video_url=url,
            config=config,
        )
```

Delete the `_resolve_title` helper function entirely.

- [ ] **Step 4: Update pipeline test seeder to pass `video_title`**

In `tests/integration/test_pipeline.py`, update `_seed_job`:

```python
def _seed_job(store: JobStore, job_id="j1", style="chapters", fmt="md", title="Test Video"):
    store.create(JobState(
        job_id=job_id,
        url="https://example/v",
        video_title=title,
        style=style,
        format=fmt,
        status="pending",
        progress=0,
        error=None,
        output_path=None,
        created_at=datetime.now(),
    ))
```

- [ ] **Step 5: Run all tests, verify they pass**

Run: `poetry run pytest -v`
Expected: all previous tests still pass with the new `video_title` field.

- [ ] **Step 6: Commit**

```bash
git add src/vidistill/models.py src/vidistill/pipeline.py tests/unit/test_models.py tests/integration/test_pipeline.py
git commit -m "feat(models,pipeline): carry video_title through JobState"
```

---

## Task 14: HTTP Routes

**Files:**
- Create: `src/vidistill/routes.py`
- Create: `tests/integration/test_routes.py`

- [ ] **Step 1: Write failing tests**

Create `tests/integration/test_routes.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")
    from vidistill.main import build_app
    app = build_app(output_dir=tmp_path)
    return TestClient(app)


def test_get_root_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "vidistill" in r.text.lower() or "<form" in r.text.lower()


def test_post_jobs_rejects_invalid_url(client):
    r = client.post("/jobs", json={"url": "not-a-url", "style": "chapters", "format": "md"})
    assert r.status_code == 422


def test_post_jobs_rejects_too_long_video(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="Long", duration=3600, has_subtitle=True, url="https://x")
    with patch("vidistill.routes.video.fetch_metadata", return_value=meta):
        r = client.post("/jobs", json={"url": "https://x", "style": "short", "format": "md"})
    assert r.status_code == 422
    assert "30" in r.json()["detail"] or "时长" in r.json()["detail"]


def test_post_jobs_returns_job_id_and_queues_task(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="Short", duration=300, has_subtitle=True, url="https://x")
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.routes.process_video") as mock_pipeline,
    ):
        r = client.post("/jobs", json={"url": "https://x", "style": "short", "format": "md"})

    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert len(body["job_id"]) > 0


def test_post_jobs_rejects_when_slot_busy(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=100, has_subtitle=True, url="https://x")
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.routes.process_video"),
    ):
        # first submit — succeeds and busies the slot
        r1 = client.post("/jobs", json={"url": "https://x", "style": "short", "format": "md"})
        assert r1.status_code == 200
        # second submit — rejected
        r2 = client.post("/jobs", json={"url": "https://x", "style": "short", "format": "md"})
    assert r2.status_code == 409
    assert "正在处理" in r2.json()["detail"] or "busy" in r2.json()["detail"].lower()


def test_get_job_status(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=100, has_subtitle=True, url="https://x")
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.routes.process_video"),
    ):
        r = client.post("/jobs", json={"url": "https://x", "style": "short", "format": "md"})
    job_id = r.json()["job_id"]

    r2 = client.get(f"/jobs/{job_id}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["job_id"] == job_id
    assert body["status"] in ("pending", "fetching", "transcribing", "summarizing", "rendering", "done", "failed")
    assert "progress" in body


def test_get_unknown_job_returns_404(client):
    r = client.get("/jobs/nope")
    assert r.status_code == 404


def test_download_returns_404_for_unknown(client):
    r = client.get("/jobs/nope/download")
    assert r.status_code == 404


def test_download_returns_409_when_not_done(client):
    from vidistill.models import VideoMetadata

    meta = VideoMetadata(title="X", duration=100, has_subtitle=True, url="https://x")
    with (
        patch("vidistill.routes.video.fetch_metadata", return_value=meta),
        patch("vidistill.routes.process_video"),
    ):
        r = client.post("/jobs", json={"url": "https://x", "style": "short", "format": "md"})
    job_id = r.json()["job_id"]

    r2 = client.get(f"/jobs/{job_id}/download")
    assert r2.status_code == 409


def test_download_returns_file_when_done(client, tmp_path):
    from vidistill.models import JobState, VideoMetadata
    from vidistill.main import get_store

    # Seed a done job manually
    fake_file = tmp_path / "result.md"
    fake_file.write_text("# Done", encoding="utf-8")

    store = get_store()
    store.create(JobState(
        job_id="done1",
        url="https://x",
        video_title="Done Video",
        style="short",
        format="md",
        status="done",
        progress=100,
        error=None,
        output_path=str(fake_file),
        created_at=datetime.now(),
    ))

    r = client.get("/jobs/done1/download")
    assert r.status_code == 200
    assert r.content == b"# Done"
    assert "attachment" in r.headers.get("content-disposition", "").lower()
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `poetry run pytest tests/integration/test_routes.py -v`
Expected: ImportError on `vidistill.main` or `vidistill.routes`.

- [ ] **Step 3: Refactor `JobStore` slot API (prerequisite for clean routes)**

The `acquire_slot()` context manager from Task 11 doesn't fit the route use case (acquire in handler, release in background task). Replace with explicit `try_acquire_slot()` / `release_slot()`.

Edit `src/vidistill/jobs.py`:

```python
import threading
from dataclasses import replace
from typing import Optional

from vidistill.models import JobState


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()
        self._slot_busy = False

    def create(self, job: JobState) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> Optional[JobState]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown job_id: {job_id}")
            self._jobs[job_id] = replace(self._jobs[job_id], **kwargs)

    def try_acquire_slot(self) -> bool:
        with self._lock:
            if self._slot_busy:
                return False
            self._slot_busy = True
            return True

    def release_slot(self) -> None:
        with self._lock:
            self._slot_busy = False
```

Note: `SingleSlotBusyError` and the `@contextmanager` import are removed.

- [ ] **Step 4: Update `test_jobs.py` for new slot API**

In `tests/unit/test_jobs.py`:

1. Remove the import of `SingleSlotBusyError` (change `from vidistill.jobs import JobStore, SingleSlotBusyError` to `from vidistill.jobs import JobStore`).
2. Delete `test_single_slot_acquire_and_release`.
3. Add two new tests:

```python
def test_try_acquire_slot_returns_true_first_then_false():
    store = JobStore()
    assert store.try_acquire_slot() is True
    assert store.try_acquire_slot() is False


def test_release_slot_allows_reacquire():
    store = JobStore()
    store.try_acquire_slot()
    store.release_slot()
    assert store.try_acquire_slot() is True
```

Run: `poetry run pytest tests/unit/test_jobs.py -v`
Expected: 7 passed (5 original + 2 new).

- [ ] **Step 5: Implement `src/vidistill/routes.py`**

```python
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, HttpUrl

from vidistill.adapters import video
from vidistill.config import Config
from vidistill.exceptions import VideoFetchError
from vidistill.jobs import JobStore
from vidistill.models import Format, JobState, Style
from vidistill.pipeline import process_video
from vidistill.renderers.markdown import sanitize_filename


router = APIRouter()


class CreateJobRequest(BaseModel):
    url: HttpUrl
    style: Style = Field(default="chapters")
    format: Format = Field(default="md")


class CreateJobResponse(BaseModel):
    job_id: str


def get_templates() -> Jinja2Templates:
    templates_dir = Path(__file__).parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return get_templates().TemplateResponse("index.html", {"request": request})


@router.post("/jobs", response_model=CreateJobResponse)
def create_job(
    req: CreateJobRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    store: JobStore = request.app.state.store
    config: Config = request.app.state.config

    try:
        meta = video.fetch_metadata(str(req.url))
    except VideoFetchError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if meta.duration > config.max_video_duration_seconds:
        minutes = meta.duration // 60
        raise HTTPException(
            status_code=422,
            detail=f"视频时长 {minutes} 分钟，超过 30 分钟上限",
        )

    if not store.try_acquire_slot():
        raise HTTPException(status_code=409, detail="另一个任务正在处理中，请稍后再试")

    job_id = uuid.uuid4().hex[:12]
    store.create(JobState(
        job_id=job_id,
        url=str(req.url),
        video_title=meta.title,
        style=req.style,
        format=req.format,
        status="pending",
        progress=0,
        error=None,
        output_path=None,
        created_at=datetime.now(),
    ))

    def _runner():
        try:
            process_video(
                job_id=job_id,
                url=str(req.url),
                style=req.style,
                fmt=req.format,
                store=store,
                config=config,
            )
        finally:
            store.release_slot()

    background_tasks.add_task(_runner)
    return CreateJobResponse(job_id=job_id)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    store: JobStore = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "video_title": job.video_title,
    }


@router.get("/jobs/{job_id}/download")
def download(job_id: str, request: Request):
    store: JobStore = request.app.state.store
    job = store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=409, detail=f"任务状态：{job.status}，文件尚未就绪")

    path = Path(job.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="文件已失效，请重新提交任务")

    filename = sanitize_filename(job.video_title) + path.suffix
    return FileResponse(path=str(path), filename=filename)
```

- [ ] **Step 6: Run pipeline + jobs tests (routes still need main.py from next task)**

Run: `poetry run pytest tests/unit/test_jobs.py tests/integration/test_pipeline.py -v`
Expected: all green. Routes tests will only pass after Task 15 wires up `main.py`.

- [ ] **Step 7: Commit**

```bash
git add src/vidistill/routes.py src/vidistill/jobs.py tests/unit/test_jobs.py tests/integration/test_routes.py
git commit -m "feat(routes): HTTP endpoints + JobStore slot API refactor"
```

---

## Task 15: Main App & Templates Directory

**Files:**
- Create: `src/vidistill/main.py`
- Create: `src/vidistill/templates/index.html` (placeholder — Task 16 fills it in)

- [ ] **Step 1: Create placeholder template**

Create `src/vidistill/templates/index.html`:

```html
<!doctype html>
<html><head><meta charset="utf-8"><title>vidistill</title></head>
<body><form>placeholder</form></body></html>
```

- [ ] **Step 2: Implement `src/vidistill/main.py`**

```python
from pathlib import Path
from typing import Optional

from fastapi import FastAPI

from vidistill.config import Config, load_config
from vidistill.jobs import JobStore
from vidistill.routes import router


_GLOBAL_STORE = JobStore()


def get_store() -> JobStore:
    """Module-level accessor used by tests that seed jobs directly."""
    return _GLOBAL_STORE


def build_app(config: Optional[Config] = None, output_dir: Optional[Path] = None) -> FastAPI:
    """Construct a FastAPI app. Factored out so tests can inject overrides."""
    if config is None:
        config = load_config()
    if output_dir is not None:
        config = Config(
            dashscope_api_key=config.dashscope_api_key,
            dashscope_compatible_base_url=config.dashscope_compatible_base_url,
            qwen_model=config.qwen_model,
            paraformer_model=config.paraformer_model,
            output_dir=output_dir,
            max_video_duration_seconds=config.max_video_duration_seconds,
            pipeline_timeout_seconds=config.pipeline_timeout_seconds,
            min_free_disk_mb=config.min_free_disk_mb,
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="vidistill")
    app.state.store = _GLOBAL_STORE
    app.state.config = config
    app.include_router(router)
    return app


app = build_app()
```

- [ ] **Step 3: Run all tests including routes**

Run: `poetry run pytest -v`
Expected: all tests green (about 35-45 passing).

- [ ] **Step 4: Smoke-start the dev server**

Run: `poetry run uvicorn vidistill.main:app --port 8000`

Open `http://localhost:8000/` in a browser → see the placeholder HTML.
Press Ctrl-C to stop.

- [ ] **Step 5: Commit**

```bash
git add src/vidistill/main.py src/vidistill/templates/index.html
git commit -m "feat(main): FastAPI app factory + globals wiring"
```

---

## Task 16: Frontend (Jinja2 + Alpine.js)

**Files:**
- Modify: `src/vidistill/templates/index.html`

- [ ] **Step 1: Replace placeholder with full template**

Overwrite `src/vidistill/templates/index.html`:

```html
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>vidistill — 视频内容 AI 总结</title>
<script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
<style>
  * { box-sizing: border-box; }
  body {
    font-family: -apple-system, "Segoe UI", "Source Han Sans SC", "Microsoft YaHei", sans-serif;
    max-width: 720px; margin: 3rem auto; padding: 0 1.5rem;
    color: #222; background: #fafafa; line-height: 1.6;
  }
  h1 { margin: 0 0 .25rem; }
  .subtitle { color: #666; margin: 0 0 2rem; }
  .card { background: white; border: 1px solid #e3e3e3; border-radius: 8px; padding: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,.04); }
  label { display: block; font-weight: 600; margin: 1rem 0 .4rem; }
  input[type=url], select { width: 100%; padding: .65rem .8rem; font-size: 1rem; border: 1px solid #ccc; border-radius: 6px; }
  input[type=url]:focus, select:focus { outline: 2px solid #1a73e8; outline-offset: -1px; }
  .hint { font-size: .85rem; color: #777; margin-top: .3rem; }
  .radio-group { display: flex; gap: .8rem; flex-wrap: wrap; }
  .radio-card { flex: 1 1 240px; border: 1px solid #ccc; border-radius: 6px; padding: .8rem 1rem; cursor: pointer; transition: all .15s; }
  .radio-card.selected { border-color: #1a73e8; background: #f0f7ff; }
  .radio-card strong { display: block; }
  .radio-card .desc { font-size: .85rem; color: #555; margin-top: .25rem; }
  button.primary {
    margin-top: 1.5rem; width: 100%; padding: .9rem; font-size: 1rem; font-weight: 600;
    background: #1a73e8; color: white; border: none; border-radius: 6px; cursor: pointer;
  }
  button.primary:hover { background: #1664c8; }
  button.primary:disabled { background: #aaa; cursor: not-allowed; }
  .progress { margin-top: 1rem; }
  .progress-bar { height: 8px; background: #e3e3e3; border-radius: 4px; overflow: hidden; }
  .progress-bar-fill { height: 100%; background: #1a73e8; transition: width .3s; }
  .status-text { margin-top: .5rem; color: #555; font-size: .9rem; }
  .error { color: #c62828; background: #fee; border: 1px solid #fcc; padding: .8rem 1rem; border-radius: 6px; margin-top: 1rem; }
  .success { color: #2e7d32; background: #efe; border: 1px solid #cec; padding: .8rem 1rem; border-radius: 6px; margin-top: 1rem; }
  a.download { display: inline-block; margin-top: .6rem; padding: .6rem 1rem; background: #2e7d32; color: white; text-decoration: none; border-radius: 6px; font-weight: 600; }
  a.download:hover { background: #246627; }
  button.retry { margin-top: 1rem; padding: .5rem 1rem; background: #555; color: white; border: none; border-radius: 6px; cursor: pointer; }
</style>
</head>
<body>

<h1>vidistill</h1>
<p class="subtitle">粘贴视频链接 → AI 总结 → 下载</p>

<div class="card" x-data="vidistillApp()">

  <!-- Form -->
  <template x-if="phase === 'idle' || phase === 'submitting' || phase === 'error_input'">
    <div>
      <label for="url">视频链接</label>
      <input id="url" type="url" x-model="url" placeholder="https://www.youtube.com/watch?v=... 或 https://www.bilibili.com/video/..." required>
      <div class="hint">支持 YouTube、Bilibili 等 yt-dlp 兼容平台。视频时长不超过 30 分钟。</div>

      <label>总结形态</label>
      <div class="radio-group">
        <label class="radio-card" :class="{ selected: style === 'short' }">
          <input type="radio" x-model="style" value="short" style="display:none">
          <strong>短摘要</strong>
          <div class="desc">3-5 句核心要点 + 5-10 条 bullet。适合快速判断"这视频值不值得看"。</div>
        </label>
        <label class="radio-card" :class="{ selected: style === 'chapters' }">
          <input type="radio" x-model="style" value="chapters" style="display:none">
          <strong>章节笔记</strong>
          <div class="desc">按视频章节切分，每章一段总结 + bullet，带时间戳。适合反复查阅。</div>
        </label>
      </div>

      <label for="format">输出格式</label>
      <select id="format" x-model="format">
        <option value="md">Markdown (.md)</option>
        <option value="html">HTML (.html)</option>
        <option value="pdf">PDF (.pdf)</option>
      </select>

      <button class="primary" @click="submit()" :disabled="phase === 'submitting' || !url">
        <span x-show="phase !== 'submitting'">开始生成</span>
        <span x-show="phase === 'submitting'">提交中...</span>
      </button>

      <div class="error" x-show="phase === 'error_input'" x-text="errorMessage"></div>
    </div>
  </template>

  <!-- Progress -->
  <template x-if="phase === 'polling'">
    <div>
      <div class="status-text"><strong x-text="videoTitle || '处理中'"></strong></div>
      <div class="status-text" x-text="statusLabel()"></div>
      <div class="progress">
        <div class="progress-bar"><div class="progress-bar-fill" :style="`width: ${progress}%`"></div></div>
      </div>
      <div class="status-text" x-text="`${progress}%`"></div>
    </div>
  </template>

  <!-- Ready to download -->
  <template x-if="phase === 'ready_to_download'">
    <div>
      <div class="success">总结完成！</div>
      <div><strong x-text="videoTitle"></strong></div>
      <a class="download" :href="`/jobs/${jobId}/download`">下载 <span x-text="format.toUpperCase()"></span> 文件</a>
      <br>
      <button class="retry" @click="reset()">再来一个</button>
    </div>
  </template>

  <!-- Processing error -->
  <template x-if="phase === 'error_processing'">
    <div>
      <div class="error" x-text="errorMessage"></div>
      <button class="retry" @click="retry()">重试</button>
      <button class="retry" @click="reset()">换一个视频</button>
    </div>
  </template>
</div>

<script>
function vidistillApp() {
  return {
    phase: 'idle',
    url: '',
    style: 'chapters',
    format: 'md',
    jobId: null,
    progress: 0,
    status: 'pending',
    videoTitle: '',
    errorMessage: '',
    pollTimer: null,

    async submit() {
      this.phase = 'submitting';
      this.errorMessage = '';
      try {
        const resp = await fetch('/jobs', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url: this.url, style: this.style, format: this.format }),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: '提交失败' }));
          this.errorMessage = err.detail || `错误 ${resp.status}`;
          this.phase = 'error_input';
          return;
        }
        const data = await resp.json();
        this.jobId = data.job_id;
        this.phase = 'polling';
        this.startPolling();
      } catch (e) {
        this.errorMessage = '网络错误：' + e.message;
        this.phase = 'error_input';
      }
    },

    startPolling() {
      this.pollTimer = setInterval(() => this.poll(), 2000);
      this.poll();
    },

    async poll() {
      try {
        const resp = await fetch(`/jobs/${this.jobId}`);
        if (!resp.ok) return;
        const data = await resp.json();
        this.status = data.status;
        this.progress = data.progress;
        this.videoTitle = data.video_title || '';
        if (data.status === 'done') {
          clearInterval(this.pollTimer);
          this.phase = 'ready_to_download';
        } else if (data.status === 'failed') {
          clearInterval(this.pollTimer);
          this.errorMessage = data.error || '处理失败';
          this.phase = 'error_processing';
        }
      } catch (e) {
        // transient network error; let polling continue
      }
    },

    statusLabel() {
      const map = {
        pending: '排队中...',
        fetching: '抓取视频信息...',
        transcribing: '语音转写中（最耗时步骤）...',
        summarizing: 'AI 总结中...',
        rendering: '生成文件...',
      };
      return map[this.status] || this.status;
    },

    retry() {
      this.errorMessage = '';
      this.submit();
    },

    reset() {
      if (this.pollTimer) clearInterval(this.pollTimer);
      this.phase = 'idle';
      this.url = '';
      this.jobId = null;
      this.progress = 0;
      this.errorMessage = '';
      this.videoTitle = '';
    },
  }
}
</script>

</body>
</html>
```

- [ ] **Step 2: Manual smoke test**

Run: `poetry run uvicorn vidistill.main:app --reload --port 8000`

Open `http://localhost:8000`. Verify:
- Page loads without console errors
- Form fields visible and styled
- Toggling between "短摘要" and "章节笔记" highlights the selected card
- Without filling URL, submit button is disabled

Stop server with Ctrl-C.

- [ ] **Step 3: Commit**

```bash
git add src/vidistill/templates/index.html
git commit -m "feat(frontend): Alpine.js single-page UI with form, polling, download"
```

---

## Task 17: Dockerfile

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`

- [ ] **Step 1: Create `.dockerignore`**

```
.git
.venv
__pycache__
*.pyc
.pytest_cache
.env
.idea
.vscode
docs
tests
*.md
!README.md
```

- [ ] **Step 2: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

# System deps: ffmpeg for audio extraction, WeasyPrint runtime libs, fonts for CJK PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1
RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /app

# Install dependencies first (better layer caching)
COPY pyproject.toml poetry.lock ./
RUN poetry install --only main --no-root

# Copy source
COPY src ./src
RUN poetry install --only-root

# Create the output directory
RUN mkdir -p /tmp/vidistill

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "vidistill.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Build the image locally (if Docker installed on Windows)**

Run: `docker build -t vidistill:dev .`
Expected: build succeeds, image is ~400-500 MB.

If Docker not installed locally, skip this step — the Ubuntu server has Docker; you can build there.

- [ ] **Step 4: Smoke-run the container**

Run:
```bash
docker run --rm -p 8000:8000 -e DASHSCOPE_API_KEY=$env:DASHSCOPE_API_KEY vidistill:dev
```
(Or PowerShell variant: `docker run --rm -p 8000:8000 -e DASHSCOPE_API_KEY=$env:DASHSCOPE_API_KEY vidistill:dev`)

Open `http://localhost:8000` → page loads. Ctrl-C to stop.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "build: Dockerfile with ffmpeg, WeasyPrint deps, CJK fonts"
```

---

## Task 18: End-to-End Smoke Test (Manual)

This task is the manual checklist from the spec §8.4. **Run only after Task 17 passes and you have a real `DASHSCOPE_API_KEY` in `.env`.**

**Files:**
- Create: `docs/smoke-test-checklist.md`

- [ ] **Step 1: Create the checklist file**

```markdown
# vidistill Smoke Test Checklist

Run before any release. Requires real `DASHSCOPE_API_KEY` and ffmpeg.

## Setup

```bash
poetry install
cp .env.example .env  # fill in DASHSCOPE_API_KEY
poetry run uvicorn vidistill.main:app --port 8000
```

Open http://localhost:8000

## Tests

- [ ] **5-minute YouTube with auto-captions → Markdown**
  - URL: (paste one)
  - Style: 章节笔记
  - Format: Markdown
  - Expect: download .md file with chapters, timestamps

- [ ] **5-minute Bilibili without subtitle → PDF (validates Chinese font + ASR)**
  - URL: (paste one)
  - Style: 章节笔记
  - Format: PDF
  - Expect: PDF opens correctly, Chinese characters render properly (not boxes)

- [ ] **Same video, switch to 短摘要 → Markdown**
  - Expect: shorter file with `## 摘要` and `## 要点`

- [ ] **35-minute video → rejected immediately**
  - Expect: 422 with "超过 30 分钟" message before processing starts

- [ ] **Invalid URL (404 video) → readable error**
  - Expect: 422 with yt-dlp's error surfaced cleanly

- [ ] **Close tab mid-progress → reopen page is blank**
  - Verifies Q11 behavior (no resume)

- [ ] **Submit while another task is running → 409**
  - Expect: "另一个任务正在处理中" message

- [ ] **Download a completed file twice → both work**
  - Verifies file is not deleted after first download
```

- [ ] **Step 2: Run all smoke tests manually**

Tick each box as you verify.

- [ ] **Step 3: Commit checklist**

```bash
git add docs/smoke-test-checklist.md
git commit -m "docs: smoke test checklist"
```

---

## Final Verification

- [ ] **Run full test suite**

```bash
poetry run pytest -v
```

Expected: all unit + integration tests pass. Approximately 45 tests.

- [ ] **Verify project structure matches spec**

Expected tree (under `src/vidistill/`):
```
src/vidistill/
├── __init__.py
├── main.py
├── routes.py
├── jobs.py
├── pipeline.py
├── prompts.py
├── config.py
├── models.py
├── exceptions.py
├── adapters/
│   ├── __init__.py
│   ├── video.py
│   ├── asr.py
│   └── llm.py
├── renderers/
│   ├── __init__.py
│   ├── markdown.py
│   ├── html.py
│   └── pdf.py
└── templates/
    └── index.html
```

- [ ] **Verify Docker image builds and runs**

(Already done in Task 17.)

- [ ] **Smoke test checklist all green**

(From Task 18.)

---

## Implementation Notes & Caveats

These are things the spec calls out but the test-driven plan above couldn't fully exercise without live API calls:

1. **Paraformer SDK specifics:** `_call_paraformer` in `src/vidistill/adapters/asr.py` uses `Transcription.async_call` with a `file://` URI. The DashScope batch ASR API historically requires an HTTPS URL. If this fails against the live API, the agent must switch to:
   - Option A: Use `dashscope.audio.asr.Recognition` (realtime API, accepts local file streams)
   - Option B: Upload audio to a temporary public URL (OSS, S3, or even a small static file server the container exposes on a random port)
   The **contract** of `_call_paraformer` (input audio path + config, output `{"output": {"sentences": [...]}}`) is stable; only the body changes.

2. **WeasyPrint on Windows:** If `poetry install` fails on `weasyprint`, install GTK runtime per WeasyPrint Windows docs, OR develop using Docker only and skip local PDF testing.

3. **Pipeline total timeout:** Spec §7.2 mentions a 30-minute total pipeline timeout via `asyncio.wait_for`. The current pipeline implementation is synchronous (uses `BackgroundTasks`, not async). To add a hard total timeout, wrap the pipeline body in a `threading.Timer` that flips the job to `failed` after 30 min, OR rewrite the pipeline to be `async def` and use `asyncio.wait_for`. **Defer this to a follow-up task** — for single-user usage, the 25-min Paraformer poll cap already bounds the most likely runaway case.

4. **Disk-space guard:** Spec §7.2 mentions a 500MB free-disk check before starting a pipeline. Not implemented in this plan — add as a follow-up task if disk pressure becomes a real concern. For single-user 30-min cap, audio is ~30MB and won't fill disk in practice.

5. **Git remote:** This plan does `git init` but does not configure a remote. If you want to push to GitHub / GitLab / company-internal Gitea later, do that separately.
