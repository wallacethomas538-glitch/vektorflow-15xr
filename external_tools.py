"""Optional external tools selected from the free-for.dev catalog.

These adapters are provider-specific but dormant unless their environment key is
configured. They keep credentials server-side and return normalized JSON-safe
results for VektorFlow agents.
"""
from __future__ import annotations

import os
from typing import Any

import httpx


TOOL_CATALOG = {
    "brave_search": {
        "provider": "Brave Search API",
        "category": "search",
        "env": "BRAVE_SEARCH_API_KEY",
        "free_for_dev": True,
        "description": "Web, news, image and LLM-context search for research and competitive intelligence.",
    },
    "tavily_search": {
        "provider": "Tavily",
        "category": "research",
        "env": "TAVILY_API_KEY",
        "free_for_dev": True,
        "description": "Agent-oriented web search, extraction and research grounding.",
    },
    "apify_actor": {
        "provider": "Apify",
        "category": "scraping",
        "env": "APIFY_API_TOKEN",
        "free_for_dev": True,
        "description": "Run public or private Apify Actors for web data extraction and automation.",
    },
    "webscraping_ai": {
        "provider": "WebScraping.AI",
        "category": "scraping",
        "env": "WEBSCRAPING_AI_API_KEY",
        "free_for_dev": True,
        "description": "Fetch/render web pages for competitive research and content extraction.",
    },
}


def tool_status() -> list[dict[str, Any]]:
    return [
        {**meta, "configured": bool(os.getenv(meta["env"], "").strip())}
        for meta in TOOL_CATALOG.values()
    ]


def _require(name: str) -> str:
    env_name = TOOL_CATALOG[name]["env"]
    value = os.getenv(env_name, "").strip()
    if not value:
        raise RuntimeError(f"{TOOL_CATALOG[name]['provider']} is not configured ({env_name}).")
    return value


async def brave_search(query: str, count: int = 10) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ValueError("query is required")
    token = _require("brave_search")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": token, "Accept": "application/json"},
            params={"q": query, "country": "US", "search_lang": "en", "count": max(1, min(count, 20))},
        )
    response.raise_for_status()
    data = response.json()
    results = []
    for item in data.get("web", {}).get("results", [])[:count]:
        results.append({
            "title": item.get("title"),
            "url": item.get("url"),
            "description": item.get("description"),
        })
    return {"provider": "brave", "query": query, "results": results}


async def tavily_search(query: str, max_results: int = 10) -> dict[str, Any]:
    query = query.strip()
    if not query:
        raise ValueError("query is required")
    api_key = _require("tavily_search")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.tavily.com/search",
            headers={"Content-Type": "application/json"},
            json={"api_key": api_key, "query": query, "max_results": max(1, min(max_results, 10))},
        )
    response.raise_for_status()
    data = response.json()
    return {
        "provider": "tavily",
        "query": query,
        "results": data.get("results", []),
        "answer": data.get("answer"),
    }


async def apify_actor(actor_id: str, run_input: dict[str, Any] | None = None) -> dict[str, Any]:
    actor_id = actor_id.strip()
    if not actor_id:
        raise ValueError("actor_id is required")
    token = _require("apify_actor")
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"https://api.apify.com/v2/actors/{actor_id}/run-sync-get-dataset-items",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=run_input or {},
        )
    response.raise_for_status()
    data = response.json()
    return {"provider": "apify", "actor_id": actor_id, "items": data if isinstance(data, list) else data.get("data", data)}


async def webscraping_ai(url: str, question: str | None = None) -> dict[str, Any]:
    url = url.strip()
    if not url:
        raise ValueError("url is required")
    api_key = _require("webscraping_ai")
    endpoint = "https://api.webscraping.ai/ai/question" if question else "https://api.webscraping.ai/html"
    params = {"api_key": api_key, "url": url}
    if question:
        params["question"] = question
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.get(endpoint, params=params)
    response.raise_for_status()
    return {
        "provider": "webscraping_ai",
        "url": url,
        "question": question,
        "content": response.text,
    }
