# Cloudflare Pingora — Reference Note

**Repo:** https://github.com/cloudflare/pingora
**Stars:** ~26.6k | **Language:** Rust | **Forks:** 1,642

## What is Pingora

Pingora is a Rust framework for building fast, reliable and programmable networked systems. It has been serving 40M+ Internet requests per second for years inside Cloudflare's production infrastructure.

## Architecture Highlights

### Core Crates
- `pingora` — public-facing crate for networked systems/proxies
- `pingora-core` — protocols, functionalities, traits
- `pingora-proxy` — HTTP proxy logic and APIs
- `pingora-error` — common error type
- `pingora-http` — HTTP header definitions
- `pingora-openssl`, `pingora-boringssl` — TLS extensions
- `pingora-ketama` — Ketama consistent hashing algorithm

### Key Features
- **Async Rust** — tokio-based, fast and memory-safe
- **HTTP 1/2 end-to-end proxy**
- **TLS** — OpenSSL, BoringSSL, s2n-tls, or rustls (experimental)
- **gRPC and WebSocket proxying**
- **Graceful reload** — zero-downtime config updates
- **Customizable load balancing and failover** — consistent hashing, health checks
- **Observability** — metrics, logging hooks

## Why It Matters for Hermes

Hermes currently uses standard Python async (`asyncio`) for its gateway and HTTP operations. If Hermes ever needed:
- **High-throughput proxy layer** (e.g., routing agent requests through a proxy)
- **Connection pooling** for outbound HTTP
- **gRPC transport** for internal agent communication
- **Rust-powered performance** for hot paths

...Pingora's architecture is the reference blueprint. The `pingora-proxy` crate in particular is a good reference for building programmable HTTP proxies in Rust.

## Relevance to Hermes

Not immediately applicable — Hermes is Python-first. But worth monitoring for:
- Future Rust-based terminal backends (replacing Python subprocess spawning)
- High-performance HTTP routing inside the gateway
- If Hermes ever needs a built-in reverse proxy / load balancer

## Quick Start (from their docs)

```bash
# Build a bare-bones load balancer
git clone https://github.com/cloudflare/pingora.git
cd pingora
cargo build --release
```

Their [user guide](https://github.com/cloudflare/pingora/blob/main/docs/user_guide/index.md) covers proxy configuration, graceful reload, and custom filter chains.