"""Tests for scripts/minimax_provider_smoke.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "minimax_provider_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("minimax_provider_smoke", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_anthropic_messages_endpoint_variants():
    smoke = _load_module()
    assert (
        smoke._anthropic_messages_endpoint("https://api.minimax.io/anthropic")
        == "https://api.minimax.io/anthropic/v1/messages"
    )
    assert (
        smoke._anthropic_messages_endpoint("https://api.minimax.io/anthropic/v1")
        == "https://api.minimax.io/anthropic/v1/messages"
    )
    assert (
        smoke._anthropic_messages_endpoint("https://proxy.example/v1")
        == "https://proxy.example/v1/messages"
    )


def test_run_smoke_passes_with_expected_responses():
    smoke = _load_module()
    creds = smoke.Credentials(
        provider="test",
        api_key="sk-test",
        base_url="https://api.minimax.io/anthropic",
        source="unit-test",
    )

    def opener(req, timeout):
        body = json.loads(req.data.decode())
        if body["messages"][0]["content"].startswith("Reply exactly"):
            return FakeResponse({"content": [{"type": "text", "text": "HERMES_MINIMAX_OK"}]})
        if "tools" not in body:
            return FakeResponse({"content": [{"type": "text", "text": "hola"}]})
        if body["tools"][0]["name"] == "get_weather":
            return FakeResponse({
                "content": [
                    {
                        "type": "tool_use",
                        "name": "get_weather",
                        "input": {"city": "Paris", "unit": "celsius"},
                    }
                ]
            })
        if body["tools"][0]["name"] == "record_order":
            return FakeResponse({
                "content": [
                    {
                        "type": "tool_use",
                        "name": "record_order",
                        "input": {"zeta": "first", "alpha": "second", "middle": "third"},
                    }
                ]
            })
        return FakeResponse({"content": [{"type": "text", "text": "hola"}]})

    results = smoke.run_smoke(creds, model="MiniMax-M2.7", opener=opener)
    assert all(result.passed for result in results)


def test_summary_fails_when_critical_check_fails():
    smoke = _load_module()
    creds = smoke.Credentials(
        provider="test",
        api_key="sk-test-secret",
        base_url="https://api.minimax.io/anthropic",
        source="unit-test",
    )
    results = [
        smoke.CheckResult("chat_content", True, "ok"),
        smoke.CheckResult("tool_schema", False, "no tool"),
        smoke.CheckResult("property_order", False, "bad order", critical=False),
    ]
    summary = smoke._summary(creds, "MiniMax-M2.7", results)
    assert summary["passed"] is False
    assert summary["api_key"] == "sk-t…cret"
    assert summary["passed_count"] == 1

def test_summary_dry_run_has_no_pass_verdict():
    smoke = _load_module()
    creds = smoke.Credentials(
        provider="test",
        api_key="sk-test-secret",
        base_url="https://api.minimax.io/anthropic",
        source="unit-test",
    )
    summary = smoke._summary(creds, "MiniMax-M2.7", [])
    assert summary["passed"] is None
    assert summary["total_count"] == 0


def test_sanitize_text_redacts_keys_and_url_userinfo():
    smoke = _load_module()
    creds = smoke.Credentials(
        provider="test",
        api_key="sk-test-secret-token-123456",
        base_url="https://user:password@gateway.example.com/anthropic",
        source="unit-test",
    )
    text = smoke._sanitize_text(
        "HTTP 401 x-api-key: sk-test-secret-token-123456 at "
        "https://user:password@gateway.example.com/anthropic",
        creds,
    )
    assert "sk-test-secret-token-123456" not in text
    assert "user:password" not in text
    assert "[REDACTED]" in text


def test_run_smoke_sanitizes_exception_details():
    smoke = _load_module()
    creds = smoke.Credentials(
        provider="test",
        api_key="sk-test-secret-token-123456",
        base_url="https://api.minimax.io/anthropic",
        source="unit-test",
    )

    def opener(req, timeout):
        raise RuntimeError("proxy echoed sk-test-secret-token-123456")

    results = smoke.run_smoke(creds, model="MiniMax-M2.7", opener=opener)
    assert results[0].name == "chat_content"
    assert all("sk-test-secret-token-123456" not in result.detail for result in results)
