from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from backend.app.application.generate_chapters import GenerateChaptersService


@dataclass
class ChapterJob:
    id: str
    status: str = "queued"
    stage: str = "queued"
    message: str = "Waiting to start"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ChapterJobManager:
    def __init__(self, service: GenerateChaptersService, max_workers: int = 2) -> None:
        self._service = service
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="chapters")
        self._jobs: dict[str, ChapterJob] = {}
        self._lock = threading.Lock()

    def create(self, video_id: str, **options: Any) -> ChapterJob:
        job = ChapterJob(id=uuid.uuid4().hex)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job.id, video_id, options)
        return self.get(job.id)

    def get(self, job_id: str) -> ChapterJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise KeyError(job_id)
            return ChapterJob(**asdict(job))

    def _update(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for name, value in changes.items():
                setattr(job, name, value)
            job.updated_at = datetime.now(timezone.utc).isoformat()

    def _run(self, job_id: str, video_id: str, options: dict[str, Any]) -> None:
        self._update(job_id, status="running")

        def progress(stage: str, message: str) -> None:
            self._update(job_id, stage=stage, message=message)

        try:
            result = self._service.execute(video_id, progress=progress, **options)
        except Exception as error:
            self._update(
                job_id,
                status="failed",
                stage="failed",
                message="Chapter generation failed",
                error=str(error),
            )
            return
        self._update(
            job_id,
            status="completed",
            stage="completed",
            message="Chapters are ready",
            result=asdict(result),
        )
