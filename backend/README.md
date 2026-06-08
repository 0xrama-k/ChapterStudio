# YouTube Chapters Backend

FastAPI backend for generating chapter text from an 11-character YouTube video ID.
It owns the transcript, chapter-generation, formatting, and LLM integration code used
by the ChapterStudio website.

## Architecture

```text
presentation/      HTTP request and response handling
application/       chapter-generation use case
domain/            models, errors, and dependency ports
infrastructure/    YouTube/plugin and OpenAI-compatible LLM adapters
```

## Configuration

Copy the example environment file:

```powershell
Copy-Item backend\.env.example .env
```

Then edit `.env` and enter your IO Intelligence API key. The backend loads `.env`
automatically when it starts. The `.env` file is ignored by Git.

## Run

From the repository root:

```powershell
py -m pip install -r backend/requirements.txt
py -m uvicorn backend.app.main:app --reload
```

The browser frontend is available at `http://127.0.0.1:8000/`.
OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

The frontend creates a background job and opens a linked progress page. Progress is
kept in memory, so active jobs are lost when the backend restarts.

## Request

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/chapters `
  -ContentType application/json `
  -Body '{"video_id":"arj7oStGLkU"}'
```

The response includes a `chapters_text` field ready to paste into YouTube.

## Usage diagnostics

`GET /api/v1/llm-usage` returns cumulative provider-reported token usage since the
backend started:

```json
{"requests": 3, "prompt_tokens": 9000, "completion_tokens": 850, "total_tokens": 9850}
```
