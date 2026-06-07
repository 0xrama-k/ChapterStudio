# Build Progress: Hermes YouTube Chapters Plugin

## Status: WORKING END-TO-END against real Hermes + IO Intelligence

## Verified live (real YouTube video, real LLM)

Test video: `https://www.youtube.com/watch?v=arj7oStGLkU` (14-min TED Tim Urban talk)

**Run 1 (deterministic path):** existing chapters from yt-dlp metadata, no LLM call
**Run 2 (LLM path with `regenerate=true`):** Whisper transcribed audio on CPU, Llama-3.3-70B (IO Intelligence) generated:

```
00:00 Introduction to Procrastination
00:51 The 90-Page Senior Thesis
02:55 The Blog and Procrastination Research
03:40 The Brain of a Procrastinator
04:58 The Instant Gratification Monkey
07:17 The Panic Monster and Procrastination
10:55 The Dark Side of Procrastination
13:24 Confronting Procrastination and Making a Change
```

Format validator caught that the LLM's first chapter started at 12s and shifted to 00:00 per YouTube rules.

## Issues found + fixed during real runs

1. **Plugin contract mismatch (round 2).** Spec said `register(plugin_api)` + `ctx.llm(prompt)`; real Hermes 0.16 uses `register(ctx)` + `ctx.register_tool(name=, toolset=, schema=, handler=)` + `ctx.llm.complete(messages=...).text`. Fixed.
2. **Handler signature.** Real signature is `(args: dict, **kw) -> str` returning `tool_result(...)` / `tool_error(...)` JSON, not arbitrary Python dicts. Fixed.
3. **`formatting._coerce` rejected `ChapterCandidate`.** Crashed `pick_chapters → to_youtube_chapters`. Fixed: duck-type on `start_seconds`/`title`.
4. **Whisper hard-failed on missing CUDA.** `device="auto"` tried CUDA, `cublas64_12.dll` missing on this machine. Fixed: catch `RuntimeError`/`OSError` and retry with `device="cpu", compute_type="int8"`.
5. **Windows Store Python filesystem virtualization.** `C:\Users\ramaz\AppData\Local\hermes\` is redirected to the Store sandbox under `LocalCache\Local\hermes\`. `Write` tool put my `config.yaml` at the real path; `hermes`/Python read from the sandbox path. Workaround: copy config to the sandbox path so Hermes actually sees it.
6. **Credential pool needed `model.api_key` not just `model.key_env`.** `_resolve_custom_runtime` read `key_env`, but the main `call_llm` path seeds credentials from `model.api_key`. Fixed by setting `api_key: ${IOINTELLIGENCE_API_KEY}` (env-var expansion) in `model:`.

## How to run

1. Open a NEW terminal so `.env` reloads.
2. `hermes` — starts the interactive REPL.
3. In the REPL: `Generate chapters for https://www.youtube.com/watch?v=...`
4. Model invokes `youtube_generate_chapters` and prints the paste-ready block.

For force-regeneration when the video already has chapters: ask the model to "regenerate them with the LLM" — it'll set `regenerate=true`.

## Not verified
- Live YouTube manual/auto caption fetch (the test video had captions disabled; Whisper path fired instead). The code path is the same one used in the spec's first acceptance test.
- IO Intelligence chunking on a long transcript (>~10K segments). The chunking logic was unit-tested with 2000 fake lines; a real 3-hour video would exercise it for real.
