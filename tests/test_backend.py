import unittest
import urllib.error
import time
import json
from unittest.mock import patch

from backend.app.application.generate_chapters import GenerateChaptersService
from backend.app.application.jobs import ChapterJobManager
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.domain.models import Chapter, ChapterResult, Transcript, TranscriptSegment, VideoMetadata
from backend.app.presentation.api import build_router
from backend.app.presentation.frontend import FRONTEND_INDEX
from backend.app.infrastructure.openai_compatible import OpenAiCompatibleLlm


class FakeVideoProvider:
    def __init__(self, metadata, transcript=None):
        self.metadata = metadata
        self.transcript = transcript
        self.transcript_calls = 0

    def validate_video_id(self, video_id):
        return video_id

    def get_metadata(self, video_id):
        return self.metadata

    def get_transcript(self, video_id, *, prefer_whisper, whisper_model, progress=None):
        self.transcript_calls += 1
        return self.transcript


class FakeGenerator:
    def generate(self, segments, *, duration_seconds, title_language):
        return [
            Chapter(0, "Start"),
            Chapter(30, "Middle"),
            Chapter(60, "End"),
        ]


class FakeFormatter:
    def format(self, chapters, duration_seconds):
        text = "\n".join(f"{chapter.start_seconds} {chapter.title}" for chapter in chapters)
        return text, len(chapters), []


class GenerateChaptersServiceTests(unittest.TestCase):
    def test_existing_chapters_do_not_fetch_transcript_or_call_llm(self):
        provider = FakeVideoProvider(
            VideoMetadata(
                chapters=[Chapter(0, "Existing start"), Chapter(30, "Existing end")],
                duration_seconds=60,
            )
        )
        service = GenerateChaptersService(provider, FakeGenerator(), FakeFormatter())

        result = service.execute("arj7oStGLkU")

        self.assertEqual(result.chapter_source, "existing")
        self.assertEqual(result.transcript_source, "not_required")
        self.assertEqual(provider.transcript_calls, 0)

    def test_missing_chapters_use_transcript_and_generator(self):
        provider = FakeVideoProvider(
            VideoMetadata(chapters=[], duration_seconds=90),
            Transcript(
                segments=[TranscriptSegment(start=0, end=2, text="Hello")],
                source="manual",
                language="en",
                duration_seconds=80,
            ),
        )
        service = GenerateChaptersService(provider, FakeGenerator(), FakeFormatter())

        result = service.execute("arj7oStGLkU")

        self.assertEqual(result.chapter_source, "llm")
        self.assertEqual(result.chapter_count, 3)
        self.assertEqual(result.duration_seconds, 90)
        self.assertEqual(provider.transcript_calls, 1)


class ApiTests(unittest.TestCase):
    def test_post_chapters_returns_generated_text(self):
        class FakeService:
            def execute(self, video_id, **kwargs):
                return ChapterResult(
                    video_id=video_id,
                    chapters_text="00:00 Start\n00:30 Middle\n01:00 End",
                    chapter_count=3,
                    chapter_source="llm",
                    transcript_source="manual",
                    transcript_language="en",
                    duration_seconds=90,
                )

        app = FastAPI()
        app.include_router(build_router(FakeService()))
        client = TestClient(app)

        response = client.post("/api/v1/chapters", json={"video_id": "arj7oStGLkU"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["chapters_text"], "00:00 Start\n00:30 Middle\n01:00 End")

    def test_frontend_asset_contains_chapter_form(self):
        content = FRONTEND_INDEX.read_text(encoding="utf-8")

        self.assertIn('id="chapter-form"', content)
        self.assertIn('fetch("/api/v1/chapter-jobs"', content)
        self.assertNotIn('id="whisper-model"', content)
        self.assertNotIn('id="prefer-whisper"', content)

    def test_background_job_completes_and_returns_result(self):
        class FakeService:
            def execute(self, video_id, *, progress, **kwargs):
                progress("transcribing", "Transcribing audio")
                return ChapterResult(
                    video_id=video_id,
                    chapters_text="00:00 Start",
                    chapter_count=1,
                    chapter_source="llm",
                    transcript_source="whisper",
                    transcript_language="en",
                    duration_seconds=30,
                )

        jobs = ChapterJobManager(FakeService(), max_workers=1)
        app = FastAPI()
        app.include_router(build_router(FakeService(), jobs))
        client = TestClient(app)

        created = client.post("/api/v1/chapter-jobs", json={"video_id": "arj7oStGLkU"})
        self.assertEqual(created.status_code, 202)
        job_id = created.json()["job_id"]

        for _ in range(20):
            job = client.get(f"/api/v1/chapter-jobs/{job_id}").json()
            if job["status"] == "completed":
                break
            time.sleep(0.01)

        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["result"]["chapters_text"], "00:00 Start")


class OpenAiCompatibleLlmTests(unittest.TestCase):
    def test_request_limits_completion_tokens(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return (
                    b'{"choices":[{"message":{"content":"[]"}}],'
                    b'"usage":{"prompt_tokens":100,"completion_tokens":20,"total_tokens":120}}'
                )

        llm = OpenAiCompatibleLlm("https://example.test", "secret", "model")
        with patch("urllib.request.urlopen", return_value=Response()) as urlopen:
            llm.complete(messages=[{"role": "user", "content": "hello"}])

        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["max_tokens"], 1200)
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(
            llm.usage_snapshot(),
            {"requests": 1, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        )

    def test_http_error_includes_provider_response(self):
        error = urllib.error.HTTPError(
            url="https://example.test/chat/completions",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=__import__("io").BytesIO(b'{"detail":"invalid API key"}'),
        )
        llm = OpenAiCompatibleLlm("https://example.test", "secret", "model")

        with patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(Exception, 'HTTP 403.*invalid API key'):
                llm.complete(messages=[{"role": "user", "content": "hello"}])


if __name__ == "__main__":
    unittest.main()
