"""
Store Manager - Handles CJ Dropshipping and other store integrations
"""

import os
import httpx
from typing import Dict, List, Optional

CJ_MCP_URL = os.environ.get("CJ_MCP_URL", "https://api-mcp-7ojz.onrender.com")

async def search_cj_products(keyword: str, api_key: str = None) -> List[Dict]:
    """Search products on CJ Dropshipping"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            response = await client.get(
                f"{CJ_MCP_URL}/search",
                params={"keyword": keyword},
                headers=headers
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("products", [])
            return []
    except Exception as e:
        print(f"CJ search error: {e}")
        return []

async def get_cj_product_details(product_id: str) -> Optional[Dict]:
    """Get detailed product info from CJ"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{CJ_MCP_URL}/product/{product_id}")
            if response.status_code == 200:
                return response.json()
            return None
    except Exception as e:
        print(f"CJ product error: {e}")
        return None

async def get_cj_inventory(api_key: str, api_secret: str) -> List[Dict]:
    """Fetch inventory from CJ Dropshipping"""
    # This would call CJ's actual inventory API
    # Placeholder - implement based on CJ API docs
    return []
