# ChapterStudio

ChapterStudio automatically generates ready-to-use YouTube chapter timestamps and
titles. Paste a video link, choose the title language, and copy the generated
chapters into the video description.

## Run locally

```powershell
py -m pip install -r backend/requirements.txt
py -m uvicorn backend.app.main:app --reload
```

Configure `LLM_API_KEY`, `LLM_MODEL`, and optionally `LLM_BASE_URL` in `.env`
before starting the server.
