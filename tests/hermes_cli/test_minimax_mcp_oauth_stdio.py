"""Tests for the MiniMax MCP OAuth stdio wrapper."""

from __future__ import annotations

import types


def test_host_from_anthropic_base_url_variants():
    from hermes_cli.minimax_mcp_oauth_stdio import host_from_anthropic_base_url

    assert host_from_anthropic_base_url(None) == "https://api.minimax.io"
    assert (
        host_from_anthropic_base_url("https://api.minimax.io/anthropic")
        == "https://api.minimax.io"
    )
    assert (
        host_from_anthropic_base_url("https://api.minimax.io/anthropic/v1/messages")
        == "https://api.minimax.io"
    )
    assert (
        host_from_anthropic_base_url("https://api.minimaxi.com/anthropic/")
        == "https://api.minimaxi.com"
    )


def test_build_uvx_argv_uses_default_package(monkeypatch):
    from hermes_cli.minimax_mcp_oauth_stdio import build_uvx_argv

    monkeypatch.delenv("UVX", raising=False)
    assert build_uvx_argv(["-y"]) == ["uvx", "minimax-mcp", "-y"]


def test_build_uvx_argv_accepts_package_and_uvx_override(monkeypatch):
    from hermes_cli.minimax_mcp_oauth_stdio import build_uvx_argv

    monkeypatch.setenv("UVX", "/opt/bin/uvx")
    assert build_uvx_argv(["minimax-coding-plan-mcp", "-y"]) == [
        "/opt/bin/uvx",
        "minimax-coding-plan-mcp",
        "-y",
    ]


def test_populate_env_preserves_existing_api_key():
    from hermes_cli.minimax_mcp_oauth_stdio import populate_minimax_env

    env = {"MINIMAX_API_KEY": "already-set"}
    result = populate_minimax_env(env)
    assert result["MINIMAX_API_KEY"] == "already-set"
    assert result["MINIMAX_API_HOST"] == "https://api.minimax.io"


def test_populate_env_resolves_hermes_oauth(monkeypatch):
    import sys

    fake_auth = types.SimpleNamespace(
        resolve_minimax_oauth_runtime_credentials=lambda: {
            "api_key": "oauth-token",
            "base_url": "https://api.minimax.io/anthropic",
        }
    )
    monkeypatch.setitem(sys.modules, "hermes_cli.auth", fake_auth)

    from hermes_cli.minimax_mcp_oauth_stdio import populate_minimax_env

    env = {}
    result = populate_minimax_env(env)
    assert result["MINIMAX_API_KEY"] == "oauth-token"
    assert result["MINIMAX_API_HOST"] == "https://api.minimax.io"
