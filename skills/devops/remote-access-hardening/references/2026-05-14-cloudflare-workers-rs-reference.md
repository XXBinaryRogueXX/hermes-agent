# Cloudflare workers-rs — Reference Note

**Repo:** https://github.com/cloudflare/workers-rs
**Stars:** ~3,474 | **Language:** Rust | **Forks:** 405

## What is it

Write Cloudflare Workers in 100% Rust via WebAssembly. The canonical Rust SDK for Cloudflare Workers runtime, built on `wasm-bindgen` and `worker-sys`.

## Key Crates

- `worker` — the main crate, provides `fetch()`, `Schedule`, `Queue` traits
- `worker-sys` — raw bindings to the Workers runtime (V8 isolates)
- `serde-wasm-bindgen` — serialize/deserialize between Rust and JS

## Runtime Model

Workers run in a **V8 isolate** (like browser JS) — no OS access, no native syscalls. Rust compiles to WASM and runs in the same environment as JS Workers.

## Usage Pattern

```rust
use worker::*;

#[worker::fetch]
fn fetch(req: Request, _env: Env, _ctx: Context) -> Result<Response> {
    console_log!("Request: {:?}", req.url());
    Response::ok("Hello from Rust!")
}
```

## Relevance to Hermes

1. **Future deployment target** — If Hermes ever targets Cloudflare Workers as a serverless platform (similar to how Daytona/Modal provide serverless containers), `workers-rs` shows the Rust + WASM path. Not immediately relevant but worth monitoring.

2. **Rust terminal backend** — Hermes currently uses Python subprocess for terminal backends. If a Rust native terminal backend were ever needed (for performance), `workers-rs` shows the WASM worker model pattern.

3. **Edge computing pattern** — Cloudflare Workers are the reference implementation for "run anything at the edge with near-zero cold start." This is directly relevant to the serverless container strategy Hermes uses with Daytona/Modal.

## Status

Active, recently updated (pushed today). The `workers` crate uses the `worker::fetch` proc macro and `Env`/`Context` dependency injection pattern similar to how some DI frameworks work.

## Links
- Repo: https://github.com/cloudflare/workers-rs
- Docs: https://developers.cloudflare.com/workers/languages/rust/