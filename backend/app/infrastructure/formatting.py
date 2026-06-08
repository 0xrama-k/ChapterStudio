"""YouTube chapter formatting + validation.

Pure functions: take a list of chapter dicts ({start_seconds, title}) and a
video duration, return either a YouTube-ready string or a structured warning.

YouTube rules enforced here:
- First chapter must start at 00:00 (shifted/inserted if missing).
- At least 3 chapters required; fewer => warning.
- Each chapter at least 10 seconds long; closer ones are merged.
- Time format: MM:SS under 1 hour, HH:MM:SS otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

MIN_CHAPTERS = 3
MIN_SPACING_SECONDS = 10


@dataclass
class Chapter:
    start_seconds: int
    title: str


@dataclass
class FormatResult:
    text: str
    chapters: list[Chapter]
    warnings: list[str] = field(default_factory=list)


def _coerce(raw: Iterable) -> list[Chapter]:
    """Accept Chapter, ChapterCandidate (from chapters.py), or plain dicts."""
    out: list[Chapter] = []
    for c in raw:
        if isinstance(c, Chapter):
            out.append(c)
            continue
        if hasattr(c, "start_seconds") and hasattr(c, "title"):
            start = int(round(float(c.start_seconds)))
            title = str(c.title).strip()
        else:
            start = int(round(float(c["start_seconds"])))
            title = str(c["title"]).strip()
        if not title:
            continue
        out.append(Chapter(start_seconds=max(0, start), title=title))
    return out


def format_timestamp(seconds: int, use_hours: bool) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if use_hours:
        return f"{h:02d}:{m:02d}:{s:02d}"
    # MM:SS, allow >59 minutes only if caller said no hours (won't happen here)
    return f"{m:02d}:{s:02d}"


def _enforce_zero_start(chapters: list[Chapter]) -> tuple[list[Chapter], list[str]]:
    warnings: list[str] = []
    if not chapters:
        return chapters, warnings
    chapters.sort(key=lambda c: c.start_seconds)
    if chapters[0].start_seconds != 0:
        # Shift the earliest chapter to 0 rather than inventing a fake title.
        warnings.append(
            f"First chapter started at {chapters[0].start_seconds}s; shifted to 00:00 per YouTube rules."
        )
        chapters[0] = Chapter(start_seconds=0, title=chapters[0].title)
    return chapters, warnings


def _merge_close(chapters: list[Chapter], min_gap: int) -> tuple[list[Chapter], list[str]]:
    if len(chapters) <= 1:
        return chapters, []
    warnings: list[str] = []
    merged: list[Chapter] = [chapters[0]]
    for ch in chapters[1:]:
        prev = merged[-1]
        if ch.start_seconds - prev.start_seconds < min_gap:
            warnings.append(
                f"Merged chapter at {ch.start_seconds}s into previous (gap < {min_gap}s)."
            )
            continue
        merged.append(ch)
    return merged, warnings


def to_youtube_chapters(
    raw_chapters: Iterable[dict | Chapter],
    duration_seconds: float,
) -> FormatResult:
    chapters = _coerce(raw_chapters)
    warnings: list[str] = []

    # Drop chapters past the video's actual duration (LLM hallucinations).
    if duration_seconds > 0:
        before = len(chapters)
        chapters = [c for c in chapters if c.start_seconds < duration_seconds]
        if len(chapters) < before:
            warnings.append(
                f"Dropped {before - len(chapters)} chapter(s) past the video duration."
            )

    chapters, w = _enforce_zero_start(chapters)
    warnings.extend(w)

    chapters, w = _merge_close(chapters, MIN_SPACING_SECONDS)
    warnings.extend(w)

    if len(chapters) < MIN_CHAPTERS:
        warnings.append(
            f"Only {len(chapters)} chapter(s) produced; YouTube requires at least {MIN_CHAPTERS}. "
            "This is usually because the video is too short."
        )

    use_hours = duration_seconds >= 3600 or any(
        c.start_seconds >= 3600 for c in chapters
    )

    lines = [f"{format_timestamp(c.start_seconds, use_hours)} {c.title}" for c in chapters]
    return FormatResult(text="\n".join(lines), chapters=chapters, warnings=warnings)
