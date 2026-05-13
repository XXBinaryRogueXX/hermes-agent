"""MiniMax image generation backend.

Uses MiniMax's synchronous ``/v1/image_generation`` API with the ``image-01``
model. The provider supports both URL and base64 responses; base64 images are
saved under ``$HERMES_HOME/cache/images/``.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import requests

from agent.image_gen_provider import (
    DEFAULT_ASPECT_RATIO,
    ImageGenProvider,
    error_response,
    resolve_aspect_ratio,
    save_b64_image,
    success_response,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.minimax.io/v1"
API_ENDPOINT = "/image_generation"
DEFAULT_MODEL = "image-01"
DEFAULT_RESPONSE_FORMAT = "base64"

_MODELS: Dict[str, Dict[str, Any]] = {
    "image-01": {
        "display": "MiniMax Image 01",
        "speed": "varies",
        "strengths": "High-quality text-to-image and subject-reference generation",
    },
}

_ASPECT_RATIOS = {
    "landscape": "16:9",
    "square": "1:1",
    "portrait": "9:16",
}


def _get_env_value(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        from hermes_cli.config import get_env_value as _config_get_env_value
    except Exception:
        return os.getenv(name, default)
    value = _config_get_env_value(name)
    return default if value is None else value


def _load_image_gen_config() -> Dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        section = cfg.get("image_gen") if isinstance(cfg, dict) else None
        return section if isinstance(section, dict) else {}
    except Exception as exc:
        logger.debug("Could not load image_gen config: %s", exc)
        return {}


def _load_minimax_config() -> Dict[str, Any]:
    section = _load_image_gen_config()
    mm_section = section.get("minimax") if isinstance(section.get("minimax"), dict) else None
    return mm_section if isinstance(mm_section, dict) else {}


def _resolve_model() -> Tuple[str, Dict[str, Any]]:
    env_override = os.getenv("MINIMAX_IMAGE_MODEL", "").strip()
    if env_override in _MODELS:
        return env_override, _MODELS[env_override]

    top = _load_image_gen_config()
    mm_cfg = top.get("minimax") if isinstance(top.get("minimax"), dict) else {}
    for candidate in (
        mm_cfg.get("model") if isinstance(mm_cfg, dict) else None,
        top.get("model"),
    ):
        if isinstance(candidate, str) and candidate.strip() in _MODELS:
            model_id = candidate.strip()
            return model_id, _MODELS[model_id]
    return DEFAULT_MODEL, _MODELS[DEFAULT_MODEL]


def _response_format(config: Dict[str, Any]) -> str:
    value = str(config.get("response_format") or DEFAULT_RESPONSE_FORMAT).strip().lower()
    return value if value in {"url", "base64"} else DEFAULT_RESPONSE_FORMAT


def _base_url(config: Dict[str, Any]) -> str:
    return str(
        config.get("base_url")
        or _get_env_value("MINIMAX_IMAGE_BASE_URL")
        or _get_env_value("MINIMAX_BASE_URL")
        or DEFAULT_BASE_URL
    ).strip().rstrip("/")


def _first_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        for item in value:
            found = _first_string(item)
            if found:
                return found
    if isinstance(value, dict):
        for key in (
            "url",
            "image_url",
            "image",
            "b64_json",
            "image_base64",
            "base64",
            "data",
        ):
            found = _first_string(value.get(key))
            if found:
                return found
    return ""


def _strip_data_uri(value: str) -> str:
    if "," in value and value.lstrip().lower().startswith("data:image/"):
        return value.split(",", 1)[1]
    return value


def _extract_image(result: Dict[str, Any]) -> Tuple[str, str]:
    data = result.get("data") if isinstance(result.get("data"), dict) else {}

    url = _first_string(
        data.get("image_urls")
        or data.get("image_url")
        or data.get("urls")
        or result.get("image_urls")
    )
    if url.startswith(("http://", "https://")):
        return "url", url

    b64 = _first_string(
        data.get("image_base64")
        or data.get("image_base64s")
        or data.get("images")
        or data.get("b64_json")
        or result.get("image_base64")
    )
    if b64 and not b64.startswith(("http://", "https://")):
        return "base64", _strip_data_uri(b64)

    # Some gateways use a generic data/images list with either URL or b64.
    generic = _first_string(data.get("images") or result.get("data"))
    if generic.startswith(("http://", "https://")):
        return "url", generic
    if generic:
        return "base64", _strip_data_uri(generic)

    return "", ""


class MiniMaxImageGenProvider(ImageGenProvider):
    @property
    def name(self) -> str:
        return "minimax"

    @property
    def display_name(self) -> str:
        return "MiniMax"

    def is_available(self) -> bool:
        return bool((_get_env_value("MINIMAX_API_KEY") or "").strip())

    def list_models(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": model_id,
                "display": meta.get("display", model_id),
                "speed": meta.get("speed", ""),
                "strengths": meta.get("strengths", ""),
                "price": "paid",
            }
            for model_id, meta in _MODELS.items()
        ]

    def default_model(self) -> Optional[str]:
        return DEFAULT_MODEL

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "MiniMax",
            "badge": "paid",
            "tag": "Native MiniMax image generation via image-01",
            "env_vars": [
                {
                    "key": "MINIMAX_API_KEY",
                    "prompt": "MiniMax API key",
                    "url": "https://platform.minimax.io/user-center/basic-information/interface-key",
                },
            ],
        }

    def generate(
        self,
        prompt: str,
        aspect_ratio: str = DEFAULT_ASPECT_RATIO,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        api_key = (_get_env_value("MINIMAX_API_KEY") or "").strip()
        aspect = resolve_aspect_ratio(aspect_ratio)
        if not api_key:
            return error_response(
                error="MINIMAX_API_KEY not set. Get one at https://platform.minimax.io/",
                error_type="missing_api_key",
                provider="minimax",
                aspect_ratio=aspect,
            )

        prompt = (prompt or "").strip()
        if not prompt:
            return error_response(
                error="Prompt is required and must be a non-empty string",
                error_type="invalid_argument",
                provider="minimax",
                aspect_ratio=aspect,
            )

        config = _load_minimax_config()
        model_id, _meta = _resolve_model()
        response_format = _response_format(config)
        payload: Dict[str, Any] = {
            "model": model_id,
            "prompt": prompt[:1500],
            "aspect_ratio": _ASPECT_RATIOS.get(aspect, "16:9"),
            "response_format": response_format,
            "n": int(config.get("n", 1) or 1),
            "prompt_optimizer": bool(config.get("prompt_optimizer", True)),
        }
        if "seed" in config:
            payload["seed"] = config["seed"]
        if "subject_reference" in kwargs:
            payload["subject_reference"] = kwargs["subject_reference"]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        timeout = float(config.get("timeout", 180) or 180)
        endpoint = f"{_base_url(config)}{API_ENDPOINT}"

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
        except requests.Timeout:
            return error_response(
                error="MiniMax image generation timed out",
                error_type="timeout",
                provider="minimax",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except requests.HTTPError as exc:
            resp = exc.response
            status = getattr(resp, "status_code", 0)
            try:
                detail = resp.json()
            except Exception:
                detail = getattr(resp, "text", str(exc))[:300]
            return error_response(
                error=f"MiniMax image generation failed ({status}): {detail}",
                error_type="api_error",
                provider="minimax",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )
        except requests.ConnectionError as exc:
            return error_response(
                error=f"MiniMax connection error: {exc}",
                error_type="connection_error",
                provider="minimax",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        try:
            result = response.json()
        except Exception as exc:
            return error_response(
                error=f"MiniMax returned invalid JSON: {exc}",
                error_type="invalid_response",
                provider="minimax",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        base_resp = result.get("base_resp") or {}
        status_code = base_resp.get("status_code", 0)
        if status_code not in (0, "0", None):
            return error_response(
                error=base_resp.get("status_msg") or f"MiniMax status {status_code}",
                error_type="api_error",
                provider="minimax",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        image_kind, image_value = _extract_image(result)
        if image_kind == "base64":
            try:
                saved_path = save_b64_image(image_value, prefix=f"minimax_{model_id}", extension="jpeg")
            except Exception as exc:
                return error_response(
                    error=f"Could not save MiniMax image to cache: {exc}",
                    error_type="io_error",
                    provider="minimax",
                    model=model_id,
                    prompt=prompt,
                    aspect_ratio=aspect,
                )
            image_ref = str(saved_path)
        elif image_kind == "url":
            image_ref = image_value
        else:
            return error_response(
                error="MiniMax returned no image URL or base64 image data",
                error_type="empty_response",
                provider="minimax",
                model=model_id,
                prompt=prompt,
                aspect_ratio=aspect,
            )

        return success_response(
            image=image_ref,
            model=model_id,
            prompt=prompt,
            aspect_ratio=aspect,
            provider="minimax",
            extra={
                "response_format": response_format,
                "minimax_trace_id": result.get("id") or result.get("trace_id"),
            },
        )


def register(ctx: Any) -> None:
    ctx.register_image_gen_provider(MiniMaxImageGenProvider())
