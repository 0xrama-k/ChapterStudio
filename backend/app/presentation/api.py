from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.application.generate_chapters import GenerateChaptersService
from backend.app.application.jobs import ChapterJobManager
from backend.app.domain.models import ChapterGenerationError, InvalidVideoIdError


class GenerateChaptersRequest(BaseModel):
    video_id: str = Field(min_length=11, max_length=11)
    regenerate: bool = False
    prefer_whisper: bool = False
    whisper_model: str = "small"
    title_language: str = "auto"


def build_router(service: GenerateChaptersService, jobs: ChapterJobManager | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/chapters")
    def generate_chapters_endpoint(request: GenerateChaptersRequest) -> dict:
        try:
            result = service.execute(
                request.video_id,
                regenerate=request.regenerate,
                prefer_whisper=request.prefer_whisper,
                whisper_model=request.whisper_model,
                title_language=request.title_language,
            )
        except InvalidVideoIdError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ChapterGenerationError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        return asdict(result)

    if jobs is not None:
        @router.post("/chapter-jobs", status_code=202)
        def create_chapter_job(request: GenerateChaptersRequest) -> dict:
            job = jobs.create(
                request.video_id,
                regenerate=request.regenerate,
                prefer_whisper=request.prefer_whisper,
                whisper_model=request.whisper_model,
                title_language=request.title_language,
            )
            return {
                "job_id": job.id,
                "status": job.status,
                "status_url": f"/api/v1/chapter-jobs/{job.id}",
                "view_url": f"/jobs/{job.id}",
            }

        @router.get("/chapter-jobs/{job_id}")
        def get_chapter_job(job_id: str) -> dict:
            try:
                return asdict(jobs.get(job_id))
            except KeyError as error:
                raise HTTPException(status_code=404, detail="Job not found.") from error

    return router
