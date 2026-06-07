# Build Progress: Hermes YouTube Chapters Plugin

Tracking implementation against `instruction.txt`.

## Status

- [x] Repo init + spec committed
- [x] PROGRESS.md created
- [x] Project layout (`plugin/`)
- [x] `formatting.py` — to_youtube_chapters, MM:SS vs HH:MM:SS, 00:00 enforcement, 10s merge, ≥3 warning
- [x] `transcript.py` — manual → auto → Whisper fallback; extract_video_id; yt-dlp bestaudio download
- [x] `chapters.py` — yt-dlp existing-chapters lookup; LLM chunked path; tolerant JSON parse; one retry
- [x] `schemas.py` — `youtube_generate_chapters` schema
- [x] `tools.py` — pipeline handler
- [x] `__init__.py` — `register()`
- [x] `plugin.yaml` — manifest
- [x] `requirements.txt`
- [x] `README.md`
- [x] Initial smoke tests of pure logic

## Real Hermes integration (round 2)

Installed `hermes-agent` 0.16.0 from PyPI, learned the real contract, rewrote
the integration layer:

- [x] `plugin.yaml` — real manifest fields (`kind: standalone`, `provides_tools`); dropped the made-up `schema_version`/`entrypoint`
- [x] `__init__.register(ctx)` — uses the real `ctx.register_tool(name=, toolset=, schema=, handler=, ...)` API
- [x] `tools.py` handler — real signature `(args: dict, **kw) -> str`, returns JSON via `tools.registry.tool_result` / `tool_error`
- [x] `chapters._call_llm` — uses the documented `ctx.llm.complete(messages=...).text` (the `PluginLlm` surface)
- [x] Plugin installed at `%LOCALAPPDATA%\hermes\plugins\youtube-chapters\`
- [x] `hermes plugins enable youtube-chapters` — succeeded
- [x] `discover_plugins(force=True)` loads it without errors; `tools_registered: ['youtube_generate_chapters']`
- [x] Tool appears in `tools.registry._tools` with correct toolset `youtube-chapters`
- [x] End-to-end handler call with stub LLM and stub transcript — returns the formatted YouTube chapter block

### Bug found and fixed during integration
- `formatting._coerce` only accepted `Chapter` and dict, but `pick_chapters` returns `chapters.ChapterCandidate`. Fixed to duck-type on `start_seconds`/`title` attributes so all three shapes work.

## Verified end-to-end (with stubs for network/LLM)

```
success: True
transcript_source: auto
chapter_source: llm
chapter_count: 3
chapters_text:
00:00 Opening
01:30 Demo of the feature
04:00 Q and A
warnings: []
notices: []
```

## Not yet verified (needs network or paid credentials)
- Live YouTube caption fetch (requires `youtube-transcript-api`, network, non-blocked IP)
- yt-dlp audio download
- faster-whisper transcription
- Real `ctx.llm` against IO Intelligence (requires `IOINTELLIGENCE_API_KEY` and `hermes config set model.*`)

## Notes / decisions
- Source kept in `./plugin/`, copied to `%LOCALAPPDATA%\hermes\plugins\youtube-chapters\` for the install
- Spec said "Hermes >= v0.14, schema v21"; PyPI has 0.16.0 which uses the kind/provides_tools manifest, not schema_version. Updated manifest to match what the loader actually accepts.
- Plugin code does not read `IOINTELLIGENCE_API_KEY` — Hermes owns auth via `PluginLlm`.
