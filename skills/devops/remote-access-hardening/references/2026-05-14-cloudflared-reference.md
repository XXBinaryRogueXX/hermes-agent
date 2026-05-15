# cloudflared (Cloudflare Tunnel) — Reference Note

**Repo:** https://github.com/cloudflare/cloudflared
**Stars:** ~14.2k | **Language:** Go | **Forks:** 1,288

## What is it

Cloudflare Tunnel client — a tunneling daemon that proxies traffic from the Cloudflare network to your origins. Instead of opening inbound ports on your server, `cloudflared` connects **outbound** to Cloudflare's edge, creating a secure tunnel.

## Key Concept

```
User → Cloudflare Edge → cloudflared tunnel → Your Server
```

Unlike Tailscale (which creates a VPN mesh between nodes), cloudflared is a **single-direction tunnel**: your server reaches out to Cloudflare, and traffic flows back through it. No inbound firewall holes needed on the server.

## cloudflared vs Tailscale

| | cloudflared | Tailscale |
|--|-------------|-----------|
| Model | Outbound tunnel to Cloudflare edge | WireGuard VPN mesh between machines |
| Setup | Single daemon connects server to Cloudflare | Each node joins a tailnet |
| DNS | `*.trycloudflare.com` subdomain | MagicDNS (`name.tail-scale.ts.net`) |
| Auth | Cloudflare account / team | Tailscale auth (Google, GitHub, etc.) |
| Use case | Expose local service to the internet through Cloudflare | Private mesh between trusted devices |
| Dependencies | Cloudflare account | Tailscale account |
| installed? | `/usr/bin/cloudflared` (version 2026.3.0) | `tailscale` |

## Relevance to Hermes — remote-access-hardening skill

`cloudflared` is an **alternative to Tailscale** for the `remote-access-hardening` skill. Use it when:
- The user has a Cloudflare account but not a Tailscale account
- The user prefers Cloudflare's authentication and DNS over Tailscale's
- The user wants to expose services through Cloudflare's CDN/warp infrastructure

## Setup

```bash
# Install (already on system at /usr/bin/cloudflared)
cloudflared --version  # confirm

# Authenticate (opens browser)
cloudflared tunnel login

# Create a tunnel
cloudflared tunnel create my-tunnel

# Run the tunnel (proxies traffic from Cloudflare edge to local port 22)
cloudflared tunnel run --token <TOKEN>
```

## Quick SSH over cloudflared

```bash
# On the server
cloudflared access ssh --hostname localhost:22
# This creates a secure SSH endpoint at: ssh.homebrew-username.trycloudflare.com
```

## When to prefer cloudflared over Tailscale for SSH

- User already uses Cloudflare (Wave, Pages, R2, etc.)
- User wants a persistent `trycloudflare.com` hostname without managing keys
- User doesn't want to manage another identity provider (Tailscale auth)
- For temporary/quick access without installing Tailscale on all devices

## When to prefer Tailscale

- True zero-trust network between machines (not just port forwarding)
- Mesh VPN — every machine can talk to every other machine directly
- MagicDNS for easy hostname resolution
- More mature SSH integration (`tailscale ssh`)