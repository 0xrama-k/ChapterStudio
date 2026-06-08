from __future__ import annotations

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse

from backend.app.application.generate_chapters import GenerateChaptersService
from backend.app.application.jobs import ChapterJobManager
from backend.app.infrastructure.openai_compatible import LlmContext, OpenAiCompatibleLlm
from backend.app.infrastructure.adapters import (
    ChapterFormatterAdapter,
    ChapterGeneratorAdapter,
    YouTubeVideoProvider,
)
from backend.app.presentation.api import build_router
from backend.app.presentation.frontend import FRONTEND_INDEX, FRONTEND_PROGRESS

load_dotenv()


def create_app() -> FastAPI:
    llm = OpenAiCompatibleLlm.from_environment()
    llm_context = LlmContext(llm)
    service = GenerateChaptersService(
        video_provider=YouTubeVideoProvider(),
        chapter_generator=ChapterGeneratorAdapter(llm_context),
        chapter_formatter=ChapterFormatterAdapter(),
    )
    jobs = ChapterJobManager(service)
    app = FastAPI(title="YouTube Chapters API", version="1.0.0")
    app.include_router(build_router(service, jobs))

    @app.get("/", include_in_schema=False)
    def frontend() -> FileResponse:
        return FileResponse(FRONTEND_INDEX)

    @app.get("/jobs/{job_id}", include_in_schema=False)
    def progress_view(job_id: str) -> FileResponse:
        return FileResponse(FRONTEND_PROGRESS)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/llm-usage")
    def llm_usage() -> dict[str, int]:
        return llm.usage_snapshot()

    return app


app = create_app()
