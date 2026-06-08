from __future__ import annotations

from backend.app.domain.models import (
    ChapterFormatter,
    ChapterGenerator,
    ChapterResult,
    ProgressCallback,
    VideoProvider,
)


class GenerateChaptersService:
    def __init__(
        self,
        video_provider: VideoProvider,
        chapter_generator: ChapterGenerator,
        chapter_formatter: ChapterFormatter,
    ) -> None:
        self._video_provider = video_provider
        self._chapter_generator = chapter_generator
        self._chapter_formatter = chapter_formatter

    def execute(
        self,
        video_id: str,
        *,
        regenerate: bool = False,
        prefer_whisper: bool = False,
        whisper_model: str = "small",
        title_language: str = "auto",
        progress: ProgressCallback | None = None,
    ) -> ChapterResult:
        self._report(progress, "validating", "Validating YouTube video ID")
        video_id = self._video_provider.validate_video_id(video_id)
        self._report(progress, "metadata", "Checking video metadata and existing chapters")
        metadata = self._video_provider.get_metadata(video_id)

        if metadata.chapters and not regenerate:
            self._report(progress, "formatting", "Formatting existing chapters")
            text, count, warnings = self._chapter_formatter.format(
                metadata.chapters,
                metadata.duration_seconds,
            )
            return ChapterResult(
                video_id=video_id,
                chapters_text=text,
                chapter_count=count,
                chapter_source="existing",
                transcript_source="not_required",
                transcript_language="unknown",
                duration_seconds=metadata.duration_seconds,
                warnings=warnings,
                notices=["The video's existing chapters were returned."],
            )

        transcript = self._video_provider.get_transcript(
            video_id,
            prefer_whisper=prefer_whisper,
            whisper_model=whisper_model,
            progress=progress,
        )
        duration = metadata.duration_seconds or transcript.duration_seconds
        self._report(progress, "generating", "Generating chapter titles with the LLM")
        chapters = self._chapter_generator.generate(
            transcript.segments,
            duration_seconds=duration,
            title_language=title_language,
        )
        self._report(progress, "formatting", "Formatting and validating chapter markers")
        text, count, warnings = self._chapter_formatter.format(chapters, duration)

        notices: list[str] = []
        if transcript.source == "whisper":
            notices.append("YouTube captions were unavailable or skipped; local Whisper was used.")

        return ChapterResult(
            video_id=video_id,
            chapters_text=text,
            chapter_count=count,
            chapter_source="llm",
            transcript_source=transcript.source,
            transcript_language=transcript.language,
            duration_seconds=duration,
            warnings=warnings,
            notices=notices,
        )

    @staticmethod
    def _report(progress: ProgressCallback | None, stage: str, message: str) -> None:
        if progress is not None:
            progress(stage, message)
