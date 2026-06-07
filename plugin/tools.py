"""Tool handler that wires transcript → chapters → formatting together."""

from __future__ import annotations

import logging
from typing import Any

from .chapters import ChapterError, pick_chapters
from .formatting import to_youtube_chapters
from .transcript import TranscriptError, extract_video_id, get_transcript

log = logging.getLogger(__name__)


_SOURCE_LABEL = {
    "manual": "manual YouTube captions",
    "auto": "auto-generated YouTube captions",
    "whisper": "local Whisper transcription",
}


def youtube_generate_chapters(
    ctx: Any,
    url: str,
    prefer_whisper: bool = False,
    whisper_model: str = "small",
    regenerate: bool = False,
    title_language: str = "auto",
) -> dict:
    """Handler bound to the `youtube_generate_chapters` schema.

    Returns a dict the Hermes UI can render. Never raises for normal failure
    modes — those come back as `{"ok": False, "error": "..."}`.
    """
    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    notices: list[str] = []

    # Step 2: transcript
    if prefer_whisper:
        notices.append(
            "Skipping YouTube captions; downloading audio and transcribing locally with Whisper. "
            "This may take several minutes for long videos."
        )
    try:
        transcript = get_transcript(
            video_id,
            prefer_whisper=prefer_whisper,
            whisper_model=whisper_model,
        )
    except TranscriptError as e:
        return {"ok": False, "error": f"Could not obtain a transcript: {e}"}

    if transcript.source == "whisper" and not prefer_whisper:
        notices.append(
            "No usable YouTube captions found. Audio was downloaded and transcribed locally with Whisper."
        )
    if transcript.duration_seconds > 2 * 3600 and transcript.source == "whisper":
        notices.append(
            f"Long video (~{transcript.duration_seconds / 3600:.1f}h); transcription may have taken a while."
        )

    # Step 3: chapters
    try:
        chapters, chapter_source = pick_chapters(
            ctx,
            video_id=video_id,
            segments=transcript.segments,
            duration_seconds=transcript.duration_seconds,
            regenerate=regenerate,
            title_language=title_language,
        )
    except ChapterError as e:
        return {"ok": False, "error": f"Chapter generation failed: {e}"}

    if chapter_source == "existing":
        if regenerate:
            # Belt-and-suspenders: pick_chapters honored `regenerate=True`, so this
            # branch shouldn't fire — but if it ever does, the user should know.
            notices.append("Used the video's existing chapters (regenerate was requested but the LLM path was skipped).")
        else:
            notices.append(
                "This video already has chapters; using them directly. "
                "Call again with `regenerate=true` to produce new ones via the LLM."
            )

    # Step 4: format + validate
    formatted = to_youtube_chapters(chapters, transcript.duration_seconds)

    return {
        "ok": True,
        "video_id": video_id,
        "transcript_source": transcript.source,
        "transcript_source_label": _SOURCE_LABEL.get(transcript.source, transcript.source),
        "transcript_language": transcript.language,
        "duration_seconds": transcript.duration_seconds,
        "chapter_source": chapter_source,
        "chapter_count": len(formatted.chapters),
        "chapters_text": formatted.text,
        "warnings": formatted.warnings,
        "notices": notices,
    }


HANDLERS = {
    "youtube_generate_chapters": youtube_generate_chapters,
}
