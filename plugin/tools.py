"""Tool handler that wires transcript → chapters → formatting together.

Real Hermes contract: handler takes ``(args: dict, **kw) -> str`` and returns
a JSON string built by ``tool_result(...)`` or ``tool_error(...)``.

The ``ctx`` is passed in via ``kw['ctx']`` when the registry calls us; we
also accept it as ``kw['plugin_ctx']`` to stay forward-compatible.
"""

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


def _resolve_ctx(kw: dict) -> Any:
    """Find the plugin context Hermes hands to the handler."""
    for key in ("ctx", "plugin_ctx", "context", "plugin_context"):
        ctx = kw.get(key)
        if ctx is not None and hasattr(ctx, "llm"):
            return ctx
    # Some registry versions pass it positionally; the caller may also have
    # the LLM attached directly.
    return kw.get("ctx") or kw.get("plugin_ctx")


def handle_youtube_generate_chapters(args: dict, **kw) -> str:
    """Hermes tool handler for `youtube_generate_chapters`."""
    from tools.registry import tool_error, tool_result  # local import: only available inside Hermes

    url = str(args.get("url") or "").strip()
    if not url:
        return tool_error("url is required")

    prefer_whisper = bool(args.get("prefer_whisper") or False)
    whisper_model = str(args.get("whisper_model") or "small")
    regenerate = bool(args.get("regenerate") or False)
    title_language = str(args.get("title_language") or "auto")

    ctx = _resolve_ctx(kw)
    if ctx is None or not hasattr(ctx, "llm"):
        return tool_error(
            "Plugin context with `.llm` was not provided to the handler. "
            "Hermes >=0.14 is required."
        )

    try:
        video_id = extract_video_id(url)
    except ValueError as e:
        return tool_error(str(e))

    notices: list[str] = []
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
        return tool_error(f"Could not obtain a transcript: {e}")

    if transcript.source == "whisper" and not prefer_whisper:
        notices.append(
            "No usable YouTube captions found. Audio was downloaded and transcribed locally with Whisper."
        )
    if transcript.duration_seconds > 2 * 3600 and transcript.source == "whisper":
        notices.append(
            f"Long video (~{transcript.duration_seconds / 3600:.1f}h); transcription may have taken a while."
        )

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
        return tool_error(f"Chapter generation failed: {e}")

    if chapter_source == "existing" and not regenerate:
        notices.append(
            "This video already has chapters; using them directly. "
            "Call again with `regenerate=true` to produce new ones via the LLM."
        )

    formatted = to_youtube_chapters(chapters, transcript.duration_seconds)

    return tool_result(
        success=True,
        video_id=video_id,
        transcript_source=transcript.source,
        transcript_source_label=_SOURCE_LABEL.get(transcript.source, transcript.source),
        transcript_language=transcript.language,
        duration_seconds=transcript.duration_seconds,
        chapter_source=chapter_source,
        chapter_count=len(formatted.chapters),
        chapters_text=formatted.text,
        warnings=formatted.warnings,
        notices=notices,
    )
