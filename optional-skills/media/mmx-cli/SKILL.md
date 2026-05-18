---
name: mmx-cli
description: Use when the user wants MiniMax's official mmx CLI for text chat, image/video generation, speech, music, vision, web search, quota checks, file upload, or MiniMax API resource management from a terminal.
version: 1.0.0
author: MiniMaxAI (adapted by Nous Research)
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [minimax, mmx, cli, image, video, speech, music, search, vision]
    related_skills: [comfyui, heartmula, songsee, youtube-content]
  upstream:
    repo: https://github.com/MiniMax-AI/cli
    path: skill/SKILL.md
    package: mmx-cli
---

# MiniMax CLI — Agent Skill Guide

Use `mmx` to generate text, images, video, speech, music, perform web search, inspect quota, upload/list/delete files, and call MiniMax models via the official MiniMax AI platform CLI.

## Hermes-specific setup

`mmx` is optional because it depends on Node.js 18+ and a MiniMax Token Plan. Prefer this skill when a task needs MiniMax features that Hermes' native tools do not expose yet, especially video generation, music generation, voice design, quota inspection, file management, MiniMax web search, or MiniMax vision from the terminal.

```bash
# Install globally
npm install -g mmx-cli

# Or run without global install
npx -y mmx-cli --help

# Authenticate interactively: supports MiniMax OAuth or an API key
mmx auth login

# Headless/API-key auth
mmx auth login --api-key sk-xxxxx

# Verify active auth source and quota
mmx auth status
mmx quota
```

If Hermes already has MiniMax OAuth configured, `mmx auth login` is still the official path because the CLI persists credentials under `~/.mmx/`. Do not copy tokens from `~/.hermes/auth.json` into chat. For one-off noninteractive calls where the user provides a MiniMax API key, pass it through the environment or `--api-key`; do not hardcode it in scripts or commits.

Region is auto-detected. Override with `--region global` or `--region cn`.

---

## Agent flags

Always use these flags in non-interactive agent/CI contexts:

| Flag | Purpose |
|---|---|
| `--non-interactive` | Fail fast on missing args instead of prompting |
| `--quiet` | Suppress spinners/progress; stdout is pure data |
| `--output json` | Machine-readable JSON output |
| `--async` | Return task ID immediately (video generation) |
| `--dry-run` | Preview the API request without executing |
| `--yes` | Skip confirmation prompts |

---

## Commands

### text chat

Chat completion. Default model: `MiniMax-M2.7`.

```bash
mmx text chat --message <text> [flags]
```

| Flag | Type | Description |
|---|---|---|
| `--message <text>` | string, **required**, repeatable | Message text. Prefix with `role:` to set role, e.g. `"system:You are helpful"`, `"user:Hello"` |
| `--messages-file <path>` | string | JSON file with messages array. Use `-` for stdin |
| `--system <text>` | string | System prompt |
| `--model <model>` | string | Model ID, default `MiniMax-M2.7`; use `MiniMax-M2.7-highspeed` for lower latency |
| `--max-tokens <n>` | number | Max tokens, default 4096 |
| `--temperature <n>` | number | Sampling temperature `(0.0, 1.0]` |
| `--top-p <n>` | number | Nucleus sampling threshold |
| `--stream` | boolean | Stream tokens, default on in TTY |
| `--tool <json-or-path>` | string, repeatable | Tool definition JSON or file path |

```bash
mmx text chat --message "user:What is MiniMax?" --output json --quiet
mmx text chat --model MiniMax-M2.7-highspeed --message "user:Say hi" --output json --quiet
cat conversation.json | mmx text chat --messages-file - --output json --quiet
```

**stdout:** response text in text mode, or full response object in JSON mode.

---

### image generate

Generate images. Model: `image-01`.

```bash
mmx image generate --prompt <text> [flags]
```

| Flag | Type | Description |
|---|---|---|
| `--prompt <text>` | string, **required** | Image description |
| `--aspect-ratio <ratio>` | string | e.g. `16:9`, `1:1`. Ignored if `--width` and `--height` are both set |
| `--n <count>` | number | Number of images, default 1 |
| `--seed <n>` | number | Random seed for reproducible generation |
| `--width <px>` / `--height <px>` | number | Pixel dimensions, 512-2048 and multiples of 8 |
| `--prompt-optimizer` | boolean | Optimize prompt before generation |
| `--aigc-watermark` | boolean | Embed AI-generated content watermark |
| `--subject-ref <params>` | string | Subject reference, e.g. `type=character,image=path-or-url` |
| `--response-format <format>` | string | `url` or `base64` |
| `--out-dir <dir>` | string | Download images to directory |
| `--out-prefix <prefix>` | string | Filename prefix |

```bash
mmx image generate --prompt "A cat in a spacesuit" --output json --quiet
mmx image generate --prompt "Logo" --n 3 --out-dir ./gen/ --quiet
```

---

### video generate

Generate video. Default model: `MiniMax-Hailuo-2.3`. This is async by nature; by default the CLI polls until completion.

```bash
mmx video generate --prompt <text> [flags]
```

| Flag | Type | Description |
|---|---|---|
| `--prompt <text>` | string, **required** | Video description |
| `--model <model>` | string | `MiniMax-Hailuo-2.3` or `MiniMax-Hailuo-2.3-Fast` |
| `--first-frame <path-or-url>` | string | First-frame image |
| `--callback-url <url>` | string | Webhook URL for completion |
| `--download <path>` | string | Save video to file |
| `--async` / `--no-wait` | boolean | Return task ID immediately |
| `--poll-interval <seconds>` | number | Polling interval, default 5 |

```bash
mmx video generate --prompt "A robot painting" --async --output json --quiet
mmx video task get --task-id 123456 --output json --quiet
mmx video download --file-id 176844028768320 --out video.mp4 --quiet
```

For long video jobs, prefer `--async`, save the task ID, and poll later instead of blocking a Hermes turn.

---

### speech synthesize

Text-to-speech. Default model: `speech-2.8-hd`.

```bash
mmx speech synthesize --text <text> [flags]
```

| Flag | Type | Description |
|---|---|---|
| `--text <text>` | string | Text to synthesize |
| `--text-file <path>` | string | Read text from file; use `-` for stdin |
| `--model <model>` | string | `speech-2.8-hd`, `speech-2.6`, `speech-02` |
| `--voice <id>` | string | Voice ID, default `English_expressive_narrator` |
| `--speed <n>` | number | Speech speed |
| `--stream` | boolean | Stream audio to stdout |
| `--out <path>` | string | Output audio file |

```bash
mmx speech voices --output json --quiet
mmx speech synthesize --text "Hello!" --voice English_expressive_narrator --out hello.mp3 --quiet
```

---

### music generate / cover

```bash
# Generate with lyrics
mmx music generate --prompt "Upbeat pop" --lyrics "[verse] La da dee, sunny day" --out song.mp3 --quiet

# Auto-generate lyrics from prompt
mmx music generate --prompt "Indie folk, melancholic, rainy night" --lyrics-optimizer --out song.mp3 --quiet

# Instrumental
mmx music generate --prompt "lofi synthwave instrumental" --instrumental --out beat.mp3 --quiet

# Cover from reference audio
mmx music cover --audio ref.wav --prompt "Jazz trio" --out cover.mp3 --quiet
```

---

### vision, search, quota, files

```bash
# Image understanding
mmx vision describe photo.jpg --prompt "Describe the scene" --output json --quiet
mmx vision photo.jpg --output json --quiet

# Web search powered by MiniMax
mmx search "MiniMax AI latest news" --output json --quiet

# Quota / token plan
mmx quota --output json --quiet

# File upload/list/delete for APIs that require file IDs
mmx file upload input.png --output json --quiet
mmx file list --output json --quiet
mmx file delete --file-id <id> --yes --quiet
```

---

## Task routing

- Use Hermes native `image_generate` when the user only needs a quick image and the configured image backend is sufficient.
- Use Hermes native `text_to_speech` when the configured TTS provider is sufficient.
- Use `mmx` when the user specifically asks for MiniMax, needs MiniMax video/music/search/vision/quota/file operations, or needs exact MiniMax model selection.
- For persistent always-on tools inside Hermes, use the MiniMax MCP presets documented in the MiniMax OAuth guide instead of shelling out repeatedly.

## Common pitfalls

1. **Interactive prompts in a noninteractive Hermes turn.** Add `--non-interactive --quiet --output json` whenever possible.
2. **Long video/music jobs blocking the session.** Use `--async`, save task IDs, and poll.
3. **Secrets in command history or commits.** Prefer env vars or `mmx auth login`; never write keys into repo files.
4. **Region/key mismatch.** Global uses `api.minimax.io`; China uses `api.minimaxi.com`. Use `--region` if auto-detect fails.
5. **Assuming Hermes OAuth automatically logs in mmx.** The official CLI has its own auth store under `~/.mmx/`; run `mmx auth login` unless using an explicit API key for one call.

## Verification checklist

- [ ] `mmx --version` works and Node.js is 18+
- [ ] `mmx auth status` reports authenticated, or the command receives an API key via env/flag
- [ ] `mmx quota --output json --quiet` succeeds before costful generation
- [ ] Generation commands use `--quiet` and either `--output json` or explicit `--out`/`--download`
- [ ] Final response includes saved output paths or task IDs
