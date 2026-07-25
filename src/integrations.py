"""Third-party integrations: Shopify, WordPress."""

import logging
from typing import Optional, List, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class ShopifyIntegration:
    def __init__(self, shop_url: str = "", access_token: str = "", api_version: str = "2024-01"):
        self.shop_url = shop_url
        self.access_token = access_token
        self.api_version = api_version
        self.client = httpx.AsyncClient(timeout=30.0)

    def _get_headers(self) -> Dict[str, str]:
        return {"X-Shopify-Access-Token": self.access_token, "Content-Type": "application/json"}

    async def get_products(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.shop_url or not self.access_token:
            return []
        try:
            response = await self.client.get(
                f"{self.shop_url}/admin/api/{self.api_version}/products.json",
                headers=self._get_headers(),
                params={"limit": limit},
            )
            response.raise_for_status()
            return response.json().get("products", [])
        except:
            return []

    async def close(self):
        await self.client.aclose()


class WordPressIntegration:
    def __init__(self, site_url: str = "", consumer_key: str = "", consumer_secret: str = ""):
        self.site_url = site_url
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.client = httpx.AsyncClient(timeout=30.0)

    def _get_auth(self) -> tuple:
        return (self.consumer_key, self.consumer_secret)

    async def get_products(self, page: int = 1, per_page: int = 20) -> List[Dict[str, Any]]:
        if not self.site_url:
            return []
        try:
            response = await self.client.get(
                f"{self.site_url}/wp-json/wc/v3/products",
                auth=self._get_auth(),
                params={"page": page, "per_page": per_page},
            )
            response.raise_for_status()
            return response.json()
        except:
            return []

    async def close(self):
        await self.client.aclose()