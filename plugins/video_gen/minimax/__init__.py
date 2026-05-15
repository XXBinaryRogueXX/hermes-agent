"""MiniMax / Hailuo video generation backend.

This provider mirrors the official ``MiniMax-AI/MiniMax-MCP`` video tools but
registers as a native Hermes ``video_generate`` backend. It supports the common
Hermes surface:

- text-to-video (prompt only)
- image-to-video (prompt + ``image_url`` / first frame)

Authentication supports either the standard MiniMax API-key env vars
(``MINIMAX_API_KEY`` + optional ``MINIMAX_API_HOST``/``MINIMAX_BASE_URL``) or
Hermes' MiniMax OAuth runtime credentials. OAuth credentials expose an
Anthropic-compatible ``/anthropic`` URL; media endpoints live on the same host
without that suffix.

The API is asynchronous: submit to ``/v1/video_generation``, poll
``/v1/query/video_generation``, then retrieve the final download URL through
``/v1/files/retrieve``. The returned URL is handed to Hermes/Gateway for native
media delivery.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from agent.video_gen_provider import VideoGenProvider, error_response, success_response

logger = logging.getLogger(__name__)

DEFAULT_API_HOST = "https://api.minimax.io"
DEFAULT_MODEL = "MiniMax-Hailuo-2.3"
DEFAULT_DURATION = 6
DEFAULT_RESOLUTION = "768P"
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_POLL_INTERVAL_SECONDS = 5

# The official MiniMax MCP currently exposes the same endpoint and documents
# these families. Hailuo 2.3 is the current default in mmx and supports both
# prompt-only generation and first-frame image-to-video.
MODELS: Dict[str, Dict[str, Any]] = {
    "MiniMax-Hailuo-2.3": {
        "display": "Hailuo 2.3",
        "speed": "~60-900s",
        "strengths": "Current default; text-to-video and first-frame image-to-video.",
        "price": "paid MiniMax video quota",
        "modalities": ["text", "image"],
    },
    "MiniMax-Hailuo-2.3-Fast": {
        "display": "Hailuo 2.3 Fast",
        "speed": "~30-600s",
        "strengths": "Faster first-frame image-to-video mode.",
        "price": "paid MiniMax video quota",
        "modalities": ["image"],
    },
    "MiniMax-Hailuo-02": {
        "display": "Hailuo 02",
        "speed": "~60-1200s",
        "strengths": "High-quality legacy Hailuo model documented by MiniMax MCP.",
        "price": "paid MiniMax video quota",
        "modalities": ["text", "image"],
    },
    "T2V-01": {
        "display": "T2V-01",
        "speed": "~60-600s",
        "strengths": "Legacy text-to-video.",
        "price": "paid MiniMax video quota",
        "modalities": ["text"],
    },
    "T2V-01-Director": {
        "display": "T2V-01 Director",
        "speed": "~60-600s",
        "strengths": "Legacy text-to-video with camera movement instructions.",
        "price": "paid MiniMax video quota",
        "modalities": ["text"],
    },
    "I2V-01": {
        "display": "I2V-01",
        "speed": "~60-600s",
        "strengths": "Legacy image-to-video.",
        "price": "paid MiniMax video quota",
        "modalities": ["image"],
    },
    "I2V-01-Director": {
        "display": "I2V-01 Director",
        "speed": "~60-600s",
        "strengths": "Legacy image-to-video with camera movement instructions.",
        "price": "paid MiniMax video quota",
        "modalities": ["image"],
    },
    "I2V-01-live": {
        "display": "I2V-01 Live",
        "speed": "~60-600s",
        "strengths": "Legacy live-style image-to-video.",
        "price": "paid MiniMax video quota",
        "modalities": ["image"],
    },
}

RESOLUTION_MAP = {
    "480p": "768P",
    "540p": "768P",
    "720p": "768P",
    "768p": "768P",
    "768P": "768P",
    "1080p": "1080P",
    "1080P": "1080P",
}
VALID_RESOLUTIONS = ("768P", "1080P")
VALID_DURATIONS = (6, 10)


class MiniMaxVideoError(RuntimeError):
    """Raised for MiniMax API and response-shape errors."""


def _strip_anthropic_suffix(url: str) -> str:
    value = (url or "").strip().rstrip("/")
    if value.endswith("/anthropic"):
        return value[: -len("/anthropic")]
    return value


def _resolve_credentials() -> Tuple[str, str, str]:
    """Return ``(api_key, api_host, source)`` or raise ``MiniMaxVideoError``."""

    env_key = os.getenv("MINIMAX_API_KEY", "").strip()
    if env_key:
        host = (
            os.getenv("MINIMAX_API_HOST")
            or os.getenv("MINIMAX_BASE_URL")
            or DEFAULT_API_HOST
        )
        return env_key, _strip_anthropic_suffix(host), "env"

    try:
        from hermes_cli.auth import resolve_minimax_oauth_runtime_credentials

        creds = resolve_minimax_oauth_runtime_credentials()
    except Exception as exc:
        raise MiniMaxVideoError(
            "MINIMAX_API_KEY is not set and MiniMax OAuth credentials could not be resolved"
        ) from exc

    token = str(creds.get("api_key") or creds.get("access_token") or "").strip()
    if not token:
        raise MiniMaxVideoError("MiniMax OAuth credentials did not include an access token")

    host = str(
        creds.get("api_host")
        or creds.get("base_url")
        or creds.get("inference_base_url")
        or DEFAULT_API_HOST
    )
    return token, _strip_anthropic_suffix(host), "oauth"


def _headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "MM-API-Source": "Hermes-Agent",
    }


def _api_request(
    method: str,
    endpoint: str,
    *,
    api_key: str,
    api_host: str,
    timeout: int = 60,
    **kwargs: Any,
) -> Dict[str, Any]:
    response = requests.request(
        method,
        f"{api_host}{endpoint}",
        headers=_headers(api_key),
        timeout=timeout,
        **kwargs,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text[:500]
        raise MiniMaxVideoError(
            f"MiniMax API HTTP {response.status_code}: {detail or exc}"
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise MiniMaxVideoError("MiniMax API returned non-JSON response") from exc

    base_resp = data.get("base_resp") if isinstance(data, dict) else None
    if isinstance(base_resp, dict) and base_resp.get("status_code") not in (None, 0):
        code = base_resp.get("status_code")
        msg = base_resp.get("status_msg") or "unknown error"
        raise MiniMaxVideoError(f"MiniMax API error {code}: {msg}")
    return data


def _normalize_resolution(resolution: Optional[str]) -> str:
    value = (resolution or DEFAULT_RESOLUTION).strip()
    return RESOLUTION_MAP.get(value, RESOLUTION_MAP.get(value.lower(), DEFAULT_RESOLUTION))


def _normalize_duration(duration: Optional[int]) -> int:
    try:
        value = int(duration) if duration is not None else DEFAULT_DURATION
    except (TypeError, ValueError):
        value = DEFAULT_DURATION
    return min(VALID_DURATIONS, key=lambda candidate: abs(candidate - value))


def _image_to_data_url(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    raw = path.read_bytes()
    encoded = base64.b64encode(raw).decode("utf-8")
    return f"data:{mime};base64,{encoded}"


def _normalize_image(image_url: Optional[str]) -> Optional[str]:
    value = (image_url or "").strip()
    if not value:
        return None
    if value.startswith(("http://", "https://", "data:")):
        return value
    path = Path(value).expanduser()
    if not path.exists():
        raise MiniMaxVideoError(f"first-frame image does not exist: {value}")
    return _image_to_data_url(path)


def _resolve_model(model: Optional[str], has_image: bool) -> Tuple[str, Dict[str, Any]]:
    chosen = (model or "").strip() or DEFAULT_MODEL
    if chosen not in MODELS:
        raise MiniMaxVideoError(
            f"unknown MiniMax video model '{chosen}'. Known models: {', '.join(MODELS)}"
        )
    meta = MODELS[chosen]
    modalities = set(meta.get("modalities") or [])
    if has_image and "image" not in modalities:
        raise MiniMaxVideoError(f"MiniMax model {chosen} does not support image-to-video")
    if not has_image and "text" not in modalities:
        raise MiniMaxVideoError(f"MiniMax model {chosen} requires image_url / first-frame input")
    return chosen, meta


def _poll_for_file_id(
    task_id: str,
    *,
    api_key: str,
    api_host: str,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> Tuple[str, str]:
    deadline = time.monotonic() + timeout_seconds
    last_status = ""
    while time.monotonic() < deadline:
        status_data = _api_request(
            "GET",
            f"/v1/query/video_generation?task_id={task_id}",
            api_key=api_key,
            api_host=api_host,
            timeout=60,
        )
        last_status = str(status_data.get("status") or "")
        if last_status == "Success":
            file_id = status_data.get("file_id")
            if not file_id:
                raise MiniMaxVideoError(f"MiniMax task {task_id} succeeded without file_id")
            return str(file_id), last_status
        if last_status == "Fail":
            raise MiniMaxVideoError(f"MiniMax video generation failed for task_id {task_id}")
        time.sleep(max(1, poll_interval_seconds))
    raise MiniMaxVideoError(
        f"Timed out waiting for MiniMax video task {task_id}; last status={last_status or 'unknown'}"
    )


def _download_url_for_file(
    file_id: str,
    *,
    api_key: str,
    api_host: str,
) -> str:
    file_data = _api_request(
        "GET",
        f"/v1/files/retrieve?file_id={file_id}",
        api_key=api_key,
        api_host=api_host,
        timeout=60,
    )
    url = (file_data.get("file") or {}).get("download_url")
    if not url:
        raise MiniMaxVideoError(f"MiniMax file {file_id} did not include download_url")
    return str(url)


class MiniMaxVideoGenProvider(VideoGenProvider):
    """MiniMax Hailuo video backend (text-to-video + image-to-video)."""

    @property
    def name(self) -> str:
        return "minimax"

    @property
    def display_name(self) -> str:
        return "MiniMax Hailuo"

    def is_available(self) -> bool:
        if os.getenv("MINIMAX_API_KEY", "").strip():
            return True
        try:
            _resolve_credentials()
            return True
        except Exception:
            return False

    def list_models(self) -> List[Dict[str, Any]]:
        return [{"id": model_id, **meta} for model_id, meta in MODELS.items()]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "MiniMax Hailuo",
            "badge": "paid",
            "tag": (
                "Hailuo 2.3 / 02 video generation — text-to-video and "
                "first-frame image-to-video. Cost/quota gated."
            ),
            "env_vars": [
                {
                    "key": "MINIMAX_API_KEY",
                    "prompt": "MiniMax API key (optional if MiniMax OAuth is logged in)",
                    "url": "https://platform.minimax.io/",
                },
                {
                    "key": "MINIMAX_API_HOST",
                    "prompt": "MiniMax API host (optional; default https://api.minimax.io)",
                    "url": "https://platform.minimax.io/docs/api-reference/video-generation",
                    "optional": True,
                },
            ],
        }

    def capabilities(self) -> Dict[str, Any]:
        return {
            "modalities": ["text", "image"],
            "aspect_ratios": [],
            "resolutions": list(VALID_RESOLUTIONS),
            "max_duration": max(VALID_DURATIONS),
            "min_duration": min(VALID_DURATIONS),
            "supports_audio": False,
            "supports_negative_prompt": False,
            "max_reference_images": 0,
            "cost_warning": (
                "MiniMax Hailuo video is paid/quota-gated. Run "
                "scripts/minimax-quota-check.sh before unattended use; "
                "current Token Plan quota may be 0 even when OAuth works."
            ),
        }

    def generate(
        self,
        prompt: str,
        *,
        model: Optional[str] = None,
        image_url: Optional[str] = None,
        reference_image_urls: Optional[List[str]] = None,
        duration: Optional[int] = None,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        negative_prompt: Optional[str] = None,
        audio: Optional[bool] = None,
        seed: Optional[int] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        prompt = (prompt or "").strip()
        if not prompt:
            return error_response(
                error="prompt is required for MiniMax video generation",
                error_type="missing_prompt",
                provider="minimax",
                model=model or DEFAULT_MODEL,
            )

        try:
            normalized_image = _normalize_image(image_url)
            model_id, _meta = _resolve_model(model, has_image=bool(normalized_image))
            api_key, api_host, auth_source = _resolve_credentials()
            normalized_duration = _normalize_duration(duration)
            normalized_resolution = _normalize_resolution(resolution)

            payload: Dict[str, Any] = {
                "model": model_id,
                "prompt": prompt,
                "duration": normalized_duration,
                "resolution": normalized_resolution,
            }
            if normalized_image:
                payload["first_frame_image"] = normalized_image

            submitted = _api_request(
                "POST",
                "/v1/video_generation",
                api_key=api_key,
                api_host=api_host,
                json=payload,
                timeout=60,
            )
            task_id = submitted.get("task_id")
            if not task_id:
                raise MiniMaxVideoError("MiniMax video response did not include task_id")

            timeout_seconds = int(os.getenv("MINIMAX_VIDEO_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
            poll_interval = int(os.getenv("MINIMAX_VIDEO_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS))
            file_id, final_status = _poll_for_file_id(
                str(task_id),
                api_key=api_key,
                api_host=api_host,
                timeout_seconds=timeout_seconds,
                poll_interval_seconds=poll_interval,
            )
            video_url = _download_url_for_file(file_id, api_key=api_key, api_host=api_host)

            return success_response(
                video=video_url,
                model=model_id,
                prompt=prompt,
                modality="image" if normalized_image else "text",
                aspect_ratio="",
                duration=normalized_duration,
                provider="minimax",
                extra={
                    "task_id": str(task_id),
                    "file_id": file_id,
                    "status": final_status,
                    "resolution": normalized_resolution,
                    "auth_source": auth_source,
                },
            )
        except Exception as exc:
            logger.warning("MiniMax video generation failed: %s", exc, exc_info=True)
            error_type = "auth_required" if "API_KEY" in str(exc) or "OAuth" in str(exc) else "api_error"
            return error_response(
                error=f"MiniMax video generation failed: {exc}",
                error_type=error_type,
                provider="minimax",
                model=model or DEFAULT_MODEL,
                prompt=prompt,
                aspect_ratio=aspect_ratio,
            )


def register(ctx) -> None:
    """Plugin entry point — wire ``MiniMaxVideoGenProvider`` into the registry."""

    ctx.register_video_gen_provider(MiniMaxVideoGenProvider())
