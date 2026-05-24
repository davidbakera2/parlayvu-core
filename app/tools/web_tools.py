# app/tools/web_tools.py
"""
Web search and URL fetching for Nathan's live meeting tool set.

web_search  — searches the web via Tavily (TAVILY_API_KEY required)
fetch_url   — fetches any public URL as clean markdown via Jina Reader (no API key needed)

Both work for LinkedIn profiles, company sites, social media, news, and anything
publicly accessible on the web.

Environment variables:
    TAVILY_API_KEY  — get a free key at https://tavily.com (required for web_search)
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger("parlayvu.tools.web")

_JINA_BASE = "https://r.jina.ai"
_TAVILY_BASE = "https://api.tavily.com"

# Characters returned per URL fetch — Tavus reads aloud, so we cap context
_MAX_FETCH_CHARS = 8_000
# Results returned per search
_MAX_SEARCH_RESULTS = 5


def _tavily_key() -> str:
    return os.getenv("TAVILY_API_KEY", "")


async def web_search(query: str, *, max_results: int = _MAX_SEARCH_RESULTS) -> dict[str, Any]:
    """
    Search the web for current information. Returns titles, URLs, and snippets.

    Good for: market research, competitor analysis, industry trends, campaign
    benchmarks, finding company info, recent news about a brand or person.
    """
    api_key = _tavily_key()
    if not api_key:
        return {
            "error": "TAVILY_API_KEY is not configured. "
                     "Get a free key at https://tavily.com and set it as an Azure secret.",
            "results": [],
        }

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
        "include_answer": True,
        "include_raw_content": False,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(f"{_TAVILY_BASE}/search", json=payload)
            resp.raise_for_status()
            data = resp.json()

        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", "")[:600],
                "published_date": r.get("published_date"),
            }
            for r in data.get("results", [])
        ]

        return {
            "query": query,
            "answer": data.get("answer", ""),
            "results": results,
        }

    except httpx.HTTPStatusError as exc:
        logger.warning("Tavily search failed: %s", exc)
        return {"error": f"Search failed: {exc.response.status_code}", "results": []}
    except Exception as exc:
        logger.exception("Unexpected error in web_search")
        return {"error": str(exc), "results": []}


async def fetch_url(url: str) -> dict[str, Any]:
    """
    Fetch and read the content of any public URL as clean markdown.

    Works for: LinkedIn profiles, company websites, social media pages,
    news articles, landing pages, competitor sites.

    LinkedIn tip: pass the full profile URL, e.g.
    https://www.linkedin.com/in/username — returns the public profile as text.

    Uses Jina Reader (r.jina.ai) which extracts clean, AI-readable text
    from any webpage, bypassing most formatting noise.
    """
    # Strip dangerous schemes
    lowered = url.strip().lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        return {"error": f"Only http/https URLs are supported, got: {url}"}

    jina_url = f"{_JINA_BASE}/{url}"

    headers = {
        "Accept": "text/plain",
        "X-Return-Format": "markdown",
        # Return only the main content, skip nav/footer noise
        "X-Remove-Selector": "nav, footer, .nav, .footer, #nav, #footer",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(jina_url, headers=headers)
            resp.raise_for_status()

        content = resp.text[:_MAX_FETCH_CHARS]
        truncated = len(resp.text) > _MAX_FETCH_CHARS

        return {
            "url": url,
            "content": content,
            "truncated": truncated,
            "char_count": len(content),
        }

    except httpx.HTTPStatusError as exc:
        logger.warning("Jina fetch failed for %s: %s", url, exc)
        return {"url": url, "error": f"Fetch failed: {exc.response.status_code}"}
    except httpx.TimeoutException:
        return {"url": url, "error": "Request timed out after 30 seconds."}
    except Exception as exc:
        logger.exception("Unexpected error fetching %s", url)
        return {"url": url, "error": str(exc)}
