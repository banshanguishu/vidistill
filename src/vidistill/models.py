from dataclasses import dataclass, field
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
    video_title: str
    style: Style
    status: JobStatus
    progress: int
    error: Optional[str]
    created_at: datetime
    output_paths: dict[str, Optional[str]] = field(default_factory=dict)
