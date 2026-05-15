from unittest.mock import MagicMock, call, patch


def test_minimax_oauth_provider_initializes_anthropic_transport(monkeypatch):
    """Direct AIAgent(provider='minimax-oauth') must use OAuth runtime + Anthropic API."""
    from run_agent import AIAgent

    monkeypatch.setattr("run_agent.get_tool_definitions", lambda *args, **kwargs: [])
    monkeypatch.setattr("run_agent.check_toolset_requirements", lambda *args, **kwargs: {})
    monkeypatch.setattr("run_agent.OpenAI", MagicMock(name="OpenAI"))

    anthropic_client = MagicMock(name="anthropic-client")
    with (
        patch("hermes_cli.auth.resolve_minimax_oauth_runtime_credentials", return_value={
            "api_key": "minimax-oauth-access-token",
            "base_url": "https://api.minimax.io/anthropic",
            "source": "oauth",
        }),
        patch("agent.anthropic_adapter.build_anthropic_client", return_value=anthropic_client) as mock_build,
    ):
        agent = AIAgent(
            provider="minimax-oauth",
            model="MiniMax-M2.7",
            platform="cli",
            quiet_mode=True,
            skip_memory=True,
            skip_context_files=True,
        )

    assert agent.api_mode == "anthropic_messages"
    assert agent.provider == "minimax-oauth"
    assert agent.api_key == "minimax-oauth-access-token"
    assert agent.base_url == "https://api.minimax.io/anthropic"
    assert agent.client is None
    assert agent._anthropic_client is anthropic_client
    assert agent._is_anthropic_oauth is False
    mock_build.assert_any_call(
        "minimax-oauth-access-token",
        "https://api.minimax.io/anthropic",
        timeout=None,
    )
    assert call("minimax-oauth-access-token", "") not in mock_build.call_args_list
