#!/usr/bin/env bash
set -euo pipefail

repo_url="https://github.com/MiniMax-AI/MiniMax-Provider-Verifier.git"
repo_dir="${MINIMAX_PROVIDER_VERIFIER_DIR:-${HOME}/.cache/hermes/minimax-provider-verifier}"
model="${MINIMAX_VERIFY_MODEL:-MiniMax-M2.7}"
base_url="${MINIMAX_VERIFY_BASE_URL:-https://api.minimax.io/v1}"
concurrency="${MINIMAX_VERIFY_CONCURRENCY:-5}"
output="${MINIMAX_VERIFY_OUTPUT:-results.jsonl}"
summary="${MINIMAX_VERIFY_SUMMARY:-summary.json}"
sample=""
extra_args=()

usage() {
  cat <<'EOF'
Usage: scripts/minimax-provider-verify.sh --sample sample.jsonl [options]

Options:
  --sample PATH        JSONL request test set (required)
  --model NAME        Model name (default: MiniMax-M2.7)
  --base-url URL      OpenAI-compatible base URL (default: https://api.minimax.io/v1)
  --concurrency N     Concurrent requests (default: 5)
  --output PATH       Detailed JSONL output (default: results.jsonl)
  --summary PATH      Summary JSON output (default: summary.json)
  --repo-dir PATH     Cache/checkout dir (default: ~/.cache/hermes/minimax-provider-verifier)
  --                 Pass remaining args through to verify.py

Auth: set MINIMAX_API_KEY or OPENAI_API_KEY in the environment. The script maps
MINIMAX_API_KEY to OPENAI_API_KEY for the verifier process without printing it.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --sample) sample="${2:?--sample requires a path}"; shift 2 ;;
    --model) model="${2:?--model requires a value}"; shift 2 ;;
    --base-url) base_url="${2:?--base-url requires a value}"; shift 2 ;;
    --concurrency) concurrency="${2:?--concurrency requires a value}"; shift 2 ;;
    --output) output="${2:?--output requires a path}"; shift 2 ;;
    --summary) summary="${2:?--summary requires a path}"; shift 2 ;;
    --repo-dir) repo_dir="${2:?--repo-dir requires a path}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; extra_args+=("$@"); break ;;
    *) extra_args+=("$1"); shift ;;
  esac
done

if [[ -z "$sample" ]]; then
  usage >&2
  exit 2
fi
if [[ ! -f "$sample" ]]; then
  echo "Sample JSONL not found: $sample" >&2
  exit 2
fi
if [[ -z "${OPENAI_API_KEY:-}" && -n "${MINIMAX_API_KEY:-}" ]]; then
  export OPENAI_API_KEY="$MINIMAX_API_KEY"
fi
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "Set MINIMAX_API_KEY or OPENAI_API_KEY in the environment before running." >&2
  exit 2
fi
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required to run the verifier environment." >&2
  exit 127
fi
if ! command -v git >/dev/null 2>&1; then
  echo "git is required to fetch MiniMax-Provider-Verifier." >&2
  exit 127
fi

mkdir -p "$(dirname "$repo_dir")"
if [[ ! -d "$repo_dir/.git" ]]; then
  git clone --depth 1 "$repo_url" "$repo_dir"
else
  git -C "$repo_dir" pull --ff-only --quiet
fi

exec uv run --python 3.12 --project "$repo_dir" python "$repo_dir/verify.py" "$sample" \
  --model "$model" \
  --base-url "$base_url" \
  --concurrency "$concurrency" \
  --output "$output" \
  --summary "$summary" \
  "${extra_args[@]}"
