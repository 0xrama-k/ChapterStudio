"""Hermes tool schemas — what the model sees when deciding whether to call us."""

from __future__ import annotations

YOUTUBE_GENERATE_CHAPTERS_SCHEMA = {
    "name": "youtube_generate_chapters",
    "description": (
        "Generate a YouTube chapter list (timestamped table of contents) for a given "
        "YouTube video URL or video ID. Returns text the creator can paste directly "
        "into the video description (lines like `00:00 Introduction`). Call this when "
        "the user asks to create, regenerate, or improve chapters / timestamps / a "
        "table of contents for a YouTube video. The tool acquires the transcript "
        "automatically (manual captions → auto captions → local Whisper) and uses the "
        "Hermes-configured LLM to title each chapter; no API keys are needed in this tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "YouTube video URL or 11-character video ID.",
            },
            "prefer_whisper": {
                "type": "boolean",
                "description": (
                    "Skip YouTube captions and transcribe locally with Whisper. "
                    "Useful when captions exist but are low quality."
                ),
                "default": False,
            },
            "whisper_model": {
                "type": "string",
                "description": (
                    "faster-whisper model size when the Whisper fallback runs. "
                    "One of: tiny, base, small, medium, large-v3."
                ),
                "default": "small",
            },
            "regenerate": {
                "type": "boolean",
                "description": (
                    "Ignore any chapters the video already has and produce a new set "
                    "via the LLM."
                ),
                "default": False,
            },
            "title_language": {
                "type": "string",
                "description": (
                    "Language for chapter titles. 'auto' uses the transcript's language; "
                    "otherwise pass a language name like 'English' or 'Turkish'."
                ),
                "default": "auto",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    },
}


ALL_SCHEMAS = [YOUTUBE_GENERATE_CHAPTERS_SCHEMA]
