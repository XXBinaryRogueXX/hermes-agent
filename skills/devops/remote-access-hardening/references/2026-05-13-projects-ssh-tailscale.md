# 2026-05-13 Projects Host SSH/Tailscale/UFW Case

Condensed reusable detail from a successful remote-access repair and hardening session.

## Situation

- User could not SSH locally like the previous night.
- Host had OpenSSH active and listening on `0.0.0.0:22` / `[::]:22`.
- LAN IP was `172.16.0.30/24` on `enp0s31f6`.
- `authorized_keys` existed with safe permissions, but `PasswordAuthentication yes` was still enabled.
- UFW was active and initially allowed public `22/tcp`, `80/tcp`, and `443/tcp`.
- Nothing was listening on `80` or `443`.
- Tailscale was not installed.

## Actions that worked

1. Verified SSH service, listeners, effective `sshd -T`, UFW rules, LAN IPs, routes, and authorized key summary.
2. Installed Tailscale using the official Ubuntu `noble` repository:
   - keyring: `https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg`
   - apt list: `https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list`
3. Enabled `tailscaled` and ran `sudo tailscale up --ssh --hostname=projects`.
4. The command printed a login URL and timed out; status showed `Logged out` / `Needs login`, which is expected until the user authenticates.
5. Added replacement SSH firewall allows before removing broad public SSH:
   - `sudo ufw allow in on tailscale0 to any port 22 proto tcp comment 'SSH over Tailscale'`
   - `sudo ufw allow from 172.16.0.0/24 to any port 22 proto tcp comment 'SSH from local LAN'`
6. Removed broad public SSH and unused web ports:
   - `yes | sudo ufw delete allow 22/tcp`
   - `yes | sudo ufw delete allow 80/tcp`
   - `yes | sudo ufw delete allow 443/tcp`
7. Verified local TCP connection to `127.0.0.1:22` and `172.16.0.30:22`.

## Final safe state

- SSH active and listening.
- Tailscale installed/running, pending user authentication.
- UFW permits SSH only from local LAN and `tailscale0`.
- Public `22/80/443` allows removed.
- Password auth intentionally left enabled until the user confirms LAN or Tailscale login works.

## Lesson

For SSH repair, provide the user a concrete LAN IP to test (`ssh user@LAN-IP`) and do not proceed to password-auth disabling until user confirms a working replacement access path.
