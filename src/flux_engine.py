"""Flux Engine — High-Speed Image Generation."""

import asyncio
import logging
from typing import Optional, Tuple, List, Dict
import httpx

logger = logging.getLogger(__name__)


class FluxEngine:
    def __init__(self):
        self.base_url = "https://image.pollinations.ai"
        self.client = httpx.AsyncClient(timeout=120.0)

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024,
                       model: str = "flux", seed: Optional[int] = None) -> Tuple[bytes, str]:
        params = {"width": width, "height": height, "model": model}
        if seed is not None:
            params["seed"] = seed
        prompt_encoded = prompt.replace(" ", "+")
        url = f"{self.base_url}/prompt/{prompt_encoded}"
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "image/png")
        except httpx.HTTPError as e:
            logger.error(f"Flux generation failed: {e}")
            raise

    async def close(self):
        await self.client.aclose()


_flux_engine = None


def get_flux_engine():
    global _flux_engine
    if _flux_engine is None:
        _flux_engine = FluxEngine()
    return _flux_engine