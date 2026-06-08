"""Chapter generation.

Two strategies, tried in order:

A. Deterministic: if the video already has YouTube chapters (yt-dlp metadata's
   `chapters` field), use them directly. No LLM call needed.

B. LLM-based: flatten the transcript into a single timestamped text, chunk if
   needed, and ask `ctx.llm` to return strict JSON of {start_seconds, title}.
   Retry once if the response isn't parseable JSON.

The LLM call is funneled through `_call_llm(ctx, prompt)` so the exact
signature of `ctx.llm` is easy to adjust in one place.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from .transcript import Segment

log = logging.getLogger(__name__)

# Roughly 4 chars per token; leaves headroom for prompt + completion in a 64K window.
DEFAULT_CHUNK_CHARS = 40_000


class ChapterError(Exception):
    pass


@dataclass
class ChapterCandidate:
    start_seconds: int
    title: str


@dataclass
class VideoMetadata:
    chapters: list[ChapterCandidate]
    duration_seconds: float


# ---------------------------------------------------------------------------
# Strategy A — existing video chapters from yt-dlp metadata
# ---------------------------------------------------------------------------


def get_video_metadata(video_id: str) -> VideoMetadata:
    """Return useful video metadata. Never raises when metadata is unavailable."""
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        return VideoMetadata(chapters=[], duration_seconds=0.0)

    url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
    except Exception as e:
        log.info("yt-dlp metadata lookup failed (%s); skipping deterministic path.", e)
        return VideoMetadata(chapters=[], duration_seconds=0.0)

    raw = info.get("chapters") or []
    out: list[ChapterCandidate] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        start = c.get("start_time")
        title = c.get("title")
        if start is None or not title:
            continue
        try:
            start_seconds = int(round(float(start)))
        except (TypeError, ValueError):
            continue
        out.append(ChapterCandidate(start_seconds=start_seconds, title=str(title).strip()))
    try:
        duration_seconds = float(info.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration_seconds = 0.0
    return VideoMetadata(
        chapters=out,
        duration_seconds=duration_seconds,
    )


def chapters_from_metadata(video_id: str) -> Optional[list[ChapterCandidate]]:
    """Return the video's own chapters if any, else None."""
    return get_video_metadata(video_id).chapters or None


# ---------------------------------------------------------------------------
# Strategy B — LLM-based chaptering
# ---------------------------------------------------------------------------


def _remove_repeated_prefix(previous: str, current: str) -> str:
    """Remove caption text repeated from the end of the previous segment."""
    previous_words = previous.split()
    current_words = current.split()
    max_overlap = min(len(previous_words), len(current_words), 30)
    for size in range(max_overlap, 2, -1):
        previous_tail = [word.casefold() for word in previous_words[-size:]]
        current_head = [word.casefold() for word in current_words[:size]]
        if previous_tail == current_head:
            return " ".join(current_words[size:]).strip()
    return current.strip()


def _flatten_segments(segments: list[Segment]) -> str:
    """One line per segment, dropping repeated rolling-caption prefixes."""
    lines: list[str] = []
    previous_text = ""
    for segment in segments:
        text = _remove_repeated_prefix(previous_text, segment.text.strip())
        if text:
            lines.append(f"[{int(segment.start)}s] {text}")
        previous_text = segment.text.strip()
    return "\n".join(lines)


def _chunk_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    lines = text.split("\n")
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in lines:
        if size + len(line) + 1 > max_chars and buf:
            chunks.append("\n".join(buf))
            buf = [line]
            size = len(line)
        else:
            buf.append(line)
            size += len(line) + 1
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _chapter_density_hint(duration_seconds: float, minimum: int = 3) -> str:
    minutes = max(1.0, duration_seconds / 60.0)
    low = max(minimum, int(round(minutes / 10 * 3)))
    high = max(low + 1, int(round(minutes / 10 * 6)))
    return f"{low}-{high}"


def _chunk_duration(flattened: str, fallback: float) -> float:
    timestamps = [int(value) for value in re.findall(r"^\[(\d+)s\]", flattened, re.MULTILINE)]
    if len(timestamps) >= 2:
        return max(60.0, float(timestamps[-1] - timestamps[0]))
    return fallback


def _build_prompt(
    flattened: str,
    *,
    duration_seconds: float,
    title_language: str,
    is_chunk: bool,
) -> str:
    lang_clause = (
        "Write titles in the same language as the transcript."
        if title_language == "auto"
        else f"Write titles in {title_language}."
    )
    prompt_duration = _chunk_duration(flattened, duration_seconds) if is_chunk else duration_seconds
    density = _chapter_density_hint(prompt_duration, minimum=1 if is_chunk else 3)
    scope = (
        "This is one CHUNK of a longer transcript; propose chapters only for the time range it covers."
        if is_chunk
        else "Cover the entire transcript."
    )
    return f"""You are generating YouTube chapter markers for a video.

Transcript (each line: `[<seconds>s] text`):
---
{flattened}
---

Rules:
- Start a new chapter at meaningful topic or subtopic shifts.
- Give each chapter a SPECIFIC, content-reflecting title (e.g. "Setting up the PostgreSQL connection"). Generic titles like "Chapter 2" or "Part one" are FORBIDDEN.
- Aim for roughly {density} chapters for the supplied transcript range (~{int(prompt_duration)}s).
- {scope}
- {lang_clause}
- `start_seconds` MUST be an integer that exists in the transcript timestamps (or very near one).

Output STRICTLY a JSON array. No prose, no markdown fences, no commentary:
[{{"start_seconds": <int>, "title": "<str>"}}, ...]
"""


_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _parse_json_array(text: str) -> list[dict]:
    """Tolerant parse: strip markdown fences, find the first [...] block."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        m = _JSON_ARRAY_RE.search(cleaned)
        if not m:
            raise
        data = json.loads(m.group(0))
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array.")
    return data


def _call_llm(ctx: Any, prompt: str) -> str:
    """Funnel point for the Hermes ``ctx.llm`` call.

    Uses the documented :class:`agent.plugin_llm.PluginLlm` surface:
    ``ctx.llm.complete(messages=...).text``. Kept in one place so it's easy
    to adjust if the host API shifts.
    """
    llm = getattr(ctx, "llm", None)
    if llm is None:
        raise ChapterError("Hermes context has no `llm` attribute; cannot call the model.")

    complete = getattr(llm, "complete", None)
    if not callable(complete):
        raise ChapterError("ctx.llm has no .complete() method; Hermes >=0.14 required.")

    try:
        result = complete(messages=[{"role": "user", "content": prompt}])
    except Exception as e:
        raise ChapterError(f"LLM call failed: {e}") from e

    text = getattr(result, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("text", "content", "output", "response"):
            value = result.get(key)
            if isinstance(value, str):
                return value
    raise ChapterError(f"Unexpected ctx.llm.complete() return type: {type(result).__name__}")


def _ask_llm_for_chapters(
    ctx: Any,
    flattened: str,
    *,
    duration_seconds: float,
    title_language: str,
    is_chunk: bool,
) -> list[ChapterCandidate]:
    prompt = _build_prompt(
        flattened,
        duration_seconds=duration_seconds,
        title_language=title_language,
        is_chunk=is_chunk,
    )
    raw = _call_llm(ctx, prompt)
    try:
        data = _parse_json_array(raw)
    except (json.JSONDecodeError, ValueError) as e:
        # One retry with an explicit fix request.
        fix_prompt = (
            "Your previous reply was not valid JSON. Reply with ONLY a JSON array of "
            '{"start_seconds": int, "title": str} objects. No fences, no prose. '
            f"Your previous reply was:\n---\n{raw}\n---"
        )
        raw2 = _call_llm(ctx, fix_prompt)
        try:
            data = _parse_json_array(raw2)
        except (json.JSONDecodeError, ValueError) as e2:
            raise ChapterError(f"Model did not return valid JSON after retry: {e2}") from e

    out: list[ChapterCandidate] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            start = int(round(float(item["start_seconds"])))
            title = str(item["title"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if title:
            out.append(ChapterCandidate(start_seconds=max(0, start), title=title))
    if not out:
        raise ChapterError("Model returned no valid chapter objects.")
    return out


def _merge_chunk_chapters(
    chunks: list[list[ChapterCandidate]],
) -> list[ChapterCandidate]:
    flat: list[ChapterCandidate] = [c for group in chunks for c in group]
    flat.sort(key=lambda c: c.start_seconds)
    # Dedup near-identical starts (within 5 seconds), keep the earlier title.
    deduped: list[ChapterCandidate] = []
    for c in flat:
        if deduped and c.start_seconds - deduped[-1].start_seconds < 5:
            continue
        deduped.append(c)
    return deduped


def generate_chapters(
    ctx: Any,
    segments: list[Segment],
    *,
    duration_seconds: float,
    title_language: str = "auto",
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
) -> list[ChapterCandidate]:
    """Generate chapters from transcript segments using the LLM."""
    if not segments:
        raise ChapterError("No transcript segments provided.")

    flattened = _flatten_segments(segments)
    chunks = _chunk_text(flattened, chunk_chars)

    if len(chunks) == 1:
        return _ask_llm_for_chapters(
            ctx,
            chunks[0],
            duration_seconds=duration_seconds,
            title_language=title_language,
            is_chunk=False,
        )

    log.info("Transcript split into %d chunks for chaptering.", len(chunks))
    per_chunk = [
        _ask_llm_for_chapters(
            ctx,
            chunk,
            duration_seconds=duration_seconds,
            title_language=title_language,
            is_chunk=True,
        )
        for chunk in chunks
    ]
    return _merge_chunk_chapters(per_chunk)


# ---------------------------------------------------------------------------
# Top-level orchestrator the tool handler calls
# ---------------------------------------------------------------------------


def pick_chapters(
    ctx: Any,
    *,
    video_id: str,
    segments: list[Segment],
    duration_seconds: float,
    regenerate: bool,
    title_language: str,
) -> tuple[list[ChapterCandidate], str]:
    """Return (chapters, source) where source is 'existing' or 'llm'."""
    if not regenerate:
        existing = chapters_from_metadata(video_id)
        if existing:
            return existing, "existing"
    chapters = generate_chapters(
        ctx,
        segments,
        duration_seconds=duration_seconds,
        title_language=title_language,
    )
    return chapters, "llm"
