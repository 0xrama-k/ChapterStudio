"""youtube-chapters plugin entry point.

Hermes loads this module and calls ``register(ctx)`` once at plugin discovery.
The single tool is wired into the ``youtube-chapters`` toolset.
"""

from __future__ import annotations

import logging

from .schemas import YOUTUBE_GENERATE_CHAPTERS_SCHEMA
from .tools import handle_youtube_generate_chapters

log = logging.getLogger(__name__)

__version__ = "0.1.0"


def register(ctx) -> None:
    """Wire the youtube_generate_chapters tool into Hermes."""
    ctx.register_tool(
        name="youtube_generate_chapters",
        toolset="youtube-chapters",
        schema=YOUTUBE_GENERATE_CHAPTERS_SCHEMA,
        handler=handle_youtube_generate_chapters,
        description="Generate a paste-ready YouTube chapter list for a video URL.",
        emoji="🎬",
    )
