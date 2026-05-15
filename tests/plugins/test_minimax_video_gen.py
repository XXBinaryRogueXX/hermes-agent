"""Tests for the MiniMax / Hailuo native video generation backend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pytest

from plugins.video_gen.minimax import MiniMaxVideoGenProvider


@dataclass
class _FakeResponse:
    payload: Dict[str, Any]
    status_code: int = 200
    text: str = ""

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)  # type: ignore[arg-type]

    def json(self) -> Dict[str, Any]:
        return self.payload


class TestMiniMaxVideoGenProvider:
    def test_text_to_video_submits_polls_and_returns_download_url(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_API_HOST", "https://api.example.test")
        monkeypatch.setattr("plugins.video_gen.minimax.time.sleep", lambda *_a, **_k: None)

        calls: List[Dict[str, Any]] = []

        def fake_request(method, url, **kwargs):
            calls.append({"method": method, "url": url, "kwargs": kwargs})
            if method == "POST" and url.endswith("/v1/video_generation"):
                return _FakeResponse({"task_id": "task-123", "base_resp": {"status_code": 0}})
            if method == "GET" and "/v1/query/video_generation" in url:
                return _FakeResponse({"status": "Success", "file_id": "file-123", "base_resp": {"status_code": 0}})
            if method == "GET" and "/v1/files/retrieve" in url:
                return _FakeResponse({"file": {"download_url": "https://cdn.example/video.mp4"}, "base_resp": {"status_code": 0}})
            raise AssertionError(f"unexpected request: {method} {url}")

        monkeypatch.setattr("plugins.video_gen.minimax.requests.request", fake_request)

        result = MiniMaxVideoGenProvider().generate(
            "a robot painting a sign",
            duration=10,
            resolution="720p",
        )

        assert result["success"] is True
        assert result["video"] == "https://cdn.example/video.mp4"
        assert result["provider"] == "minimax"
        assert result["model"] == "MiniMax-Hailuo-2.3"
        assert result["duration"] == 10
        assert result["resolution"] == "768P"
        submit_payload = calls[0]["kwargs"]["json"]
        assert submit_payload == {
            "model": "MiniMax-Hailuo-2.3",
            "prompt": "a robot painting a sign",
            "duration": 10,
            "resolution": "768P",
        }
        assert calls[0]["kwargs"]["headers"]["Authorization"] == "Bearer test-key"
        assert calls[0]["kwargs"]["headers"]["MM-API-Source"] == "Hermes-Agent"

    def test_local_image_path_is_converted_to_data_url(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        monkeypatch.setattr("plugins.video_gen.minimax.time.sleep", lambda *_a, **_k: None)

        image = tmp_path / "frame.jpg"
        image.write_bytes(b"fake-jpeg")
        payloads: List[Dict[str, Any]] = []

        def fake_request(method, url, **kwargs):
            if method == "POST":
                payloads.append(kwargs["json"])
                return _FakeResponse({"task_id": "task-img", "base_resp": {"status_code": 0}})
            if "/v1/query/video_generation" in url:
                return _FakeResponse({"status": "Success", "file_id": "file-img", "base_resp": {"status_code": 0}})
            if "/v1/files/retrieve" in url:
                return _FakeResponse({"file": {"download_url": "https://cdn.example/i2v.mp4"}, "base_resp": {"status_code": 0}})
            raise AssertionError(f"unexpected request: {method} {url}")

        monkeypatch.setattr("plugins.video_gen.minimax.requests.request", fake_request)

        result = MiniMaxVideoGenProvider().generate(
            "animate the first frame",
            image_url=str(image),
            model="MiniMax-Hailuo-2.3-Fast",
        )

        assert result["success"] is True
        assert result["modality"] == "image"
        assert payloads[0]["first_frame_image"].startswith("data:image/jpeg;base64,")
        assert payloads[0]["model"] == "MiniMax-Hailuo-2.3-Fast"

    def test_image_only_model_requires_image_url(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")

        result = MiniMaxVideoGenProvider().generate(
            "prompt only",
            model="I2V-01",
        )

        assert result["success"] is False
        assert result["error_type"] == "api_error"
        assert "requires image_url" in result["error"]

    def test_is_available_uses_api_key_without_oauth_probe(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        assert MiniMaxVideoGenProvider().is_available() is True
