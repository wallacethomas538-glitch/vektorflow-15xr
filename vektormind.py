"""VektorMind capabilities for the command-center chat.

Two capabilities, both honest about availability:

1. Agent dispatch parsing. The commander can name any of the 15 agents in
   plain language ("dispatch Rook to check inventory", "@Scout find
   trending products", "ask Echo to draft a reply") and VektorMind hands
   the task to that agent through the same run path as
   /api/agents/{name}/chat, then presents the agent's real answer,
   attributed to the agent.

2. Web browsing. Search runs on whichever provider key is configured in
   the backend environment (Brave first, then Tavily) — provider-flexible,
   never Brave-locked. Reading a page uses WebScraping.AI when configured,
   otherwise a direct server-side fetch. When nothing is configured, the
   capability reports itself unavailable instead of fabricating results.
"""
from __future__ import annotations

import html as _html
import re
from typing import Any

import httpx

import external_tools

try:
    from vektorflow_agents import AGENT_ROLES
    _ROSTER = [name for name, _desc in AGENT_ROLES]
except Exception:  # pragma: no cover - roster fallback if agents module shifts
    _ROSTER = [
        "Scout", "Smaug", "Architect", "DaVinci", "Rook", "Aegis", "Arbiter",
        "Sentinel", "Echo", "Cerebrum", "ViralDet", "Shadow", "Bundler",
        "Pivot", "Oracle",
    ]

_NAME_MAP = {name.lower(): name for name in _ROSTER}
# Longer names first so "viraldet" wins over any shorter prefix collisions.
_NAMES_RE = "|".join(sorted((re.escape(n) for n in _ROSTER), key=len, reverse=True))

_DISPATCH_PATTERNS = [
    re.compile(rf"^@({_NAMES_RE})\b[:\s,]+(.+)$", re.IGNORECASE | re.DOTALL),
    re.compile(
        rf"^(?:dispatch|send|run|deploy|assign|task)\s+({_NAMES_RE})\b\s*(?:to\s+|:\s*)?(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        rf"^(?:ask|have|tell|get)\s+({_NAMES_RE})\b\s*(?:to\s+)?(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
]

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")

MAX_PAGE_CHARS = 6000


def roster() -> list[str]:
    return list(_ROSTER)


def resolve_agent_name(name: str | None) -> str | None:
    if not name:
        return None
    return _NAME_MAP.get(name.strip().lower())


def parse_dispatch(message: str) -> dict[str, Any] | None:
    """Return {"agent": canonical, "task": str} when the commander names an
    agent to dispatch; None when the message is for VektorMind itself."""
    text = (message or "").strip()
    if not text:
        return None
    # Allow "VektorMind, dispatch Rook to ..." style address.
    text = re.sub(r"^(?:vektormind|commander)\b[:\s,]+", "", text, flags=re.IGNORECASE)
    for pattern in _DISPATCH_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        agent = resolve_agent_name(m.group(1))
        task = (m.group(2) or "").strip()
        if agent and task:
            return {"agent": agent, "task": task}
    return None


def extract_urls(text: str) -> list[str]:
    urls = []
    for raw in _URL_RE.findall(text or ""):
        urls.append(raw.rstrip(".,;:!?"))
    return urls


def configured_search_providers() -> list[str]:
    """Search providers whose env key is set, in VektorMind's try-order.
    Serper (Google results) first when configured, then Brave, then Tavily."""
    status = {row["provider"]: row for row in external_tools.tool_status()}
    order = []
    if status.get("Serper (Google)", {}).get("configured"):
        order.append("serper")
    if status.get("Brave Search API", {}).get("configured"):
        order.append("brave")
    if status.get("Tavily", {}).get("configured"):
        order.append("tavily")
    return order


async def web_search(query: str, count: int = 5) -> dict[str, Any]:
    """Provider-flexible web search. Brave first, then Tavily; whichever is
    configured. Raises RuntimeError with an honest message when no provider
    is configured or every configured provider fails."""
    providers = configured_search_providers()
    if not providers:
        raise RuntimeError(
            "Web search is not configured on the backend "
            "(no BRAVE_SEARCH_API_KEY or TAVILY_API_KEY in the environment)."
        )
    errors: list[str] = []
    for provider in providers:
        try:
            if provider == "serper":
                data = await external_tools.serper_search(query, count=count)
                raw = data.get("results") or []
            elif provider == "brave":
                data = await external_tools.brave_search(query, count=count)
                raw = data.get("results") or []
            else:
                data = await external_tools.tavily_search(query, max_results=count)
                raw = data.get("results") or []
            results = []
            for item in raw[:count]:
                results.append({
                    "title": item.get("title") or "",
                    "url": item.get("url") or "",
                    "description": item.get("description") or item.get("content") or "",
                })
            return {"provider": provider, "query": query, "results": results}
        except Exception as exc:  # try the next configured provider
            errors.append(f"{provider}: {exc}")
    raise RuntimeError("Web search failed on all configured providers (" + "; ".join(errors) + ").")


def _html_to_text(raw: str) -> str:
    """Crude but dependable HTML -> readable text (no external parser)."""
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw or "")
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|li|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


async def browse_url(url: str, question: str | None = None) -> dict[str, Any]:
    """Read a web page and return its text. WebScraping.AI when configured,
    otherwise a direct server-side fetch. Raises on unusable URLs."""
    url = (url or "").strip()
    if not re.match(r"^https?://[^\s/]+", url, re.IGNORECASE):
        raise ValueError(f"VektorMind can only browse http(s) URLs, got: {url!r}")
    status = {row["provider"]: row for row in external_tools.tool_status()}
    if status.get("WebScraping.AI", {}).get("configured"):
        data = await external_tools.webscraping_ai(url, question)
        content = data.get("content") or ""
        if "<" in content[:2000] and ">" in content[:2000]:
            content = _html_to_text(content)
        return {
            "provider": "webscraping_ai",
            "url": url,
            "content": content[:MAX_PAGE_CHARS],
        }
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; VektorFlow/1.1; +https://vektorflow-15xr-1.onrender.com)",
        "Accept": "text/html, text/plain;q=0.9, */*;q=0.5",
    }
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    raw = response.text or ""
    content = _html_to_text(raw) if ("html" in content_type or "<html" in raw[:2000].lower()) else raw
    return {
        "provider": "direct_fetch",
        "url": str(response.url),
        "content": content[:MAX_PAGE_CHARS],
    }


_WEB_INTENT = re.compile(
    r"(?i)\b("
    r"weather|forecast|temperature outside|rain|snow|storm|hurricane|"
    r"news|headline|latest|breaking|just announced|"
    r"stock price|share price|price of|how much is|bitcoin|"
    r"score|who won|standings|game tonight|"
    r"use the internet|search the web|search for|look up|find out|google it|"
    r"current|recently|right now|today'?s|this week|this month|2025|2026"
    r")\b"
)


def needs_web(message: str) -> bool:
    """True when the message asks for live/current external information —
    the cases where a chat model without web context would fall back to
    stale training data or deny it can browse. Conservative on purpose:
    store ops and agent dispatch never route through here."""
    text = (message or "").strip()
    if not text:
        return False
    if extract_urls(text):
        return False  # browsing path handles links
    return bool(_WEB_INTENT.search(text))
