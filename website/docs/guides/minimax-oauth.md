---
sidebar_position: 15
title: "MiniMax OAuth"
description: "Log into MiniMax via browser OAuth and use MiniMax-M2.7 models in Hermes Agent — no API key required"
---

# MiniMax OAuth

Hermes Agent supports **MiniMax** through a browser-based OAuth login flow, using the same credentials as the [MiniMax portal](https://www.minimax.io). No API key or credit card is required — log in once and Hermes automatically refreshes your session.

The transport reuses the `anthropic_messages` adapter (MiniMax exposes an Anthropic Messages-compatible endpoint at `/anthropic`), so all existing tool-calling, streaming, and context features work without any adapter changes.

## Overview

| Item | Value |
|------|-------|
| Provider ID | `minimax-oauth` |
| Display name | MiniMax (OAuth) |
| Auth type | Browser OAuth (PKCE device-code flow) |
| Transport | Anthropic Messages-compatible (`anthropic_messages`) |
| Models | `MiniMax-M2.7`, `MiniMax-M2.7-highspeed` |
| Global endpoint | `https://api.minimax.io/anthropic` |
| China endpoint | `https://api.minimaxi.com/anthropic` |
| Requires env var | No (`MINIMAX_API_KEY` is **not** used for this provider) |

## Prerequisites

- Python 3.9+
- Hermes Agent installed
- A MiniMax account at [minimax.io](https://www.minimax.io) (global) or [minimaxi.com](https://www.minimaxi.com) (China)
- A browser available on the local machine (or use `--no-browser` for remote sessions)

## Quick Start

```bash
# Launch the provider and model picker
hermes model
# → Select "MiniMax (OAuth)" from the provider list
# → Hermes opens your browser to the MiniMax authorization page
# → Approve access in the browser
# → Select a model (MiniMax-M2.7 or MiniMax-M2.7-highspeed)
# → Start chatting

hermes
```

After the first login, credentials are stored under `~/.hermes/auth.json` and are refreshed automatically before each session.

## Logging In Manually

You can trigger a login without going through the model picker:

```bash
hermes auth add minimax-oauth
```

### China region

If your account is on the China platform (`minimaxi.com`), use the China-region OAuth provider id `minimax-cn` instead, or skip OAuth and configure `MINIMAX_CN_API_KEY` / `MINIMAX_CN_BASE_URL` directly. The `--region cn` flag described in older docs is **not** wired through the CLI's argument parser; use the `minimax-cn` provider instead:

```bash
hermes auth add minimax-cn --type oauth   # if OAuth is supported on your CN account
# or simpler:
echo 'MINIMAX_CN_API_KEY=your-key' >> ~/.hermes/.env
```

### Remote / headless sessions

On servers or containers where no browser is available:

```bash
hermes auth add minimax-oauth --no-browser
```

Hermes will print the verification URL and user code — open the URL on any device and enter the code when prompted.

## The OAuth Flow

Hermes implements a PKCE device-code flow against the MiniMax OAuth endpoints:

1. Hermes generates a PKCE verifier / challenge pair and a random state value.
2. It POSTs to `{base_url}/oauth/code` with the challenge and receives a `user_code` and `verification_uri`.
3. Your browser opens `verification_uri`. If prompted, enter the `user_code`.
4. Hermes polls `{base_url}/oauth/token` until the token arrives (or the deadline passes).
5. Tokens (`access_token`, `refresh_token`, expiry) are saved to `~/.hermes/auth.json` under the `minimax-oauth` key.

Token refresh (standard OAuth `refresh_token` grant) runs automatically at each session start when the access token is within 60 seconds of expiry.

## Checking Login Status

```bash
hermes doctor
```

The `◆ Auth Providers` section will show:

```
✓ MiniMax OAuth  (logged in, region=global)
```

or, if not logged in:

```
⚠ MiniMax OAuth  (not logged in)
```

## Switching Models

```bash
hermes model
# → Select "MiniMax (OAuth)"
# → Pick from the model list
```

Or set the model directly:

```bash
hermes config set model MiniMax-M2.7
hermes config set provider minimax-oauth
```

## Configuration Reference

After login, `~/.hermes/config.yaml` will contain entries similar to:

```yaml
model:
  default: MiniMax-M2.7
  provider: minimax-oauth
  base_url: https://api.minimax.io/anthropic
```

### Region endpoints

| Provider id | Portal | Inference endpoint |
|-------------|--------|-------------------|
| `minimax-oauth` (global) | `https://api.minimax.io` | `https://api.minimax.io/anthropic` |
| `minimax-cn` (China) | `https://api.minimaxi.com` | `https://api.minimaxi.com/anthropic` |

### Provider aliases

All of the following resolve to `minimax-oauth`:

```bash
hermes --provider minimax-oauth    # canonical
hermes --provider minimax-portal   # alias
hermes --provider minimax-global   # alias
hermes --provider minimax_oauth    # alias (underscore form)
```

## Environment Variables

The `minimax-oauth` provider does **not** use `MINIMAX_API_KEY` or `MINIMAX_BASE_URL`. Those variables are for the API-key-based `minimax` and `minimax-cn` providers only.

| Variable | Effect |
|----------|--------|
| `MINIMAX_API_KEY` | Used by `minimax` provider only — ignored for `minimax-oauth` |
| `MINIMAX_CN_API_KEY` | Used by `minimax-cn` provider only — ignored for `minimax-oauth` |

To force the `minimax-oauth` provider at runtime:

```bash
HERMES_INFERENCE_PROVIDER=minimax-oauth hermes
```

## Models

| Model | Best for |
|-------|----------|
| `MiniMax-M2.7` | Long-context reasoning, complex tool-calling |
| `MiniMax-M2.7-highspeed` | Lower latency, lighter tasks, auxiliary calls |

Both models support up to 200,000 tokens of context.

`MiniMax-M2.7-highspeed` is also used automatically as the auxiliary model for vision and delegation tasks when `minimax-oauth` is the primary provider.

The API-key providers (`minimax` and `minimax-cn`) expose the same curated model picker entries, including `MiniMax-M2.7-highspeed`.

## Official MiniMax CLI (`mmx`)

Hermes ships an optional `mmx-cli` skill for MiniMax's official terminal CLI. Use it when you need MiniMax capabilities beyond Hermes' native provider adapter, especially video generation, music generation, voice design, MiniMax web search, vision describe, file upload/list/delete, or Token Plan quota checks.

```bash
# Install and authenticate the official CLI
npm install -g mmx-cli
mmx auth login

# Agent-friendly examples
mmx text chat --model MiniMax-M2.7-highspeed --message "user:Say hi" --output json --quiet
mmx video generate --prompt "Ocean waves at sunset" --async --output json --quiet
mmx music generate --prompt "lofi instrumental" --instrumental --out song.mp3 --quiet
mmx search "MiniMax AI latest news" --output json --quiet
mmx quota --output json --quiet
```

Install the optional skill with:

```bash
hermes skills install mmx-cli
```

:::note
The official `mmx` CLI keeps its own auth state under `~/.mmx/`. Hermes' `minimax-oauth` login does not automatically log in `mmx`; run `mmx auth login` for the CLI, or pass a MiniMax API key through environment variables for one-off calls. Do not copy OAuth access tokens into chat or committed files.
:::

## MiniMax MCP presets

Hermes' MCP CLI includes presets for the official MiniMax MCP servers.

### OAuth-backed presets, no persistent MiniMax API key

These wrap the official `uvx` MCP packages and export the short-lived Hermes `minimax-oauth` access token only to the child MCP process:

```bash
# Media generation tools: text_to_audio, list_voices, voice_clone,
# generate_video, query_video_generation, text_to_image, music_generation,
# voice_design.
hermes mcp add minimax-media --preset minimax-oauth

# Coding Plan search + vision tools: web_search, understand_image.
hermes mcp add minimax-coding --preset minimax-coding-plan-oauth
```

### API-key presets

If you prefer API-key auth, set the key in `~/.hermes/.env` and use the direct presets:

```bash
# Edit ~/.hermes/.env or use your preferred secret manager to set:
# MINIMAX_API_KEY=<your-key>
# MINIMAX_API_HOST=https://api.minimax.io

hermes mcp add minimax-media --preset minimax
hermes mcp add minimax-coding --preset minimax-coding-plan
```

For China-region keys, use `https://api.minimaxi.com` as `MINIMAX_API_HOST`. Restart or start a new Hermes session after adding MCP servers so their tools are discovered.

:::warning Cost-bearing tools
MiniMax MCP media tools can spend Token Plan quota. Use `mmx quota` or MiniMax's Token Plan dashboard before running large image, video, speech, or music jobs.
:::

## Provider smoke verifier

Hermes includes a lightweight smoke verifier inspired by MiniMax-AI's Provider Verifier. It checks reachability, non-empty content, tool-call triggering/schema accuracy, language following, and tool argument property order for official or third-party MiniMax endpoints.

```bash
# Default: use Hermes minimax-oauth credentials
python scripts/minimax_provider_smoke.py --provider minimax-oauth --json

# API-key provider
MINIMAX_API_KEY=sk-... python scripts/minimax_provider_smoke.py --provider minimax --model MiniMax-M2.7

# Third-party Anthropic-compatible MiniMax gateway
MINIMAX_GATEWAY_KEY=... python scripts/minimax_provider_smoke.py \
  --provider custom-minimax \
  --base-url https://gateway.example.com/anthropic \
  --api-key-env MINIMAX_GATEWAY_KEY \
  --model MiniMax-M2.7
```

The script redacts keys in output and exits non-zero when critical checks fail.

## Troubleshooting

### Token expired — not re-logging in automatically

Hermes refreshes the token on every session start if it is within 60 seconds of expiry. If the access token is already expired (for example, after a long offline period), the refresh happens automatically on the next request. If refresh fails with `refresh_token_reused` or `invalid_grant`, Hermes marks the session as requiring re-login.

**Fix:** run `hermes auth add minimax-oauth` again to start a fresh login.

### Authorization timed out

The device-code flow has a finite expiry window. If you don't approve the login in time, Hermes raises a timeout error.

**Fix:** re-run `hermes auth add minimax-oauth` (or `hermes model`). The flow starts fresh.

### State mismatch (possible CSRF)

Hermes detected that the `state` value returned by the authorization server does not match what it sent.

**Fix:** re-run the login. If it persists, check for a proxy or redirect that is modifying the OAuth response.

### Logging in from a remote server

If `hermes` cannot open a browser window, use `--no-browser`:

```bash
hermes auth add minimax-oauth --no-browser
```

Hermes prints the URL and code. Open the URL on any device and complete the flow there.

### "Not logged into MiniMax OAuth" error at runtime

The auth store has no credentials for `minimax-oauth`. You have not logged in yet, or the credential file was deleted.

**Fix:** run `hermes model` and select MiniMax (OAuth), or run `hermes auth add minimax-oauth`.

## Logging Out

To remove stored MiniMax OAuth credentials:

```bash
hermes auth remove minimax-oauth
```

## See Also

- [AI Providers reference](../integrations/providers.md)
- [Environment Variables](../reference/environment-variables.md)
- [Configuration](../user-guide/configuration.md)
- [hermes doctor](../reference/cli-commands.md)
