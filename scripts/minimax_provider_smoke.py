#!/usr/bin/env python3
"""MiniMax provider smoke verifier for Hermes Agent.

This is a lightweight, deterministic counterpart to MiniMax-AI's full
MiniMax-Provider-Verifier. It checks the things Hermes cares about before a
MiniMax endpoint is used as an agent backend:

- basic Anthropic Messages reachability
- non-empty final content (guards reasoning-only/empty-content failures)
- tool-call trigger + argument schema accuracy
- minor-language following
- property-order preservation in tool-call arguments

The script never prints API keys. It supports Hermes MiniMax OAuth, direct
MiniMax API-key providers, and arbitrary Anthropic-compatible MiniMax gateways.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from typing import Any, Callable, Iterable

DEFAULT_MODEL = "MiniMax-M2.7"
DEFAULT_TIMEOUT = 30.0
ANTHROPIC_VERSION = "2023-06-01"


@dataclass
class Credentials:
    provider: str
    api_key: str
    base_url: str
    source: str


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    critical: bool = True


def _redact(text: str) -> str:
    if not text:
        return text
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}…{text[-4:]}"


_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)((?:x-api-key|api[_-]?key|token|secret)[\"'\s:=]+)[A-Za-z0-9._~+/=-]{12,}"),
]


def _sanitize_text(text: Any, creds: Credentials | None = None) -> str:
    """Redact credentials from user-visible diagnostics."""
    sanitized = str(text)
    if creds and creds.api_key:
        sanitized = sanitized.replace(creds.api_key, "[REDACTED]")
    sanitized = re.sub(r"(https?://)([^/@\s:]+):([^/@\s]+)@", r"\1[REDACTED]@", sanitized)
    for pattern in _SECRET_PATTERNS:
        sanitized = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]",
            sanitized,
        )
    return sanitized


def _anthropic_messages_endpoint(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1/messages"):
        return base
    if base.endswith("/anthropic"):
        return f"{base}/v1/messages"
    if base.endswith("/anthropic/v1"):
        return f"{base}/messages"
    if base.endswith("/v1"):
        return f"{base}/messages"
    return f"{base}/anthropic/v1/messages"


def _resolve_credentials(args: argparse.Namespace) -> Credentials:
    provider = args.provider
    if provider == "minimax-oauth":
        try:
            from hermes_cli.auth import resolve_minimax_oauth_runtime_credentials

            creds = resolve_minimax_oauth_runtime_credentials()
        except Exception as exc:
            raise SystemExit(
                "MiniMax OAuth credentials unavailable. Run `hermes model` and "
                "select MiniMax (OAuth), or pass --provider minimax --api-key-env MINIMAX_API_KEY."
            ) from exc
        return Credentials(
            provider="minimax-oauth",
            api_key=str(creds["api_key"]),
            base_url=str(creds["base_url"]).rstrip("/"),
            source="hermes-oauth",
        )

    if args.base_url:
        base_url = args.base_url.rstrip("/")
    elif provider == "minimax-cn":
        base_url = "https://api.minimaxi.com/anthropic"
    else:
        base_url = "https://api.minimax.io/anthropic"

    env_name = args.api_key_env
    if not env_name:
        env_name = "MINIMAX_CN_API_KEY" if provider == "minimax-cn" else "MINIMAX_API_KEY"
    api_key = os.environ.get(env_name)
    if not api_key:
        raise SystemExit(f"Missing API key. Set ${env_name} or pass --api-key-env.")
    return Credentials(provider=provider, api_key=api_key, base_url=base_url, source=f"env:{env_name}")


def _post_messages(
    creds: Credentials,
    payload: dict[str, Any],
    *,
    timeout: float,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    endpoint = _anthropic_messages_endpoint(creds.base_url)
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "content-type": "application/json",
            "anthropic-version": ANTHROPIC_VERSION,
            "x-api-key": creds.api_key,
        },
    )
    open_fn = opener or urllib.request.urlopen
    try:
        with open_fn(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(_sanitize_text(f"HTTP {exc.code}: {raw[:500]}", creds)) from exc
    except Exception as exc:
        raise RuntimeError(_sanitize_text(str(exc), creds)) from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(_sanitize_text(f"Non-JSON response: {raw[:500]}", creds)) from exc


def _content_text(resp: dict[str, Any]) -> str:
    parts: list[str] = []
    for block in resp.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts).strip()


def _tool_blocks(resp: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        block
        for block in (resp.get("content") or [])
        if isinstance(block, dict) and block.get("type") == "tool_use"
    ]


def _check_chat(post: Callable[[dict[str, Any]], dict[str, Any]], model: str) -> CheckResult:
    resp = post({
        "model": model,
        "max_tokens": 64,
        "temperature": 0,
        "messages": [
            {"role": "user", "content": "Reply exactly with HERMES_MINIMAX_OK."}
        ],
    })
    text = _content_text(resp)
    if "HERMES_MINIMAX_OK" in text:
        return CheckResult("chat_content", True, "returned expected sentinel")
    return CheckResult("chat_content", False, f"unexpected text: {text[:120]!r}")


def _check_language(post: Callable[[dict[str, Any]], dict[str, Any]], model: str) -> CheckResult:
    resp = post({
        "model": model,
        "max_tokens": 32,
        "temperature": 0,
        "messages": [
            {"role": "user", "content": "Responde solamente con la palabra española: hola"}
        ],
    })
    text = _content_text(resp).strip().lower().strip('"` .!')
    if text == "hola":
        return CheckResult("language_following", True, "followed Spanish one-word instruction")
    return CheckResult("language_following", False, f"unexpected text: {text[:120]!r}", critical=False)


def _check_tool_schema(post: Callable[[dict[str, Any]], dict[str, Any]], model: str) -> CheckResult:
    resp = post({
        "model": model,
        "max_tokens": 128,
        "temperature": 0,
        "tools": [
            {
                "name": "get_weather",
                "description": "Get weather for a city.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                        "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                    },
                    "required": ["city", "unit"],
                },
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": "Use the get_weather tool for Paris in celsius. Do not answer in prose.",
            }
        ],
    })
    tools = _tool_blocks(resp)
    if not tools:
        return CheckResult("tool_schema", False, "no tool_use block returned")
    block = tools[0]
    args = block.get("input") or {}
    if block.get("name") == "get_weather" and args.get("city") == "Paris" and args.get("unit") == "celsius":
        return CheckResult("tool_schema", True, "triggered get_weather with correct args")
    return CheckResult("tool_schema", False, f"wrong tool call: {block!r}")


def _check_property_order(post: Callable[[dict[str, Any]], dict[str, Any]], model: str) -> CheckResult:
    expected = ["zeta", "alpha", "middle"]
    resp = post({
        "model": model,
        "max_tokens": 128,
        "temperature": 0,
        "tools": [
            {
                "name": "record_order",
                "description": "Record three labeled fields.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "zeta": {"type": "string"},
                        "alpha": {"type": "string"},
                        "middle": {"type": "string"},
                    },
                    "required": expected,
                },
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": "Call record_order with zeta='first', alpha='second', middle='third'.",
            }
        ],
    })
    tools = _tool_blocks(resp)
    if not tools:
        return CheckResult("property_order", False, "no tool_use block returned", critical=False)
    keys = list((tools[0].get("input") or {}).keys())
    if keys[:3] == expected:
        return CheckResult("property_order", True, "tool argument order preserved", critical=False)
    return CheckResult("property_order", False, f"argument order was {keys[:3]!r}", critical=False)


def run_smoke(
    creds: Credentials,
    *,
    model: str,
    timeout: float = DEFAULT_TIMEOUT,
    opener: Callable[..., Any] | None = None,
) -> list[CheckResult]:
    def post(payload: dict[str, Any]) -> dict[str, Any]:
        return _post_messages(creds, payload, timeout=timeout, opener=opener)

    checks = [
        ("chat_content", _check_chat),
        ("tool_schema", _check_tool_schema),
        ("language_following", _check_language),
        ("property_order", _check_property_order),
    ]
    results: list[CheckResult] = []
    for name, check in checks:
        try:
            result = check(post, model)
            result.detail = _sanitize_text(result.detail, creds)
            results.append(result)
        except Exception as exc:
            results.append(CheckResult(name, False, _sanitize_text(str(exc), creds)))
    return results


def _summary(creds: Credentials, model: str, results: Iterable[CheckResult]) -> dict[str, Any]:
    result_list = list(results)
    critical = [r for r in result_list if r.critical]
    return {
        "provider": creds.provider,
        "source": creds.source,
        "base_url": _sanitize_text(creds.base_url, creds),
        "endpoint": _sanitize_text(_anthropic_messages_endpoint(creds.base_url), creds),
        "model": model,
        "api_key": _redact(creds.api_key),
        "passed": all(r.passed for r in critical) if result_list else None,
        "passed_count": sum(1 for r in result_list if r.passed),
        "total_count": len(result_list),
        "checks": [asdict(r) for r in result_list],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="minimax-oauth", help="minimax-oauth, minimax, minimax-cn, or a custom label")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", help="Anthropic-compatible MiniMax base URL")
    parser.add_argument("--api-key-env", help="Environment variable containing the API key/token")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON only")
    parser.add_argument("--dry-run", action="store_true", help="Resolve credentials and print planned endpoint without live calls")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    creds = _resolve_credentials(args)
    if args.dry_run:
        payload = _summary(creds, args.model, [])
        payload["dry_run"] = True
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    results = run_smoke(creds, model=args.model, timeout=args.timeout)
    payload = _summary(creds, args.model, results)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        status = "PASS" if payload["passed"] else "FAIL"
        print(f"MiniMax provider smoke: {status}")
        print(f"provider: {payload['provider']} ({payload['source']})")
        print(f"endpoint: {payload['endpoint']}")
        print(f"model: {payload['model']}")
        for check in payload["checks"]:
            marker = "✓" if check["passed"] else "✗"
            severity = "critical" if check["critical"] else "advisory"
            print(f"{marker} {check['name']} [{severity}]: {check['detail']}")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
