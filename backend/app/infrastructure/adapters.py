from __future__ import annotations

from backend.app.domain.models import (
    Chapter,
    ChapterGenerationError,
    InvalidVideoIdError,
    ProgressCallback,
    Transcript,
    TranscriptSegment,
    VideoMetadata,
)
from backend.app.infrastructure.chapter_generation import (
    ChapterError,
    generate_chapters,
    get_video_metadata,
)
from backend.app.infrastructure.formatting import to_youtube_chapters
from backend.app.infrastructure.transcript import TranscriptError, extract_video_id, get_transcript


class YouTubeVideoProvider:
    def validate_video_id(self, video_id: str) -> str:
        try:
            parsed = extract_video_id(video_id.strip())
        except ValueError as error:
            raise InvalidVideoIdError(str(error)) from error
        if parsed != video_id.strip():
            raise InvalidVideoIdError("Send only the 11-character YouTube video ID, not a URL.")
        return parsed

    def get_metadata(self, video_id: str) -> VideoMetadata:
        metadata = get_video_metadata(video_id)
        return VideoMetadata(
            chapters=[
                Chapter(start_seconds=chapter.start_seconds, title=chapter.title)
                for chapter in metadata.chapters
            ],
            duration_seconds=metadata.duration_seconds,
        )

    def get_transcript(
        self,
        video_id: str,
        *,
        prefer_whisper: bool,
        whisper_model: str,
        progress: ProgressCallback | None = None,
    ) -> Transcript:
        try:
            transcript = get_transcript(
                video_id,
                prefer_whisper=prefer_whisper,
                whisper_model=whisper_model,
                progress=progress,
            )
        except TranscriptError as error:
            raise ChapterGenerationError(f"Could not obtain transcript: {error}") from error
        return Transcript(
            segments=[
                TranscriptSegment(start=segment.start, end=segment.end, text=segment.text)
                for segment in transcript.segments
            ],
            source=transcript.source,
            language=transcript.language,
            duration_seconds=transcript.duration_seconds,
        )


class ChapterGeneratorAdapter:
    def __init__(self, llm_context: object) -> None:
        self._llm_context = llm_context

    def generate(
        self,
        segments: list[TranscriptSegment],
        *,
        duration_seconds: float,
        title_language: str,
    ) -> list[Chapter]:
        try:
            chapters = generate_chapters(
                self._llm_context,
                segments,
                duration_seconds=duration_seconds,
                title_language=title_language,
            )
        except ChapterError as error:
            raise ChapterGenerationError(str(error)) from error
        return [
            Chapter(start_seconds=chapter.start_seconds, title=chapter.title)
            for chapter in chapters
        ]


class ChapterFormatterAdapter:
    def format(
        self,
        chapters: list[Chapter],
        duration_seconds: float,
    ) -> tuple[str, int, list[str]]:
        formatted = to_youtube_chapters(chapters, duration_seconds)
        return formatted.text, len(formatted.chapters), formatted.warnings
