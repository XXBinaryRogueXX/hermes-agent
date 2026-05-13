"""Tests for the bundled MiniMax image_gen plugin."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

import plugins.image_gen.minimax as minimax_plugin


@pytest.fixture(autouse=True)
def _tmp_home_and_key(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("MINIMAX_API_KEY", "test-minimax-key")
    yield tmp_path


class TestMetadata:
    def test_name_and_default_model(self):
        provider = minimax_plugin.MiniMaxImageGenProvider()
        assert provider.name == "minimax"
        assert provider.display_name == "MiniMax"
        assert provider.default_model() == "image-01"

    def test_is_available_uses_minimax_key(self, monkeypatch):
        provider = minimax_plugin.MiniMaxImageGenProvider()
        assert provider.is_available() is True
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        assert provider.is_available() is False

    def test_setup_schema_prompts_for_minimax_key(self):
        schema = minimax_plugin.MiniMaxImageGenProvider().get_setup_schema()
        assert schema["name"] == "MiniMax"
        assert schema["env_vars"][0]["key"] == "MINIMAX_API_KEY"


class TestGenerate:
    def test_empty_prompt_rejected(self):
        result = minimax_plugin.MiniMaxImageGenProvider().generate("", aspect_ratio="square")
        assert result["success"] is False
        assert result["error_type"] == "invalid_argument"

    def test_url_response_success(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "id": "trace-123",
            "data": {"image_urls": ["https://minimax.example/image.jpg"]},
            "base_resp": {"status_code": 0, "status_msg": "success"},
        }

        with patch("plugins.image_gen.minimax.requests.post", return_value=response) as mock_post:
            result = minimax_plugin.MiniMaxImageGenProvider().generate(
                "a small robot reading",
                aspect_ratio="portrait",
            )

        assert result["success"] is True
        assert result["image"] == "https://minimax.example/image.jpg"
        assert result["provider"] == "minimax"
        assert result["model"] == "image-01"
        assert result["aspect_ratio"] == "portrait"
        assert result["minimax_trace_id"] == "trace-123"

        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "image-01"
        assert payload["aspect_ratio"] == "9:16"
        assert payload["response_format"] == "base64"
        assert payload["n"] == 1
        assert payload["prompt_optimizer"] is True

    def test_base64_response_saves_to_cache(self, tmp_path):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": {"image_base64": ["dGVzdC1pbWFnZS1kYXRh"]},
            "base_resp": {"status_code": 0},
        }

        with patch("plugins.image_gen.minimax.requests.post", return_value=response):
            result = minimax_plugin.MiniMaxImageGenProvider().generate("a cat", aspect_ratio="square")

        assert result["success"] is True
        saved = Path(result["image"])
        assert saved.exists()
        assert saved.parent == tmp_path / "cache" / "images"
        assert saved.read_bytes() == b"test-image-data"

    def test_config_overrides_response_format_and_seed(self, tmp_path):
        import yaml

        (tmp_path / "config.yaml").write_text(
            yaml.safe_dump({
                "image_gen": {
                    "provider": "minimax",
                    "model": "image-01",
                    "minimax": {
                        "response_format": "url",
                        "seed": 42,
                        "prompt_optimizer": False,
                    },
                },
            })
        )

        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "data": {"image_urls": ["https://minimax.example/seeded.jpg"]},
            "base_resp": {"status_code": 0},
        }

        with patch("plugins.image_gen.minimax.requests.post", return_value=response) as mock_post:
            result = minimax_plugin.MiniMaxImageGenProvider().generate("a cat")

        assert result["success"] is True
        payload = mock_post.call_args.kwargs["json"]
        assert payload["response_format"] == "url"
        assert payload["seed"] == 42
        assert payload["prompt_optimizer"] is False

    def test_base_resp_error(self):
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "base_resp": {"status_code": 1001, "status_msg": "bad request"},
        }

        with patch("plugins.image_gen.minimax.requests.post", return_value=response):
            result = minimax_plugin.MiniMaxImageGenProvider().generate("a cat")

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "bad request" in result["error"]

    def test_timeout(self):
        with patch("plugins.image_gen.minimax.requests.post", side_effect=requests.Timeout()):
            result = minimax_plugin.MiniMaxImageGenProvider().generate("a cat")

        assert result["success"] is False
        assert result["error_type"] == "timeout"
