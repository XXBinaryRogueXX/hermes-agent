from __future__ import annotations

import json

import pytest
import requests

from tools import tts_tool


class _FakeResponse:
    def __init__(self, payload, *, status_code=200, content_type="application/json"):
        self._payload = payload
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.content = json.dumps(payload).encode()
        self.text = self.content.decode()

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(response=self)


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch):
    monkeypatch.setattr(
        tts_tool,
        "get_env_value",
        lambda name, default=None: "test-minimax-key" if name == "MINIMAX_API_KEY" else default,
    )


def test_minimax_tts_uses_current_t2a_v2_payload(monkeypatch, tmp_path):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append((url, json, headers, timeout))
        return _FakeResponse({
            "data": {"audio": b"minimax-audio".hex(), "status": 2},
            "base_resp": {"status_code": 0, "status_msg": "success"},
        })

    monkeypatch.setattr(requests, "post", fake_post)

    output = tmp_path / "out.mp3"
    tts_tool._generate_minimax_tts(
        "hello",
        str(output),
        {"minimax": {"voice_id": "English_expressive_narrator"}},
    )

    assert output.read_bytes() == b"minimax-audio"
    url, payload, headers, timeout = calls[0]
    assert url == "https://api.minimax.io/v1/t2a_v2"
    assert headers["Authorization"] == "Bearer test-minimax-key"
    assert payload["model"] == "speech-2.8-hd"
    assert payload["stream"] is False
    assert payload["output_format"] == "hex"
    assert payload["voice_setting"]["voice_id"] == "English_expressive_narrator"
    assert payload["audio_setting"]["format"] == "mp3"
    assert timeout == 60


def test_minimax_tts_adds_group_id_only_when_configured(monkeypatch, tmp_path):
    calls = []

    def fake_post(url, *, json, headers, timeout):
        calls.append(url)
        return _FakeResponse({
            "data": {"audio": b"group-audio".hex()},
            "base_resp": {"status_code": 0},
        })

    monkeypatch.setattr(requests, "post", fake_post)

    output = tmp_path / "out.wav"
    tts_tool._generate_minimax_tts(
        "hello",
        str(output),
        {"minimax": {"group_id": "group-123"}},
    )

    assert calls == ["https://api.minimax.io/v1/t2a_v2?GroupId=group-123"]
    assert output.read_bytes() == b"group-audio"


def test_minimax_tts_surfaces_base_resp_errors(monkeypatch, tmp_path):
    def fake_post(url, *, json, headers, timeout):
        return _FakeResponse({
            "base_resp": {"status_code": 1001, "status_msg": "invalid voice"},
        })

    monkeypatch.setattr(requests, "post", fake_post)

    with pytest.raises(RuntimeError, match="invalid voice"):
        tts_tool._generate_minimax_tts("hello", str(tmp_path / "out.mp3"), {"minimax": {}})
