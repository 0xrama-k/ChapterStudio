from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

ProgressCallback = Callable[[str, str], None]


class InvalidVideoIdError(ValueError):
    """Raised when the supplied value is not a YouTube video ID."""


class ChapterGenerationError(RuntimeError):
    """Raised when chapters cannot be generated."""


@dataclass(frozen=True)
class Chapter:
    start_seconds: int
    title: str


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    segments: list[TranscriptSegment]
    source: str
    language: str
    duration_seconds: float


@dataclass(frozen=True)
class VideoMetadata:
    chapters: list[Chapter]
    duration_seconds: float


@dataclass(frozen=True)
class ChapterResult:
    video_id: str
    chapters_text: str
    chapter_count: int
    chapter_source: str
    transcript_source: str
    transcript_language: str
    duration_seconds: float
    warnings: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)


class VideoProvider(Protocol):
    def validate_video_id(self, video_id: str) -> str: ...

    def get_metadata(self, video_id: str) -> VideoMetadata: ...

    def get_transcript(
        self,
        video_id: str,
        *,
        prefer_whisper: bool,
        whisper_model: str,
        progress: ProgressCallback | None = None,
    ) -> Transcript: ...


class ChapterGenerator(Protocol):
    def generate(
        self,
        segments: list[TranscriptSegment],
        *,
        duration_seconds: float,
        title_language: str,
    ) -> list[Chapter]: ...


class ChapterFormatter(Protocol):
    def format(
        self,
        chapters: list[Chapter],
        duration_seconds: float,
    ) -> tuple[str, int, list[str]]: ...
