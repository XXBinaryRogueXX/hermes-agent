#!/usr/bin/env bash
set -euo pipefail

if ! command -v mmx >/dev/null 2>&1; then
  echo "mmx CLI not found. Install it with: npm install -g mmx-cli" >&2
  exit 127
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
use_temp_home=0

# mmx uses its own API-key auth and auto-persists env-provided keys into
# ~/.mmx/config.json. For Hermes-driven checks, bridge MiniMax OAuth into the
# mmx process and isolate HOME so no token is written to the operator's real
# mmx config. Existing mmx credentials are still used when no env key/OAuth
# bridge is available.
if [[ -n "${MINIMAX_API_KEY:-}" ]]; then
  use_temp_home=1
fi

if [[ -z "${MINIMAX_API_KEY:-}" ]]; then
  env_exports="$(${PYTHON:-python3} - "$repo_root" <<'PY'
import shlex
import sys

repo_root = sys.argv[1]
sys.path.insert(0, repo_root)
try:
    from hermes_cli.auth import resolve_minimax_oauth_runtime_credentials

    creds = resolve_minimax_oauth_runtime_credentials()
    token = str(creds.get("api_key") or creds.get("access_token") or "").strip()
    base_url = str(
        creds.get("api_host")
        or creds.get("base_url")
        or creds.get("inference_base_url")
        or "https://api.minimax.io"
    ).strip().rstrip("/")
    if base_url.endswith("/anthropic"):
        base_url = base_url[: -len("/anthropic")]
    if token:
        print("export MINIMAX_API_KEY=" + shlex.quote(token))
        print("export MINIMAX_BASE_URL=" + shlex.quote(base_url))
        print("export HERMES_MMX_BRIDGED_OAUTH=1")
except Exception:
    pass
PY
)"
  if [[ -n "$env_exports" ]]; then
    eval "$env_exports"
    use_temp_home=1
  fi
fi

run_mmx_quota() {
  mmx quota show --output json --quiet --non-interactive --no-color "$@" \
    2> >(grep -v '^API key saved to ' >&2)
}

if [[ "$use_temp_home" == "1" ]]; then
  tmp_home="$(mktemp -d)"
  trap 'rm -rf "$tmp_home"' EXIT
  mkdir -p "$tmp_home"
  HOME="$tmp_home" XDG_CONFIG_HOME="$tmp_home/.config" run_mmx_quota "$@"
else
  run_mmx_quota "$@"
fi
