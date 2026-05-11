"""Tests for the Brave Search API web search provider.

Covers:
- BraveSearchProvider.is_configured() env var gating
- BraveSearchProvider.search() — happy path, HTTP error, request error, bad JSON
- Result normalization (title, url, description, position)
- Limit truncation + Brave's count cap (20)
- _is_backend_available("brave") integration plus the legacy "brave-free" alias
- _get_backend() recognizes "brave" as the canonical configured backend
- check_web_api_key() includes Brave availability
- web_extract uses native extraction instead of trying to route extraction through Brave
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# BraveSearchProvider unit tests
# ---------------------------------------------------------------------------


class TestBraveProviderIsConfigured:
    def test_configured_when_key_set(self, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider
        assert BraveSearchProvider().is_configured() is True

    def test_not_configured_when_key_missing(self, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        from tools.web_providers.brave_free import BraveSearchProvider
        assert BraveSearchProvider().is_configured() is False

    def test_not_configured_when_key_whitespace(self, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "   ")
        from tools.web_providers.brave_free import BraveSearchProvider
        assert BraveSearchProvider().is_configured() is False

    def test_provider_name(self):
        from tools.web_providers.brave_free import BraveSearchProvider
        assert BraveSearchProvider().provider_name() == "brave"

    def test_legacy_provider_alias_kept(self):
        from tools.web_providers.brave_free import BraveFreeSearchProvider, BraveSearchProvider
        assert BraveFreeSearchProvider is BraveSearchProvider

    def test_implements_web_search_provider(self):
        from tools.web_providers.base import WebSearchProvider
        from tools.web_providers.brave_free import BraveSearchProvider
        assert issubclass(BraveSearchProvider, WebSearchProvider)


class TestBraveProviderSearch:
    _SAMPLE_RESPONSE = {
        "web": {
            "results": [
                {"title": "A", "url": "https://a.example.com", "description": "desc A"},
                {"title": "B", "url": "https://b.example.com", "description": "desc B"},
                {"title": "C", "url": "https://c.example.com", "description": "desc C"},
            ]
        }
    }

    @staticmethod
    def _mock_resp(json_data, status_code=200):
        m = MagicMock()
        m.status_code = status_code
        m.json.return_value = json_data
        m.raise_for_status = MagicMock()
        return m

    def test_happy_path_normalizes_results(self, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider

        with patch("httpx.get", return_value=self._mock_resp(self._SAMPLE_RESPONSE)):
            result = BraveSearchProvider().search("test query", limit=5)

        assert result["success"] is True
        web = result["data"]["web"]
        assert len(web) == 3
        assert web[0] == {"title": "A", "url": "https://a.example.com", "description": "desc A", "position": 1}
        assert web[2]["position"] == 3

    def test_sends_subscription_token_header_and_count(self, monkeypatch):
        """Brave uses X-Subscription-Token; count maps from limit."""
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider

        captured = {}

        def fake_get(url, **kwargs):
            captured["url"] = url
            captured["headers"] = kwargs.get("headers", {})
            captured["params"] = kwargs.get("params", {})
            return self._mock_resp({"web": {"results": []}})

        with patch("httpx.get", side_effect=fake_get):
            BraveSearchProvider().search("q", limit=5)

        assert captured["url"] == "https://api.search.brave.com/res/v1/web/search"
        assert captured["headers"].get("X-Subscription-Token") == "BSAkey123"
        assert captured["params"].get("q") == "q"
        assert captured["params"].get("count") == 5

    def test_count_is_capped_at_20(self, monkeypatch):
        """Brave caps count at 20 — limit above that clamps."""
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider

        captured = {}

        def fake_get(url, **kwargs):
            captured["params"] = kwargs.get("params", {})
            return self._mock_resp({"web": {"results": []}})

        with patch("httpx.get", side_effect=fake_get):
            BraveSearchProvider().search("q", limit=100)

        assert captured["params"].get("count") == 20

    def test_limit_is_respected_client_side(self, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider

        with patch("httpx.get", return_value=self._mock_resp(self._SAMPLE_RESPONSE)):
            result = BraveSearchProvider().search("q", limit=2)

        assert result["success"] is True
        assert len(result["data"]["web"]) == 2

    def test_empty_results(self, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider

        with patch("httpx.get", return_value=self._mock_resp({"web": {"results": []}})):
            result = BraveSearchProvider().search("nothing", limit=5)

        assert result["success"] is True
        assert result["data"]["web"] == []

    def test_missing_web_key_returns_empty(self, monkeypatch):
        """Responses without a ``web`` block should produce an empty result set, not crash."""
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider

        with patch("httpx.get", return_value=self._mock_resp({})):
            result = BraveSearchProvider().search("q", limit=5)

        assert result["success"] is True
        assert result["data"]["web"] == []

    def test_http_error_returns_failure(self, monkeypatch):
        import httpx
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider

        bad = MagicMock()
        bad.status_code = 429
        err = httpx.HTTPStatusError("429", request=MagicMock(), response=bad)

        with patch("httpx.get", side_effect=err):
            result = BraveSearchProvider().search("q", limit=5)

        assert result["success"] is False
        assert "429" in result["error"]

    def test_request_error_returns_failure(self, monkeypatch):
        import httpx
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_providers.brave_free import BraveSearchProvider

        with patch("httpx.get", side_effect=httpx.RequestError("boom")):
            result = BraveSearchProvider().search("q", limit=5)

        assert result["success"] is False
        assert "boom" in result["error"] or "Brave" in result["error"]

    def test_missing_key_returns_failure(self, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        from tools.web_providers.brave_free import BraveSearchProvider

        result = BraveSearchProvider().search("q", limit=5)
        assert result["success"] is False
        assert "BRAVE_SEARCH_API_KEY" in result["error"]


# ---------------------------------------------------------------------------
# Integration: _is_backend_available / _get_backend / check_web_api_key
# ---------------------------------------------------------------------------


class TestBraveBackendWiring:
    def test_is_backend_available_true_when_key_set(self, monkeypatch):
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        from tools.web_tools import _is_backend_available
        assert _is_backend_available("brave") is True
        assert _is_backend_available("brave-free") is True  # legacy alias

    def test_is_backend_available_false_when_key_missing(self, monkeypatch):
        monkeypatch.delenv("BRAVE_SEARCH_API_KEY", raising=False)
        from tools.web_tools import _is_backend_available
        assert _is_backend_available("brave") is False
        assert _is_backend_available("brave-free") is False

    def test_configured_backend_accepted(self, monkeypatch):
        from tools import web_tools
        monkeypatch.setattr(web_tools, "_load_web_config", lambda: {"backend": "brave-free"})
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        assert web_tools._get_backend() == "brave"

    def test_auto_detect_picks_brave_when_only_key_set(self, monkeypatch):
        from tools import web_tools
        monkeypatch.setattr(web_tools, "_load_web_config", lambda: {})
        for key in ("FIRECRAWL_API_KEY", "FIRECRAWL_API_URL", "PARALLEL_API_KEY",
                    "TAVILY_API_KEY", "EXA_API_KEY", "SEARXNG_URL"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        monkeypatch.setattr(web_tools, "_is_tool_gateway_ready", lambda: False)
        monkeypatch.setattr(web_tools, "_ddgs_package_importable", lambda: False)
        assert web_tools._get_backend() == "brave"
        assert web_tools._get_search_backend() == "brave"
        assert web_tools._get_extract_backend() == "native"

    def test_brave_does_not_override_paid_provider(self, monkeypatch):
        """Tavily (higher priority) should win in auto-detect."""
        from tools import web_tools
        monkeypatch.setattr(web_tools, "_load_web_config", lambda: {})
        for key in ("FIRECRAWL_API_KEY", "FIRECRAWL_API_URL", "PARALLEL_API_KEY", "EXA_API_KEY", "SEARXNG_URL"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("TAVILY_API_KEY", "tvly")
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        monkeypatch.setattr(web_tools, "_is_tool_gateway_ready", lambda: False)
        assert web_tools._get_backend() == "tavily"

    def test_check_web_api_key_true_when_brave_configured(self, monkeypatch):
        from tools import web_tools
        monkeypatch.setattr(web_tools, "_load_web_config", lambda: {"backend": "brave"})
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        assert web_tools.check_web_api_key() is True


# ---------------------------------------------------------------------------
# Brave Search is search-only; extraction should use native unless explicitly misconfigured
# ---------------------------------------------------------------------------


class TestBraveSearchOnlyAndNativeExtract:
    def test_native_extract_fetches_html_without_brave(self, monkeypatch):
        import asyncio
        import httpx
        from tools import web_tools

        class DummyAsyncClient:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url):
                return httpx.Response(
                    200,
                    headers={"content-type": "text/html; charset=utf-8"},
                    content=b"<html><head><title>Example Title</title></head><body><p>Hello native extract.</p><script>ignore()</script></body></html>",
                    request=httpx.Request("GET", url),
                )

        monkeypatch.setattr(web_tools.httpx, "AsyncClient", DummyAsyncClient)
        monkeypatch.setattr(web_tools, "check_website_access", lambda url: None)
        monkeypatch.setattr(web_tools, "is_safe_url", lambda url: True)
        monkeypatch.setattr("tools.interrupt.is_interrupted", lambda: False, raising=False)

        result = asyncio.get_event_loop().run_until_complete(
            web_tools._native_extract(["https://example.com"])
        )

        assert result[0]["title"] == "Example Title"
        assert "Hello native extract." in result[0]["content"]
        assert "ignore()" not in result[0]["content"]
        assert result[0]["metadata"]["source"] == "native"

    def test_web_extract_uses_native_with_brave_search_backend(self, monkeypatch):
        import asyncio
        from tools import web_tools

        monkeypatch.setattr(web_tools, "_load_web_config", lambda: {"search_backend": "brave", "extract_backend": "native"})
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        monkeypatch.setattr(web_tools, "_is_tool_gateway_ready", lambda: False)
        monkeypatch.setattr("tools.interrupt.is_interrupted", lambda: False, raising=False)
        monkeypatch.setattr(web_tools, "check_auxiliary_model", lambda: False)

        async def fake_native_extract(urls, format=None):
            return [{
                "url": urls[0],
                "title": "Example",
                "content": "native content",
                "raw_content": "native content",
                "metadata": {"source": "native"},
            }]

        monkeypatch.setattr(web_tools, "_native_extract", fake_native_extract)

        result_str = asyncio.get_event_loop().run_until_complete(
            web_tools.web_extract_tool(["https://example.com"])
        )
        result = json.loads(result_str)
        assert result["results"][0]["content"] == "native content"

    def test_explicit_brave_extract_backend_returns_search_only_error(self, monkeypatch):
        import asyncio
        from tools import web_tools

        monkeypatch.setattr(web_tools, "_load_web_config", lambda: {"extract_backend": "brave"})
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        monkeypatch.setattr("tools.interrupt.is_interrupted", lambda: False, raising=False)

        result_str = asyncio.get_event_loop().run_until_complete(
            web_tools.web_extract_tool(["https://example.com"])
        )
        result = json.loads(result_str)
        assert result["success"] is False
        assert "search-only" in result["error"].lower()
        assert "brave search api" in result["error"].lower()

    def test_web_crawl_returns_search_only_error(self, monkeypatch):
        import asyncio
        from tools import web_tools

        monkeypatch.setattr(web_tools, "_load_web_config", lambda: {"backend": "brave"})
        monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "BSAkey123")
        monkeypatch.setattr(web_tools, "_is_tool_gateway_ready", lambda: False)
        monkeypatch.setattr(web_tools, "check_firecrawl_api_key", lambda: False)
        monkeypatch.setattr("tools.interrupt.is_interrupted", lambda: False, raising=False)

        result_str = asyncio.get_event_loop().run_until_complete(
            web_tools.web_crawl_tool("https://example.com")
        )
        result = json.loads(result_str)
        assert result["success"] is False
        assert "search-only" in result["error"].lower()
        assert "brave" in result["error"].lower()
