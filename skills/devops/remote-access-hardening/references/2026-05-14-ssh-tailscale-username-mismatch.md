# SSH via Tailscale — username mismatch on projects node
**Date:** 2026-05-14
**Symptom:** `Permission denied (publickey,password)` connecting to `100.85.214.83` via Tailscale

## Root cause
Target node `projects` has local user `milk`, but the SSH client was using `luciusmilko` (the user's Microsoft/email identity, which does not exist on that machine).

## Diagnosis performed
```bash
# On projects node — confirmed no luciusmilko user exists:
getent passwd luciusmilko  # empty
ls -la /home/             # only /home/milk exists

# Self-SSH with correct username worked immediately:
ssh milk@100.85.214.83    # succeeded
```

## Fix
Use the local username that exists on the target machine. On `projects`, the only user is `milk`:

```bash
ssh milk@100.85.214.83
ssh milk@projects.tail1f0eae.ts.net
```

## Key lesson
Tailscale SSH authenticates against the **target node's local OS user database**, not against the Tailscale identity/email. The Tailscale identity (`luciusmilko@outlook.com`) only governs Tailscale-level permissions (who can connect to the tailnet), not OS-level login. After Tailscale auth, SSH still needs a valid local username and the corresponding `authorized_keys` entry.

When troubleshooting this error, always check `getent passwd <attempted-username>` and `ls /home/` on the target before investigating keys or firewall rules.