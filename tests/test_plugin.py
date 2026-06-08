import sys
import types
import unittest
from unittest.mock import patch

from plugin.chapters import (
    ChapterCandidate,
    ChapterError,
    MAX_REPAIR_RESPONSE_CHARS,
    VideoMetadata,
    _ask_llm_for_chapters,
    _build_prompt,
    _flatten_segments,
)
from plugin.formatting import to_youtube_chapters
from plugin.transcript import Segment, _friendly_download_error, _try_youtube_captions


class TranscriptTests(unittest.TestCase):
    def test_download_dns_error_is_user_friendly(self):
        message = _friendly_download_error(
            Exception(
                "\x1b[0;31mERROR:\x1b[0m Failed to resolve 'www.youtube.com' "
                "([Errno 11001] getaddrinfo failed)"
            )
        )

        self.assertIn("DNS resolution failed", message)
        self.assertNotIn("\x1b", message)

    def test_current_youtube_transcript_api_objects_are_supported(self):
        module = types.ModuleType("youtube_transcript_api")

        class TranscriptsDisabled(Exception):
            pass

        class NoTranscriptFound(Exception):
            pass

        class VideoUnavailable(Exception):
            pass

        snippet = types.SimpleNamespace(start=2.0, duration=3.5, text=" Hello ")
        fetched = types.SimpleNamespace(snippets=[snippet])
        transcript = types.SimpleNamespace(
            is_generated=False,
            language_code="en",
            fetch=lambda: fetched,
        )

        class YouTubeTranscriptApi:
            def list(self, video_id):
                self.video_id = video_id
                return [transcript]

        module.YouTubeTranscriptApi = YouTubeTranscriptApi
        module.TranscriptsDisabled = TranscriptsDisabled
        module.NoTranscriptFound = NoTranscriptFound
        module.VideoUnavailable = VideoUnavailable

        with patch.dict(sys.modules, {"youtube_transcript_api": module}):
            result = _try_youtube_captions("abcdefghijk")

        self.assertEqual(result.source, "manual")
        self.assertEqual(result.language, "en")
        self.assertEqual(result.duration_seconds, 5.5)
        self.assertEqual(result.segments[0].text, "Hello")

    def test_legacy_youtube_transcript_api_is_supported(self):
        module = types.ModuleType("youtube_transcript_api")
        module.TranscriptsDisabled = type("TranscriptsDisabled", (Exception,), {})
        module.NoTranscriptFound = type("NoTranscriptFound", (Exception,), {})
        module.VideoUnavailable = type("VideoUnavailable", (Exception,), {})

        transcript = types.SimpleNamespace(
            is_generated=True,
            language_code="tr",
            fetch=lambda: [{"start": 1, "duration": 2, "text": "Merhaba"}],
        )

        class YouTubeTranscriptApi:
            @staticmethod
            def list_transcripts(video_id):
                return [transcript]

        module.YouTubeTranscriptApi = YouTubeTranscriptApi

        with patch.dict(sys.modules, {"youtube_transcript_api": module}):
            result = _try_youtube_captions("abcdefghijk")

        self.assertEqual(result.source, "auto")
        self.assertEqual(result.segments[0].text, "Merhaba")


class ChapterTests(unittest.TestCase):
    def test_json_repair_prompt_is_compact_and_truncated(self):
        prompts = []

        def complete(**kwargs):
            prompt = kwargs["messages"][0]["content"]
            prompts.append(prompt)
            if len(prompts) == 1:
                return types.SimpleNamespace(text="x" * (MAX_REPAIR_RESPONSE_CHARS + 500))
            return types.SimpleNamespace(text='[{"start_seconds": 0, "title": "Start"}]')

        ctx = types.SimpleNamespace(llm=types.SimpleNamespace(complete=complete))
        chapters = _ask_llm_for_chapters(
            ctx,
            "[0s] hello",
            duration_seconds=60,
            title_language="auto",
            is_chunk=False,
        )

        self.assertEqual(chapters[0].title, "Start")
        self.assertLess(len(prompts[1]), MAX_REPAIR_RESPONSE_CHARS + 300)
        self.assertNotIn("Transcript (each line", prompts[1])

    def test_flatten_segments_removes_rolling_caption_overlap(self):
        flattened = _flatten_segments(
            [
                Segment(0, 2, "Today we configure the database connection"),
                Segment(2, 4, "the database connection and create the schema"),
                Segment(4, 6, "and create the schema"),
            ]
        )

        self.assertEqual(
            flattened,
            "[0s] Today we configure the database connection\n"
            "[2s] and create the schema",
        )

    def test_chunk_prompt_uses_chunk_duration(self):
        prompt = _build_prompt(
            "[600s] first\n[660s] second",
            duration_seconds=7200,
            title_language="auto",
            is_chunk=True,
        )
        self.assertIn("supplied transcript range (~60s)", prompt)
        self.assertNotIn("~7200s", prompt)

    def test_empty_valid_model_output_is_an_error(self):
        ctx = types.SimpleNamespace(
            llm=types.SimpleNamespace(
                complete=lambda **kwargs: types.SimpleNamespace(text='[{"bad": "item"}]')
            )
        )
        with self.assertRaisesRegex(ChapterError, "no valid chapter"):
            _ask_llm_for_chapters(
                ctx,
                "[0s] hello",
                duration_seconds=60,
                title_language="auto",
                is_chunk=False,
            )


class ToolTests(unittest.TestCase):
    def test_existing_chapters_skip_transcript_and_llm_context(self):
        registry = types.ModuleType("tools.registry")
        registry.tool_error = lambda message: {"error": message}
        registry.tool_result = lambda **kwargs: kwargs

        metadata = VideoMetadata(
            chapters=[
                ChapterCandidate(0, "Start"),
                ChapterCandidate(20, "Middle"),
                ChapterCandidate(40, "End"),
            ],
            duration_seconds=60,
        )

        with patch.dict(sys.modules, {"tools.registry": registry}):
            with patch("plugin.tools.get_video_metadata", return_value=metadata):
                with patch("plugin.tools.get_transcript") as get_transcript:
                    from plugin.tools import handle_youtube_generate_chapters

                    result = handle_youtube_generate_chapters({"url": "abcdefghijk"})

        get_transcript.assert_not_called()
        self.assertEqual(result["chapter_source"], "existing")
        self.assertEqual(result["transcript_source"], "not_required")

    def test_metadata_duration_prevents_caption_tail_from_dropping_chapters(self):
        result = to_youtube_chapters(
            [
                ChapterCandidate(0, "Start"),
                ChapterCandidate(50, "Middle"),
                ChapterCandidate(90, "Silent ending"),
            ],
            duration_seconds=100,
        )
        self.assertEqual(len(result.chapters), 3)


if __name__ == "__main__":
    unittest.main()
