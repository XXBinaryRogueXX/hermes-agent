"""Run official MiniMax MCP servers with Hermes MiniMax OAuth credentials.

The official MiniMax MCP packages expect a ``MINIMAX_API_KEY`` environment
variable. Hermes' ``minimax-oauth`` provider stores a refreshable OAuth access
token in ``~/.hermes/auth.json`` instead. This small stdio wrapper resolves the
short-lived OAuth token at process start, exports it only to the child process,
and then execs ``uvx <package> ...``.

No MiniMax API key is persisted by this module.
"""

from __future__ import annotations

import os
import sys
from typing import MutableMapping, Sequence


DEFAULT_PACKAGE = "minimax-mcp"
DEFAULT_HOST = "https://api.minimax.io"


def host_from_anthropic_base_url(base_url: str | None) -> str:
    """Return the MiniMax API host for a Hermes Anthropic-compatible base URL."""
    if not base_url:
        return DEFAULT_HOST
    host = str(base_url).rstrip("/")
    for suffix in ("/anthropic/v1/messages", "/anthropic/v1", "/anthropic", "/v1/messages"):
        if host.endswith(suffix):
            host = host[: -len(suffix)]
            break
    return host or DEFAULT_HOST


def populate_minimax_env(env: MutableMapping[str, str] | None = None) -> MutableMapping[str, str]:
    """Populate MiniMax MCP env vars, preferring existing API-key config.

    If ``MINIMAX_API_KEY`` is already present, the caller explicitly configured
    API-key auth and we leave it untouched. Otherwise, resolve Hermes
    ``minimax-oauth`` credentials and export the access token in-memory under the
    env var name expected by MiniMax's MCP servers.
    """
    env = os.environ if env is None else env
    if env.get("MINIMAX_API_KEY"):
        env.setdefault("MINIMAX_API_HOST", DEFAULT_HOST)
        return env

    try:
        from hermes_cli.auth import resolve_minimax_oauth_runtime_credentials

        creds = resolve_minimax_oauth_runtime_credentials()
    except Exception as exc:  # pragma: no cover - exact AuthError type varies in installs
        raise SystemExit(
            "MiniMax OAuth credentials are unavailable. Run `hermes model` and "
            "select MiniMax (OAuth), or set MINIMAX_API_KEY for API-key MCP auth."
        ) from exc

    token = creds.get("api_key")
    if not token:
        raise SystemExit("MiniMax OAuth resolver returned no access token.")

    env["MINIMAX_API_KEY"] = str(token)
    env.setdefault(
        "MINIMAX_API_HOST",
        host_from_anthropic_base_url(str(creds.get("base_url") or "")),
    )
    return env


def build_uvx_argv(argv: Sequence[str]) -> list[str]:
    """Build the ``uvx`` argv from wrapper args.

    The first non-option positional is the package name. If omitted, the media
    MCP package is used. Remaining args are passed directly to ``uvx``.
    """
    args = list(argv)
    if args and not args[0].startswith("-"):
        package = args.pop(0)
    else:
        package = DEFAULT_PACKAGE
    return [os.environ.get("UVX", "uvx"), package, *args]


def main(argv: Sequence[str] | None = None) -> None:
    populate_minimax_env(os.environ)
    command = build_uvx_argv(sys.argv[1:] if argv is None else argv)
    os.execvp(command[0], command)


if __name__ == "__main__":  # pragma: no cover
    main()
