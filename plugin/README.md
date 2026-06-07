# youtube-chapters — a Hermes Agent plugin

Generate YouTube chapter markers (`00:00 Title` lines) for a video URL. The
plugin pulls the transcript (manual captions → auto captions → local Whisper),
asks the Hermes-configured LLM to split it into chapters with content-specific
titles, then validates the result against YouTube's rules.

## Install

Copy this directory to `~/.hermes/plugins/youtube-chapters/`, then:

```
pip install -r ~/.hermes/plugins/youtube-chapters/requirements.txt
hermes plugins reload
```

## Usage

```
> Generate chapters for https://youtube.com/watch?v=XXXXXXXXXXX
```

The model will call the `youtube_generate_chapters` tool. Optional flags:

- `prefer_whisper=true` — skip captions, transcribe locally with Whisper.
- `whisper_model=small` — `tiny | base | small | medium | large-v3`.
- `regenerate=true` — ignore the video's existing chapters and produce new ones.
- `title_language=auto` — `auto` follows the transcript; otherwise e.g. `English`, `Turkish`.

Output is a paste-ready block:

```
00:00 Introduction and overview
01:42 Installation steps
06:18 The configuration file
...
```

## LLM configuration (IO Intelligence)

The plugin doesn't pick an LLM — it uses Hermes's active provider via `ctx.llm`.
For IO Intelligence (io.net), an OpenAI-compatible endpoint:

```
export IOINTELLIGENCE_API_KEY=...   # set in your shell/profile, never in config files

hermes config set model.provider custom
hermes config set model.base_url https://api.intelligence.io.solutions/api/v1
hermes config set model.default meta-llama/Llama-3.3-70B-Instruct
```

The plugin never reads `IOINTELLIGENCE_API_KEY` itself; Hermes handles auth.
Choose an IO model with at least **64K context** (Hermes requires this at startup).
Even with a large window, long transcripts are chunked by the plugin.

IO Intelligence has a free daily token allowance per model that is generous for
personal use; heavy or commercial use may exceed the free tier.

## Limitations

- **Whisper time.** When no captions exist, transcription runs locally. A 30-minute
  video on `small` takes a few minutes on CPU and seconds on a modern GPU.
  Long videos (>2h) are warned about.
- **Hardware.** `faster-whisper` runs on CPU but is much faster with CUDA. Larger
  models (`medium`, `large-v3`) need more RAM/VRAM.
- **Privacy.** When local Whisper is used, audio never leaves your machine.
- **Legal.** Downloading audio from YouTube may violate the YouTube Terms of
  Service outside of personal/research use. Use responsibly.
