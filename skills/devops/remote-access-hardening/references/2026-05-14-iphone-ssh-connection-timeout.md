# iOS Tailscale SSH timeout — milk bot screenshot
**Date:** 2026-05-14
**Symptom:** iPhone app shows "Connection could not be established" → "connection timed out" to `100.85.214.83:22`

## Visual diagnosis from milk bot screenshot

Mobile app (dark mode, bottom nav with Vaults/Connections/Profile) modal showed:

1. 👤 "Starting a new connection to: '100.85.214.83' port '22'"
2. ⚙️ "Connecting to '100.85.214.83' port '22'"
3. 😨 "Connection failed: connection timed out"

Meanwhile `tailscale status` on projects node showed:

```
100.85.214.83   projects     Luciusmilko@  linux  -
100.104.179.56  iphone17     Luciusmilko@  iOS    offline, last seen 3h ago
```

## Root cause

The iPhone's Tailscale client was **offline** — not maintaining a live tailnet session. The projects node and Tailscale infrastructure were fully functional. The connection timed out because the phone wasn't on the tailnet at all.

The iOS app (milk bot running on the phone) attempted direct SSH to `100.85.214.83:22` over Tailscale, but since the phone wasn't connected to Tailscale, the connection never reached the tailnet — timeout.

## Key lesson

Tailscale SSH from a mobile client requires the **Tailscale app to be open and connected** on that device. If the app is killed, background data is restricted, or the device is in low-power mode, Tailscale may appear "offline" in `tailscale status` and all tailnet traffic (including SSH) will fail from that device.

When self-SSH from the server works but a mobile client times out:
1. `tailscale status` on server — check if the mobile node is listed as **offline**
2. On the mobile device, open the Tailscale app and confirm it shows "Connected"
3. Toggle Tailscale off/on on the mobile device if it doesn't reconnect
4. Check Tailscale version on mobile — outdated clients may have bugs preventing reconnection