"""Brave Search API web search provider.

Brave Search's Data-for-Search API exposes web search results after signing up
at https://brave.com/search/api/.  This provider implements
``WebSearchProvider`` only — the Data-for-Search endpoint returns search
results, it does not extract/crawl arbitrary URLs.

Configuration::

    # ~/.hermes/.env
    BRAVE_SEARCH_API_KEY=your-subscription-token

    # ~/.hermes/config.yaml
    web:
      search_backend: "brave"
      extract_backend: "firecrawl"    # pair with an extract provider if needed

The API uses the ``X-Subscription-Token`` header.  See the Brave dashboard for
the current quota attached to the subscription token.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

from tools.web_providers.base import WebSearchProvider

logger = logging.getLogger(__name__)

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider(WebSearchProvider):
    """Search via the Brave Search API.

    Requires ``BRAVE_SEARCH_API_KEY`` to be set. The value is passed as the
    ``X-Subscription-Token`` header. No extract capability — pair with
    Firecrawl/Tavily/Exa/Parallel when you also need ``web_extract``.
    """

    def provider_name(self) -> str:
        return "brave"

    def is_configured(self) -> bool:
        """Return True when ``BRAVE_SEARCH_API_KEY`` is set to a non-empty value."""
        return bool(os.getenv("BRAVE_SEARCH_API_KEY", "").strip())

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Execute a search against the Brave Search API.

        Returns normalized results::

            {
                "success": True,
                "data": {
                    "web": [
                        {
                            "title": str,
                            "url": str,
                            "description": str,
                            "position": int,
                        },
                        ...
                    ]
                }
            }

        On failure returns ``{"success": False, "error": str}``.
        """
        import httpx

        api_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
        if not api_key:
            return {"success": False, "error": "BRAVE_SEARCH_API_KEY is not set"}

        # Brave's `count` is capped at 20.
        count = max(1, min(int(limit), 20))

        try:
            resp = httpx.get(
                _BRAVE_ENDPOINT,
                params={"q": query, "count": count},
                headers={
                    "X-Subscription-Token": api_key,
                    "Accept": "application/json",
                },
                timeout=15,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning("Brave Search HTTP error: %s", exc)
            return {
                "success": False,
                "error": f"Brave Search returned HTTP {exc.response.status_code}",
            }
        except httpx.RequestError as exc:
            logger.warning("Brave Search request error: %s", exc)
            return {"success": False, "error": f"Could not reach Brave Search: {exc}"}

        try:
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Brave Search response parse error: %s", exc)
            return {"success": False, "error": "Could not parse Brave Search response as JSON"}

        raw_results = (data.get("web") or {}).get("results", []) or []
        truncated = raw_results[:limit]

        web_results = [
            {
                "title": str(r.get("title", "")),
                "url": str(r.get("url", "")),
                "description": str(r.get("description", "")),
                "position": i + 1,
            }
            for i, r in enumerate(truncated)
        ]

        logger.info(
            "Brave Search '%s': %d results (from %d raw, limit %d)",
            query,
            len(web_results),
            len(raw_results),
            limit,
        )

        return {"success": True, "data": {"web": web_results}}


# Backward-compatible alias for old imports/configs that used the original
# free-tier-specific name.  The API surface is the same for paid subscriptions;
# the canonical backend name is now ``brave``.
BraveFreeSearchProvider = BraveSearchProvider
