"""Pollinations AI client."""

import asyncio
import logging
from typing import Optional, Tuple, List, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class PollinationsClient:
    def __init__(self):
        self.image_base_url = "https://image.pollinations.ai"
        self.text_base_url = "https://text.pollinations.ai"
        self.client = httpx.AsyncClient(timeout=120.0)

    async def generate_image(self, prompt: str, width: int = 1024, height: int = 1024,
                             model: str = "flux", seed: Optional[int] = None,
                             nologo: bool = True) -> Tuple[bytes, str]:
        params = {"width": width, "height": height, "model": model,
                  "nologo": "true" if nologo else "false"}
        if seed is not None:
            params["seed"] = seed
        prompt_encoded = prompt.replace(" ", "+")
        url = f"{self.image_base_url}/prompt/{prompt_encoded}"
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.content, response.headers.get("content-type", "image/png")
        except httpx.HTTPError as e:
            logger.error(f"Image generation failed: {e}")
            raise

    async def generate_bulk_images(self, prompt: str, variations: int = 4,
                                   width: int = 1024, height: int = 1024) -> List[bytes]:
        tasks = []
        for i in range(variations):
            tasks.append(self.generate_image(f"{prompt} variation {i+1}", width, height,
                                             seed=i + 1))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        images = []
        for result in results:
            if not isinstance(result, Exception):
                images.append(result[0])
        return images

    async def close(self):
        await self.client.aclose()