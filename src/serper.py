"""Serper API client."""

import logging
from typing import Optional, List, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class SerperClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://google.serper.dev"
        self.client = httpx.AsyncClient(timeout=30.0)

    def _get_headers(self) -> Dict[str, str]:
        if not self.api_key:
            return {}
        return {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json",
        }

    async def search(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("Serper API key not set")
            return []
        payload = {"q": query, "num": num_results}
        try:
            response = await self.client.post(
                f"{self.base_url}/search",
                headers=self._get_headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            results = []
            for item in data.get("organic", [])[:num_results]:
                results.append({
                    "title": item.get("title"),
                    "link": item.get("link"),
                    "snippet": item.get("snippet"),
                })
            return results
        except httpx.HTTPError as e:
            logger.error(f"Serper search failed: {e}")
            return []

    async def search_trending(self, topic: str = "tiktok") -> List[str]:
        query = f"trending TikTok hashtags {topic} 2026"
        results = await self.search(query)
        hashtags = []
        for result in results:
            snippet = result.get("snippet", "")
            words = snippet.split()
            for word in words:
                if word.startswith("#") and len(word) > 2:
                    hashtags.append(word)
        return list(set(hashtags))[:10]

    async def close(self):
        await self.client.aclose()