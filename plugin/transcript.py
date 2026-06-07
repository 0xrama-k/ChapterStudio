"""Transcript acquisition with a tiered fallback chain.

Order (first that succeeds wins):
    1. Manual YouTube captions (youtube-transcript-api)
    2. Auto/ASR YouTube captions (youtube-transcript-api)
    3. Local Whisper (faster-whisper) on audio downloaded via yt-dlp

All three paths return the same `TranscriptResult` shape so downstream code
doesn't care which one was used.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})")


class TranscriptError(Exception):
    """Raised when no transcript can be obtained by any method."""


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    segments: list[Segment]
    source: str  # "manual" | "auto" | "whisper"
    language: str
    duration_seconds: float


def extract_video_id(url_or_id: str) -> str:
    """Accept a full YouTube URL or a bare 11-char video ID."""
    s = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = _VIDEO_ID_RE.search(s)
    if m:
        return m.group(1)
    raise ValueError(f"Could not extract a YouTube video ID from: {url_or_id!r}")


def _try_youtube_captions(video_id: str) -> Optional[TranscriptResult]:
    """Returns a result for manual or auto captions, or None if neither is available."""
    try:
        from youtube_transcript_api import (  # type: ignore
            YouTubeTranscriptApi,
            TranscriptsDisabled,
            NoTranscriptFound,
            VideoUnavailable,
        )
    except ImportError as e:
        log.warning("youtube-transcript-api not installed: %s", e)
        return None

    try:
        listing = YouTubeTranscriptApi.list_transcripts(video_id)
    except (TranscriptsDisabled, NoTranscriptFound):
        return None
    except VideoUnavailable as e:
        raise TranscriptError(f"Video unavailable: {e}") from e
    except Exception as e:  # network, IP block, etc.
        log.info("Caption listing failed (%s); falling back.", e)
        return None

    # Prefer manual captions over auto. Within each, prefer English-like; otherwise first.
    manual = [t for t in listing if not t.is_generated]
    auto = [t for t in listing if t.is_generated]

    for kind, group, source in (("manual", manual, "manual"), ("auto", auto, "auto")):
        if not group:
            continue
        chosen = group[0]
        try:
            raw = chosen.fetch()
        except Exception as e:
            log.info("Fetching %s captions failed (%s); trying next.", kind, e)
            continue
        segs = [
            Segment(
                start=float(item["start"]),
                end=float(item["start"]) + float(item.get("duration", 0.0)),
                text=str(item["text"]).strip(),
            )
            for item in raw
            if str(item.get("text", "")).strip()
        ]
        if not segs:
            continue
        duration = max(s.end for s in segs)
        return TranscriptResult(
            segments=segs,
            source=source,
            language=getattr(chosen, "language_code", "unknown"),
            duration_seconds=duration,
        )
    return None


def _download_audio(video_id: str, dest_dir: str) -> tuple[str, float]:
    """Download bestaudio-only and return (filepath, duration_seconds)."""
    try:
        import yt_dlp  # type: ignore
    except ImportError as e:
        raise TranscriptError(
            "yt-dlp is required for the Whisper fallback. Install with `pip install yt-dlp`."
        ) from e

    out_template = os.path.join(dest_dir, "%(id)s.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        # Avoid full-video download; bestaudio is usually m4a/webm.
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        raise TranscriptError(f"Could not download audio: {e}") from e

    filepath = None
    for fn in os.listdir(dest_dir):
        if fn.startswith(video_id):
            filepath = os.path.join(dest_dir, fn)
            break
    if filepath is None:
        raise TranscriptError("Audio download succeeded but no file was found on disk.")

    duration = float(info.get("duration") or 0.0)
    return filepath, duration


def _transcribe_whisper(
    audio_path: str, model_name: str, duration_hint: float
) -> tuple[list[Segment], str]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise TranscriptError(
            "faster-whisper is required for local transcription. "
            "Install with `pip install faster-whisper`."
        ) from e

    if duration_hint and duration_hint > 2 * 3600:
        log.warning(
            "Video is %.1f hours long; local Whisper transcription will take a while.",
            duration_hint / 3600,
        )

    model = WhisperModel(model_name, device="auto", compute_type="auto")
    segments_iter, info = model.transcribe(audio_path, vad_filter=True)
    segs = [
        Segment(start=float(s.start or 0.0), end=float(s.end or 0.0), text=s.text.strip())
        for s in segments_iter
        if (s.text or "").strip()
    ]
    return segs, getattr(info, "language", "unknown") or "unknown"


def get_transcript(
    video_id: str,
    *,
    prefer_whisper: bool = False,
    whisper_model: str = "small",
) -> TranscriptResult:
    """Get a transcript via the tiered fallback chain.

    Raises TranscriptError if every method fails.
    """
    video_id = extract_video_id(video_id)

    if not prefer_whisper:
        result = _try_youtube_captions(video_id)
        if result is not None:
            return result
        log.info("No usable YouTube captions; falling back to Whisper.")

    tmpdir = tempfile.mkdtemp(prefix="hermes-yt-")
    try:
        audio_path, duration = _download_audio(video_id, tmpdir)
        segs, language = _transcribe_whisper(audio_path, whisper_model, duration)
        if not segs:
            raise TranscriptError("Whisper produced no segments (audio may be silent or unreadable).")
        if not duration and segs:
            duration = max(s.end for s in segs)
        return TranscriptResult(
            segments=segs,
            source="whisper",
            language=language,
            duration_seconds=duration,
        )
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
