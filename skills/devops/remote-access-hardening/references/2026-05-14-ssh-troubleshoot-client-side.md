# SSH/Tailscale Session Notes — 2026-05-14

## What happened

User couldn't SSH from macbook (`100.72.130.14`) to projects server (`100.85.214.83`) over Tailscale.

## Diagnosis performed

- `tailscale status` showed both nodes active on Tailscale
- `tailscale ping macbook` returned pong in 70ms — Tailscale connectivity confirmed
- Self-SSH from server to itself succeeded: `ssh milk@100.85.214.83 echo "SSH works"` → worked
- `nc -zv macbook 22` → Connection refused from server side (expected — macOS blocks incoming SSH)
- `ssh milk@100.72.130.14` from server → Connection refused

## Root cause

macOS blocks incoming SSH by default (Remote Login in System Settings is OFF). The server-side SSH and Tailscale SSH were both correctly configured — the **client** (macbook) had its SSH service disabled.

## How to fix on macOS client

**Option 1 — System Settings (GUI):**
- System Settings → General → Sharing → Remote Login → Toggle ON
- Set "Allow full access" or limit to specific users

**Option 2 — Terminal:**
```bash
sudo systemsetup -f -setremotelogin on
```

## Key diagnostic pattern

When self-SSH from the server works but the user still can't connect:
→ The problem is on the **client side**, not the server.
→ Check: SSH service running on client? Firewall on client blocking outgoing port 22?

## Tailscale SSH operator fix

On the server, when `tailscale set --ssh=true` fails with:
```
Access denied: checkprefs access denied
Use 'sudo tailscale set --operator=$USER' once.
```

Fix:
```bash
sudo tailscale set --operator=milk   # allow non-root user to manage tailscaled
tailscale set --ssh=true             # now succeeds
```