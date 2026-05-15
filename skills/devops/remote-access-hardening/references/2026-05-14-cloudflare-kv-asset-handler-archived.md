# Cloudflare kv-asset-handler — Archived

**Repo:** https://github.com/cloudflare/kv-asset-handler
**Stars:** ~259 | **Language:** TypeScript | **Forks:** 47

## Status: Archived

This repository has been **archived** and `@cloudflare/kv-asset-handler` has moved to [`cloudflare/workers-sdk`](https://github.com/cloudflare/workers-sdk).

## What it was

TypeScript library for routing requests to Cloudflare KV assets. Provided caching headers, default document routing, and asset serving from Workers KV (Cloudflare's edge key-value storage).

## Relevance to Hermes

Not directly applicable — Hermes doesn't use Cloudflare KV. However, the pattern (routing + caching + asset serving from edge KV) could inform:
- Future blob storage integrations (R2 object storage, S3-compatible)
- If Hermes ever needed edge caching for cron output or session artifacts

## Action

Do not link to this repo directly. Use `cloudflare/workers-sdk` for KV asset handler functionality going forward.