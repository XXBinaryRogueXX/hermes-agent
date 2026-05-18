# Cloudflare Workers Python SDK — Reference Note

**Repo:** https://github.com/cloudflare/workers-py
**Stars:** ~79 | **Language:** Python | **Forks:** 12

## What is workers-py

A monorepo for writing Cloudflare Workers in 100% Python via Pyodide. Ships:
- `packages/cli/` — workers-py CLI toolchain
- `packages/runtime-sdk/` — Python SDK for Cloudflare Workers runtime

## Architecture

Uses **Pyodide** (Python compiled to WebAssembly) to run Python in Cloudflare's V8 isolate runtime. This is the canonical way to run Python on Cloudflare Workers — no native code, pure WASM.

## Key Files
- `packages/cli/` — worker template CLI
- `packages/runtime-sdk/` — `fetch()`, `Request`, `Response` bindings matching the Workers runtime API

## Relevance to Hermes

If Hermes ever officially supports **Cloudflare Workers as a deployment target** (alternative to Daytona/Modal serverless), this is the SDK to integrate with. The runtime-sdk shows the pattern for mapping Python to Workers' `fetch()` handler model.

## Status

Active development. Python 3.12+ required, uses `uv` for package management. Each package is independently released with semantic versioning.

## Links
- Main repo: https://github.com/cloudflare/workers-py
- Runtime SDK: `packages/runtime-sdk/`
- CLI tool: `packages/cli/`