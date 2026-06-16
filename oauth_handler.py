"""
OAuth Handler - Secure store authorization for Shopify, WooCommerce, CJ Dropshipping
"""

import os
import secrets
import httpx
from urllib.parse import urlencode
from typing import Dict, Tuple, Optional

# ========== PLATFORM CONFIG ==========
PLATFORM_CONFIG = {
    "shopify": {
        "auth_url": "https://{shop}.myshopify.com/admin/oauth/authorize",
        "token_url": "https://{shop}.myshopify.com/admin/oauth/access_token",
        "scopes": "read_products,write_products,read_orders,write_orders,read_inventory,write_inventory",
        "client_id": os.environ.get("SHOPIFY_CLIENT_ID", ""),
        "client_secret": os.environ.get("SHOPIFY_CLIENT_SECRET", "")
    },
    "woocommerce": {
        "auth_url": "https://{domain}/oauth/authorize",
        "token_url": "https://{domain}/oauth/token",
        "scopes": "read_write",
        "client_id": os.environ.get("WOO_CLIENT_ID", ""),
        "client_secret": os.environ.get("WOO_CLIENT_SECRET", "")
    },
    "cjdropshipping": {
        "auth_url": "https://developers.cjdropshipping.com/api2.0/v1/authentication/getAccessToken",
        "token_url": "https://developers.cjdropshipping.com/api2.0/v1/authentication/refreshAccessToken",
        "scopes": "all",
        "client_id": os.environ.get("CJ_CLIENT_ID", ""),
        "client_secret": os.environ.get("CJ_CLIENT_SECRET", "")
    }
}

# ========== PARSE STORE URL ==========
def parse_store_url(url: str, platform: str) -> Tuple[str, str]:
    """Extract shop identifier from store URL"""
    url = url.lower().strip().rstrip('/')
    if platform == "shopify":
        if ".myshopify.com" in url:
            parts = url.replace("https://", "").replace("http://", "").split(".")
            return parts[0], url
        return url.split("//")[-1].split(".")[0], url
    elif platform == "woocommerce":
        domain = url.split("//")[-1].split("/")[0]
        return domain, url
    return "unknown", url

# ========== GENERATE OAUTH URL ==========
def generate_oauth_url(platform: str, store_url: str, redirect_uri: str) -> Tuple[str, str]:
    """Generate OAuth authorization URL and state"""
    config = PLATFORM_CONFIG.get(platform)
    if not config:
        return "", ""
    
    shop_id, _ = parse_store_url(store_url, platform)
    state = secrets.token_urlsafe(32)
    
    if platform == "shopify":
        auth_url = config["auth_url"].format(shop=shop_id)
        params = {
            "client_id": config["client_id"],
            "scope": config["scopes"],
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code"
        }
    elif platform == "woocommerce":
        auth_url = config["auth_url"].format(domain=shop_id)
        params = {
            "client_id": config["client_id"],
            "redirect_uri": redirect_uri,
            "state": state,
            "response_type": "code"
        }
    else:
        return "", ""
    
    return f"{auth_url}?{urlencode(params)}", state

# ========== EXCHANGE CODE FOR TOKEN ==========
async def exchange_code_for_token(platform: str, code: str, shop: str, redirect_uri: str = "") -> Dict:
    """Exchange authorization code for access token"""
    config = PLATFORM_CONFIG.get(platform)
    if not config:
        return {"success": False, "error": "Unsupported platform"}
    
    if platform == "shopify":
        token_url = f"https://{shop}/admin/oauth/access_token"
        payload = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code
        }
    elif platform == "woocommerce":
        token_url = config["token_url"].format(domain=shop)
        payload = {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri
        }
    else:
        return {"success": False, "error": "Unsupported platform"}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, json=payload)
            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token", ""),
                    "scope": data.get("scope", ""),
                    "store_id": shop
                }
            return {"success": False, "error": f"Token exchange failed: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
