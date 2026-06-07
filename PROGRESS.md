# Build Progress: Hermes YouTube Chapters Plugin

Tracking implementation against `instruction.txt`.

## Plan
1. Scaffold project layout (`plugin/` directory matching the spec)
2. `formatting.py` — pure functions, validation, time formatting
3. `transcript.py` — fallback chain (manual → auto → Whisper)
4. `chapters.py` — deterministic + LLM strategies with chunking
5. `schemas.py` — tool schema(s) for the Hermes model
6. `tools.py` — handler that wires the pipeline together
7. `__init__.py` — Hermes `register()`
8. `plugin.yaml` — manifest
9. `requirements.txt`
10. `README.md` — install / usage / IO Intelligence / limitations

## Status

- [x] Repo init + spec committed
- [x] PROGRESS.md created
- [x] Project layout (`plugin/`)
- [x] `formatting.py` — to_youtube_chapters, MM:SS vs HH:MM:SS, 00:00 enforcement, 10s merge, ≥3 warning
- [x] `transcript.py` — manual → auto → Whisper fallback; extract_video_id; yt-dlp bestaudio download
- [x] `chapters.py` — yt-dlp existing-chapters lookup; LLM chunked path; tolerant JSON parse; one retry on bad JSON; ctx.llm shape probing in one helper
- [x] `schemas.py` — `youtube_generate_chapters` schema
- [x] `tools.py` — pipeline handler, structured `{ok, ...}` return
- [x] `__init__.py` — `register()` with binding-shape fallbacks
- [x] `plugin.yaml` — manifest (schema v21, hermes >=0.14)
- [x] `requirements.txt`
- [x] `README.md` — install, IO Intelligence env-var setup, limitations
- [x] Smoke test pure logic (formatting edge cases, video ID parsing, JSON parsing, chunking)

## Verified locally (no network)
- All modules byte-compile clean
- `formatting.to_youtube_chapters` handles: normal, first-not-zero shift, <10s merge, past-duration drop, hours threshold
- `transcript.extract_video_id` handles bare ID + watch?v + youtu.be + /shorts/
- `chapters._parse_json_array` handles plain JSON, ```json fences```, JSON embedded in prose
- `chapters._chunk_text` splits a 2000-line transcript correctly

## Not verified (needs live env)
- Live YouTube caption fetch (requires `youtube-transcript-api` + network + non-blocked IP)
- yt-dlp audio download
- faster-whisper transcription
- Real `ctx.llm` integration — funneled through a single helper, so easy to fix once Hermes's signature is confirmed

## Notes / decisions
- Built under `./plugin/` in this repo; user copies it to `~/.hermes/plugins/youtube-chapters/`
- `_call_llm` tries 3 common signatures; spec said the exact shape isn't standardized
- Plugin code never reads `IOINTELLIGENCE_API_KEY` — Hermes owns auth (per spec §8)
- Tool returns `{ok: False, error: ...}` for normal failures instead of raising
