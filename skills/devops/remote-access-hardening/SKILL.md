---
name: remote-access-hardening
description: Harden and repair Linux remote access with OpenSSH, UFW, Tailscale, and local LAN access without locking the user out.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [ssh, tailscale, ufw, firewall, remote-access, linux, hardening]
---

# Remote Access Hardening

Use this skill when the user asks to fix SSH access, install/configure Tailscale, restrict firewall exposure, close public ports, or harden a Linux workstation/server's remote access.

Reference cases:
- `references/2026-05-13-projects-ssh-tailscale.md` — initial Projects-host repair/hardening flow
- `references/2026-05-14-ssh-tailscale-username-mismatch.md` — Tailscale SSH auth failure: local username vs Tailscale identity mismatch on projects node
- `references/2026-05-14-iphone-ssh-connection-timeout.md` — mobile Tailscale client offline causing connection timeout on iOS app (milk bot screenshot)

Cloudflare tunnel alternative:
- `references/2026-05-14-cloudflared-reference.md` — cloudflared (Cloudflare Tunnel) as alternative to Tailscale for remote access
- `references/2026-05-14-cloudflare-pingora-reference.md` — Pingora (Rust network proxy framework) architecture notes
- `references/2026-05-14-cloudflare-workers-py-reference.md` — workers-py (Python on Cloudflare Workers via Pyodide)
- `references/2026-05-14-cloudflare-workers-rs-reference.md` — workers-rs (Rust + WASM on Cloudflare Workers)
- `references/2026-05-14-cloudflare-workers-oauth-provider-reference.md` — OAuth 2.1 + PKCE provider pattern
- `references/2026-05-14-cloudflare-kv-asset-handler-archived.md` — archived, points to workers-sdk

Core principle: **avoid lockout first, harden second**. Do not disable password auth, delete broad SSH firewall rules, or bind SSH only to a VPN interface until at least one replacement path is verified.

## 1. Diagnose before changing anything

Collect the live state without exposing secrets:

```bash
hostname
date -Is

# SSH service and listeners
systemctl is-enabled ssh 2>/dev/null || true
systemctl is-active ssh 2>/dev/null || true
systemctl --no-pager --full status ssh 2>/dev/null | sed -n '1,18p' || true
ss -tlnp 2>/dev/null | awk 'NR==1 || /:22 /' || true

# Addresses and routing
ip -br addr show scope global || true
ip route get 1.1.1.1 2>/dev/null || true

# Tailscale, if present
command -v tailscale >/dev/null && { tailscale version || true; tailscale status 2>&1 || true; } || echo 'tailscale not installed'

# Firewall
sudo -n ufw status numbered 2>/dev/null || ufw status numbered 2>/dev/null || true

# Effective SSH config
(sudo -n sshd -T 2>/dev/null || sshd -T 2>/dev/null || true) \
  | grep -Ei '^(port|listenaddress|passwordauthentication|pubkeyauthentication|permitrootlogin|authorizedkeysfile|allowusers|denyusers|allowgroups|denygroups|usepam|kbdinteractiveauthentication) ' || true

# Authorized keys summary only
if [ -f "$HOME/.ssh/authorized_keys" ]; then
  stat -c '%a %U:%G %n' "$HOME/.ssh" "$HOME/.ssh/authorized_keys"
  wc -l "$HOME/.ssh/authorized_keys"
  sed -n '1,5p' "$HOME/.ssh/authorized_keys" | sed -E 's/^((ssh-[a-z0-9]+|ecdsa-[^ ]+) [^ ]{12}).*$/\1...[REDACTED_KEY]/'
else
  echo 'missing authorized_keys'
fi
```

Verify the local target that the user can try:

```bash
# Replace with detected LAN IP(s)
for host in 127.0.0.1 192.168.1.10; do
  if timeout 3 bash -c "</dev/tcp/$host/22" 2>/dev/null; then
    echo "tcp $host:22 OK"
  else
    echo "tcp $host:22 FAIL"
  fi
done
```

If the user reports `host is unreachable`, treat it as a routing/L2 reachability problem, not an SSH auth problem. Identify the actual LAN and the client that worked before:

```bash
# LAN IP/range and gateway for the server.
ip -4 -br addr show scope global
ip route show default
ip route get 1.1.1.1 2>/dev/null || true

# Source IPs that successfully logged in recently.
journalctl -u ssh --since '48 hours ago' --no-pager 2>/dev/null \
  | grep -E 'Accepted (password|publickey)' \
  | sed -E 's/.*Accepted (password|publickey) for ([^ ]+) from ([0-9a-fA-F:.]+) port.*/\1 user=\2 from=\3/' \
  | sort | uniq -c

# Can the server still see/ping that client?
ping -c 2 -W 1 <last-successful-client-ip> || true
ip neigh show <last-successful-client-ip> || true
```

Then tell the user the exact LAN CIDR and that their SSH client must be on that subnet or on Tailscale. Example: server `172.16.0.30/24` means the local LAN is `172.16.0.0/24`; a client on cellular, guest Wi-Fi, another VLAN, or a different subnet will get `host unreachable` before SSH is involved.

## 2. Install Tailscale safely on Ubuntu/Debian

Prefer the official package repository over ad-hoc binaries. For Ubuntu:

```bash
. /etc/os-release
CODENAME="${VERSION_CODENAME:-noble}"

curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${CODENAME}.noarmor.gpg" -o /tmp/tailscale-archive-keyring.gpg
curl -fsSL "https://pkgs.tailscale.com/stable/ubuntu/${CODENAME}.tailscale-keyring.list" -o /tmp/tailscale.list
sudo install -m 0644 /tmp/tailscale-archive-keyring.gpg /usr/share/keyrings/tailscale-archive-keyring.gpg
sudo install -m 0644 /tmp/tailscale.list /etc/apt/sources.list.d/tailscale.list
sudo apt-get update
sudo apt-get install -y tailscale
sudo systemctl enable --now tailscaled
```

Start login/configuration:

```bash
# Choose a stable hostname users can recognize in their tailnet.
sudo tailscale up --ssh --hostname=projects
```

If the command prints an auth URL and times out, that is still useful: send the URL to the user. Verify status:

```bash
tailscale status 2>&1 || true
tailscale ip -4 2>/dev/null || true
tailscale debug prefs 2>/dev/null | sed -n '1,80p' || true
systemctl is-active tailscaled
```

Expected pre-auth state may be `Logged out` / `Needs login` with an auth URL. Do not call that a failure; the user must authenticate to join their tailnet unless an auth key was provided.

## 3. UFW hardening sequence

Before removing broad SSH access, add the replacement allow rules first.

For a workstation on a local LAN plus Tailscale:

```bash
# Allow SSH over Tailscale when tailscale0 exists/appears.
sudo ufw allow in on tailscale0 to any port 22 proto tcp comment 'SSH over Tailscale'

# Allow SSH from the detected local subnet. Replace with the real subnet from `ip -br addr`.
sudo ufw allow from 172.16.0.0/24 to any port 22 proto tcp comment 'SSH from local LAN'

sudo ufw status numbered
```

Only after the replacement rules are present, remove broad public SSH if the user wants LAN/Tailscale-only access:

```bash
yes | sudo ufw delete allow 22/tcp || true
sudo ufw status numbered
```

Close public web ports when nothing is listening and the user does not intend to serve web traffic:

```bash
ss -tlnp 2>/dev/null | awk 'NR==1 || /:(80|443) /'
yes | sudo ufw delete allow 80/tcp || true
yes | sudo ufw delete allow 443/tcp || true
sudo ufw status numbered
```

## 4. SSH password-auth hardening

Do **not** disable `PasswordAuthentication` until the user confirms they can log in through at least one non-password path:

- SSH key works from the user's client, or
- Tailscale SSH works after tailnet authentication, or
- there is confirmed physical/console access for recovery.

Once confirmed, harden with a drop-in file instead of editing packaged defaults inline:

```bash
sudo install -d -m 0755 /etc/ssh/sshd_config.d
cat <<'EOF' | sudo tee /etc/ssh/sshd_config.d/99-hermes-hardening.conf >/dev/null
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
PermitRootLogin prohibit-password
EOF

sudo sshd -t
sudo systemctl reload ssh
sudo sshd -T | grep -Ei '^(passwordauthentication|kbdinteractiveauthentication|pubkeyauthentication|permitrootlogin) '
```

Keep an existing session open while testing a new login.

## 5. Final verification report

Report concise, actionable facts:

```bash
systemctl is-enabled ssh 2>/dev/null || true
systemctl is-active ssh 2>/dev/null || true
ss -tlnp 2>/dev/null | awk 'NR==1 || /:22 /'
ip -br addr show scope global || true
tailscale status 2>&1 || true
sudo ufw status numbered
ss -tlnp 2>/dev/null | awk 'NR==1 || /:(80|443) /'
```

**Self-SSH test** (run from the server itself before asking the user to try from their client):

```bash
# Replace <user> and <tailscale-ip> with the actual user and the server's Tailscale IP.
# This confirms SSH over Tailscale is functional on the server side.
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 <user>@<tailscale-ip> echo "SSH works"
```

If self-SSH succeeds but the user's client still fails, the issue is on the **client side** — not the server. Check:
- Client's SSH service is running (`sudo systemsetup -f -setremotelogin on` on macOS, or `sudo systemctl enable --now sshd` on Linux)
- Client's firewall is not blocking outgoing SSH
- Client is actually on Tailscale (not on a split-HNS/vpn that routes differently)

Tell the user exactly what to try next, for example:

```bash
ssh <user>@<LAN-IP>
# after Tailscale auth:
ssh <user>@<tailscale-ip-or-magicdns-name>
```

## Pitfalls

- **Username mismatch is the most common SSH auth failure.** A Tailscale node may have a local user (e.g., `milk`) that differs from the user's email/SSO identity (e.g., `luciusmilko`). The SSH server only knows local OS users. Always verify the target machine's local usernames with `getent passwd` or `ls /home/` before diagnosing keys or firewall rules. In this session: `ssh luciusmilko@100.85.214.83` failed with `Permission denied (publickey,password)`; `ssh milk@100.85.214.83` succeeded immediately.
- **Mobile Tailscale client offline is a common cause of apparent SSH failure.** When self-SSH from the server works but a mobile client times out, the device's Tailscale app is likely disconnected or stale. Check `tailscale status` on the server — if the mobile node shows `offline, last seen Xh ago`, the device is not on the tailnet. The fix is on the device: open the Tailscale app, confirm "Connected", toggle off/on, update if outdated. SSH and the server are fine.
- **When Telegram image uploads fail in Hermes** (gateway returns "no image attached" despite a valid JPEG file in the cache), fall back to `mcp_minimax_understand_image` with the cached file path from `/home/milk/.hermes/cache/images/<hash>.jpg` instead of relying on the gateway's image parsing pipeline.

## Mobile client SSH failure pattern

When self-SSH from the server works but a mobile client (iOS/Android) times out with "connection timed out":

1. Run `tailscale status` on the server — if the mobile node shows **offline** or **last seen N hours ago**, the device is not on the tailnet
2. The problem is the mobile Tailscale app, not the server or SSH configuration
3. On the device: open Tailscale app → confirm "Connected" status → toggle off/on if needed → try again
4. Also check: background data restrictions, low-power mode, or outdated Tailscale version on the mobile device

**Note:** The milk bot iOS app attempted SSH over Tailscale to `100.85.214.83:22` and timed out because the phone's Tailscale was offline (last seen 3 hours earlier). The server was fully functional.

### Diagnosing "Permission denied (publickey,password)" on a known-good server

When `ssh <user>@<tailscale-ip>` fails with `Permission denied` even though:
- Tailscale is connected and the IP is correct
- `sshd` is running and port 22 is open
- The client's key is in `authorized_keys` on the server

The two most likely causes are:

**1. Wrong username.** Run on the server:
```bash
getent passwd           # list all local users
ls -la /home/           # check which home directories exist
```
Then try the correct local username:
```bash
ssh <correct-user>@<tailscale-ip>
```

**2. SSH not accepting the key.** Run on the server to confirm key presence:
```bash
cat ~/.ssh/authorized_keys    # for the target user
```
Then from the client, explicitly specify the identity file:
```bash
ssh -o IdentityFile=~/.ssh/id_ed25519 <user>@<tailscale-ip>
```
If key-based auth works with `-i` but not otherwise, check SSH agent forwarding and `~/.ssh/config` for hostname-specific overrides.

### Tailscale SSH "Access denied: checkprefs access denied"

When `tailscale set --ssh=true` fails with this error as a non-root user, the operator is not set. Fix in two steps:

```bash
sudo tailscale set --operator=$USER   # allow user to manage tailscaled without sudo
tailscale set --ssh=true              # now succeeds
```

The `tailscale status --self` output will still show the node without indicating SSH is enabled — check with `tailscale status` on another node or try an actual SSH connection.
