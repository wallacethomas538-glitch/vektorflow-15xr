"""
VektorFlow 15xr - Store Manager
Multi-platform store connection, product sync, and inventory management.
"""

import os
import json
import logging
import hashlib
import hmac
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from urllib.parse import urlparse, quote

import httpx
from pydantic import BaseModel, ValidationError

from database import (
    get_user_stores,
    connect_store as db_connect_store,
    save_memory,
    get_memory,
    add_task_history,
    update_task_result
)

logger = logging.getLogger("vektorflow")

# ============ CONFIGURATION ============
CJ_API_KEY = os.environ.get("CJ_API_KEY")
CJ_API_SECRET = os.environ.get("CJ_API_SECRET")
SHOPIFY_API_KEY = os.environ.get("SHOPIFY_API_KEY")
SHOPIFY_API_SECRET = os.environ.get("SHOPIFY_API_SECRET")
WOOCOMMERCE_API_KEY = os.environ.get("WOOCOMMERCE_API_KEY")
WOOCOMMERCE_API_SECRET = os.environ.get("WOOCOMMERCE_API_SECRET")

# ============ MODELS ============

class StoreCredentials(BaseModel):
    """Store connection credentials."""
    platform: str  # shopify, woocommerce, bigcommerce, cj
    store_url: str
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None
    shop_id: Optional[str] = None

class Product(BaseModel):
    """Product data model."""
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    price: float
    compare_at_price: Optional[float] = None
    cost_price: Optional[float] = None
    sku: Optional[str] = None
    barcode: Optional[str] = None
    weight: Optional[float] = None
    weight_unit: str = "kg"
    quantity: int = 0
    images: List[str] = []
    variants: List[Dict[str, Any]] = []
    tags: List[str] = []
    category: Optional[str] = None
    supplier: Optional[str] = None
    supplier_url: Optional[str] = None
    platform: str = "general"
    platform_id: Optional[str] = None

class Order(BaseModel):
    """Order data model."""
    id: Optional[str] = None
    order_number: str
    customer_email: str
    customer_name: str
    total_price: float
    subtotal_price: float
    tax_price: float = 0
    shipping_price: float = 0
    currency: str = "USD"
    status: str = "pending"
    line_items: List[Dict[str, Any]] = []
    shipping_address: Dict[str, Any] = {}
    billing_address: Dict[str, Any] = {}
    created_at: datetime = datetime.now()
    platform: str = "general"
    platform_id: Optional[str] = None

# ============ CJ DROPSHIPPING API ============

class CJAPI:
    """CJ Dropshipping API 2.0 wrapper with token authentication."""
    BASE_URL = "https://developers.cjdropshipping.com/api2.0/v1"

    def __init__(self, api_key: str = None, api_secret: str = None, access_token: str = None):
        self.api_key = api_key or CJ_API_KEY
        self.api_secret = api_secret or CJ_API_SECRET
        self.access_token = access_token or os.environ.get("CJ_ACCESS_TOKEN", "")
        self.refresh_token = os.environ.get("CJ_REFRESH_TOKEN", "")

    async def _get_access_token(self) -> Optional[str]:
        if self.access_token:
            return self.access_token
        if not self.api_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/authentication/getAccessToken",
                    json={"apiKey": self.api_key},
                    headers={"Content-Type": "application/json"},
                )
            response.raise_for_status()
            data = response.json()
            token = (data.get("data") or {}).get("accessToken")
            if token:
                self.access_token = token
                return token
            logger.error("CJ authentication returned no access token: %s", data.get("message", "unknown error"))
        except Exception as exc:
            logger.error("CJ authentication failed: %s", exc)
        return None

    async def _get(self, path: str, params: Dict[str, Any]) -> Dict:
        token = await self._get_access_token()
        if not token:
            return {"success": False, "error": "CJ API credentials are not configured.", "products": []}
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}{path}",
                    params=params,
                    headers={"CJ-Access-Token": token},
                )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            logger.error("CJ API request failed: %s", exc)
            return {"success": False, "error": str(exc)}

    async def search_products(self, keyword: str, page: int = 1, limit: int = 20) -> Dict:
        """Search CJ's current product catalog using Product List V2."""
        keyword = (keyword or "").strip()
        if not keyword:
            return {"success": False, "error": "Keyword required", "products": []}
        limit = max(1, min(int(limit), 100))
        data = await self._get("/product/listV2", {"page": max(1, int(page)), "size": limit, "keyWord": keyword})
        if data.get("success") is False:
            return {"success": False, "error": data.get("message") or data.get("error") or "CJ product search failed", "products": []}
        payload = data.get("data") or {}
        products = payload.get("content") or payload.get("list") or []
        return {
            "success": True,
            "products": products,
            "total": payload.get("totalRecords", payload.get("total", len(products))),
        }

    async def get_product_details(self, product_id: str) -> Dict:
        """Get full product details from CJ by product ID."""
        product_id = (product_id or "").strip()
        if not product_id:
            return {"success": False, "error": "Product ID required"}
        data = await self._get("/product/query", {"pid": product_id})
        if data.get("success") is False:
            return {"success": False, "error": data.get("message") or data.get("error") or "CJ product lookup failed"}
        return {"success": True, "product": data.get("data") or {}}

    async def create_order(self, order_data: Dict) -> Dict:
        """CJ order creation is intentionally not mapped to the deprecated legacy endpoint."""
        return {"success": False, "error": "CJ order creation requires the API 2.0 order workflow and has not been enabled here."}

    async def track_order(self, order_id: str) -> Dict:
        """Order tracking requires a CJ API 2.0 order/tracking workflow."""
        return {"success": False, "error": "CJ order tracking requires the API 2.0 order workflow and has not been enabled here."}

# ============ SHOPIFY API ============

class ShopifyAPI:
    """Shopify API wrapper."""
    
    def __init__(self, store_url: str, api_key: str = None, api_secret: str = None, access_token: str = None):
        self.store_url = store_url.rstrip("/")
        self.api_key = api_key or SHOPIFY_API_KEY
        self.api_secret = api_secret or SHOPIFY_API_SECRET
        self.access_token = access_token
        self.client = httpx.AsyncClient(timeout=30.0)
    
    def _headers(self) -> Dict:
        """Get request headers."""
        if self.access_token:
            return {
                "X-Shopify-Access-Token": self.access_token,
                "Content-Type": "application/json"
            }
        elif self.api_key and self.api_secret:
            # Basic auth for legacy API
            import base64
            auth = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
            return {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json"
            }
        return {}
    
    async def get_products(self, limit: int = 50) -> Dict:
        """Get products from Shopify store."""
        try:
            response = await self.client.get(
                f"{self.store_url}/admin/api/2023-10/products.json",
                params={"limit": limit},
                headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "products": data.get("products", [])
            }
        except httpx.HTTPError as e:
            logger.error(f"Shopify get products error: {e}")
            return {"success": False, "error": str(e), "products": []}
    
    async def get_products_count(self) -> int:
        """Get total product count from Shopify store (not page size)."""
        try:
            response = await self.client.get(
                f"{self.store_url}/admin/api/2023-10/products/count.json",
                headers=self._headers()
            )
            response.raise_for_status()
            return int(response.json().get("count", 0))
        except (httpx.HTTPError, ValueError, TypeError) as e:
            logger.error(f"Shopify product count error: {e}")
            return 0

    async def get_orders_count(self) -> int:
        """Get total order count from Shopify store (not page size)."""
        try:
            response = await self.client.get(
                f"{self.store_url}/admin/api/2023-10/orders/count.json",
                headers=self._headers()
            )
            response.raise_for_status()
            return int(response.json().get("count", 0))
        except (httpx.HTTPError, ValueError, TypeError) as e:
            logger.error(f"Shopify order count error: {e}")
            return 0

    async def create_product(self, product: Dict) -> Dict:
        """Create a product on Shopify."""
        try:
            response = await self.client.post(
                f"{self.store_url}/admin/api/2023-10/products.json",
                json={"product": product},
                headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "product": data.get("product", {})
            }
        except httpx.HTTPError as e:
            logger.error(f"Shopify create product error: {e}")
            return {"success": False, "error": str(e)}
    
    async def update_product(self, product_id: str, product: Dict) -> Dict:
        """Update a product on Shopify."""
        try:
            response = await self.client.put(
                f"{self.store_url}/admin/api/2023-10/products/{product_id}.json",
                json={"product": product},
                headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "product": data.get("product", {})
            }
        except httpx.HTTPError as e:
            logger.error(f"Shopify update product error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_orders(self, limit: int = 50) -> Dict:
        """Get orders from Shopify store."""
        try:
            response = await self.client.get(
                f"{self.store_url}/admin/api/2023-10/orders.json",
                params={"limit": limit, "status": "any"},
                headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
            return {
                "success": True,
                "orders": data.get("orders", [])
            }
        except httpx.HTTPError as e:
            logger.error(f"Shopify get orders error: {e}")
            return {"success": False, "error": str(e), "orders": []}

# ============ WOOCOMMERCE API ============

class WooCommerceAPI:
    """WooCommerce API wrapper."""
    
    def __init__(self, store_url: str, api_key: str = None, api_secret: str = None):
        self.store_url = store_url.rstrip("/")
        self.api_key = api_key or WOOCOMMERCE_API_KEY
        self.api_secret = api_secret or WOOCOMMERCE_API_SECRET
        self.client = httpx.AsyncClient(timeout=30.0)
    
    def _headers(self) -> Dict:
        """Get request headers."""
        import base64
        if self.api_key and self.api_secret:
            auth = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode()
            return {"Authorization": f"Basic {auth}"}
        return {}
    
    async def get_products(self, limit: int = 50) -> Dict:
        """Get products from WooCommerce store."""
        try:
            response = await self.client.get(
                f"{self.store_url}/wp-json/wc/v3/products",
                params={"per_page": limit},
                headers=self._headers()
            )
            response.raise_for_status()
            return {
                "success": True,
                "products": response.json()
            }
        except httpx.HTTPError as e:
            logger.error(f"WooCommerce get products error: {e}")
            return {"success": False, "error": str(e), "products": []}
    
    async def create_product(self, product: Dict) -> Dict:
        """Create a product on WooCommerce."""
        try:
            response = await self.client.post(
                f"{self.store_url}/wp-json/wc/v3/products",
                json=product,
                headers=self._headers()
            )
            response.raise_for_status()
            return {
                "success": True,
                "product": response.json()
            }
        except httpx.HTTPError as e:
            logger.error(f"WooCommerce create product error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_orders(self, limit: int = 50) -> Dict:
        """Get orders from WooCommerce store."""
        try:
            response = await self.client.get(
                f"{self.store_url}/wp-json/wc/v3/orders",
                params={"per_page": limit},
                headers=self._headers()
            )
            response.raise_for_status()
            return {
                "success": True,
                "orders": response.json()
            }
        except httpx.HTTPError as e:
            logger.error(f"WooCommerce get orders error: {e}")
            return {"success": False, "error": str(e), "orders": []}

# ============ STORE CONNECTION MANAGER ============

class StoreManager:
    """Manages store connections and operations."""
    
    def __init__(self, email: str = None):
        self.email = email
        self.stores = []
        if email:
            self.load_stores()
    
    def load_stores(self):
        """Load stores from database."""
        if not self.email:
            return
        self.stores = db_get_user_stores(self.email)
    
    def get_store(self, platform: str, store_url: str = None) -> Optional[Dict]:
        """Get a specific store connection."""
        for store in self.stores:
            if store.get("platform") == platform:
                if store_url and store.get("store_url") != store_url:
                    continue
                return store
        return None
    
    async def connect_store(self, platform: str, store_url: str, credentials: Dict) -> Dict:
        """
        Connect a new store.
        
        Args:
            platform: shopify, woocommerce, bigcommerce, cj
            store_url: Store URL
            credentials: API credentials
        
        Returns:
            Connection result
        """
        try:
            # Validate platform
            if platform not in ["shopify", "woocommerce", "bigcommerce", "cj"]:
                return {"success": False, "error": f"Unsupported platform: {platform}"}
            
            # Test connection
            test_result = await self.test_connection(platform, store_url, credentials)
            if not test_result.get("success"):
                return test_result
            
            # Save to database
            result = db_connect_store(
                email=self.email,
                platform=platform,
                store_url=store_url
            )
            
            # Save credentials
            if credentials.get("api_key"):
                save_memory(
                    self.email,
                    f"store_{platform}_api_key",
                    credentials["api_key"]
                )
            if credentials.get("api_secret"):
                save_memory(
                    self.email,
                    f"store_{platform}_api_secret",
                    credentials["api_secret"]
                )
            if credentials.get("access_token"):
                save_memory(
                    self.email,
                    f"store_{platform}_access_token",
                    credentials["access_token"]
                )
            
            # Reload stores
            self.load_stores()
            
            return {
                "success": True,
                "message": f"Successfully connected to {platform}",
                "platform": platform,
                "store_url": store_url
            }
        except Exception as e:
            logger.error(f"Connect store error: {e}")
            return {"success": False, "error": str(e)}
    
    async def test_connection(self, platform: str, store_url: str, credentials: Dict) -> Dict:
        """Test store connection with credentials."""
        try:
            if platform == "shopify":
                api = ShopifyAPI(
                    store_url=store_url,
                    api_key=credentials.get("api_key"),
                    api_secret=credentials.get("api_secret"),
                    access_token=credentials.get("access_token")
                )
                result = await api.get_products(limit=1)
                return result
            
            elif platform == "woocommerce":
                api = WooCommerceAPI(
                    store_url=store_url,
                    api_key=credentials.get("api_key"),
                    api_secret=credentials.get("api_secret")
                )
                result = await api.get_products(limit=1)
                return result
            
            elif platform == "cj":
                api = CJAPI(
                    api_key=credentials.get("api_key"),
                    api_secret=credentials.get("api_secret")
                )
                result = await api.search_products("test", limit=1)
                return {"success": True, "message": "CJ API connection successful"}
            
            else:
                return {"success": False, "error": f"Unsupported platform: {platform}"}
        except Exception as e:
            logger.error(f"Test connection error: {e}")
            return {"success": False, "error": str(e)}
    
    async def sync_products(self, platform: str = None) -> Dict:
        """
        Sync products from connected stores.
        
        Args:
            platform: Optional platform filter
        
        Returns:
            Sync results
        """
        try:
            results = {}
            stores = self.stores
            if platform:
                stores = [s for s in stores if s.get("platform") == platform]
            
            for store in stores:
                p = store.get("platform")
                store_url = store.get("store_url")
                
                # Get credentials from memory
                api_key = get_memory(self.email, f"store_{p}_api_key")
                api_secret = get_memory(self.email, f"store_{p}_api_secret")
                access_token = get_memory(self.email, f"store_{p}_access_token")
                
                if p == "shopify":
                    api = ShopifyAPI(store_url, api_key, api_secret, access_token)
                    result = await api.get_products()
                    if result.get("success"):
                        results[p] = {
                            "count": len(result.get("products", [])),
                            "products": result.get("products", [])
                        }
                
                elif p == "woocommerce":
                    api = WooCommerceAPI(store_url, api_key, api_secret)
                    result = await api.get_products()
                    if result.get("success"):
                        results[p] = {
                            "count": len(result.get("products", [])),
                            "products": result.get("products", [])
                        }
                
                elif p == "cj":
                    api = CJAPI(api_key, api_secret)
                    result = await api.search_products("top", limit=20)
                    if result.get("success"):
                        results[p] = {
                            "count": len(result.get("products", [])),
                            "products": result.get("products", [])
                        }
            
            # Save to task history
            task_id = add_task_history(
                email=self.email,
                agent_name="store_manager",
                task=f"Synced products from {len(results)} stores",
                status="completed"
            )
            update_task_result(
                task_id=task_id,
                result=json.dumps(results),
                status="completed"
            )
            
            return {
                "success": True,
                "results": results,
                "task_id": task_id
            }
        except Exception as e:
            logger.error(f"Sync products error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_inventory(self, platform: str = None) -> Dict:
        """Get inventory from connected stores."""
        try:
            results = {}
            stores = self.stores
            if platform:
                stores = [s for s in stores if s.get("platform") == platform]
            
            for store in stores:
                p = store.get("platform")
                store_url = store.get("store_url")
                
                # Get credentials
                api_key = get_memory(self.email, f"store_{p}_api_key")
                api_secret = get_memory(self.email, f"store_{p}_api_secret")
                access_token = get_memory(self.email, f"store_{p}_access_token")
                
                if p == "shopify":
                    api = ShopifyAPI(store_url, api_key, api_secret, access_token)
                    result = await api.get_products()
                    if result.get("success"):
                        # Extract inventory data
                        inventory = []
                        for product in result.get("products", []):
                            for variant in product.get("variants", []):
                                if variant.get("inventory_quantity", 0) > 0:
                                    inventory.append({
                                        "product_id": product.get("id"),
                                        "title": product.get("title"),
                                        "variant_id": variant.get("id"),
                                        "sku": variant.get("sku"),
                                        "quantity": variant.get("inventory_quantity", 0)
                                    })
                        results[p] = inventory
                
                elif p == "woocommerce":
                    api = WooCommerceAPI(store_url, api_key, api_secret)
                    result = await api.get_products()
                    if result.get("success"):
                        inventory = []
                        for product in result.get("products", []):
                            if product.get("stock_quantity", 0) > 0:
                                inventory.append({
                                    "product_id": product.get("id"),
                                    "title": product.get("name"),
                                    "sku": product.get("sku"),
                                    "quantity": product.get("stock_quantity", 0)
                                })
                        results[p] = inventory
            
            return {
                "success": True,
                "inventory": results
            }
        except Exception as e:
            logger.error(f"Get inventory error: {e}")
            return {"success": False, "error": str(e)}
    
    async def check_inventory_alerts(self) -> Dict:
        """Check for low inventory across all stores."""
        try:
            inventory_result = await self.get_inventory()
            if not inventory_result.get("success"):
                return {"success": False, "error": inventory_result.get("error")}
            
            alerts = {}
            low_threshold = 10  # Default low stock threshold
            
            for platform, items in inventory_result.get("inventory", {}).items():
                low_items = [item for item in items if item.get("quantity", 0) < low_threshold]
                if low_items:
                    alerts[platform] = low_items
            
            if alerts:
                return {
                    "success": True,
                    "alerts": alerts,
                    "message": f"Low inventory detected in {len(alerts)} stores"
                }
            else:
                return {
                    "success": True,
                    "alerts": {},
                    "message": "All inventory levels are healthy"
                }
        except Exception as e:
            logger.error(f"Check inventory alerts error: {e}")
            return {"success": False, "error": str(e)}

# ============ MAIN ENTRY POINTS ============

# CJ Dropshipping wrapper functions
async def search_cj_products(keyword: str, page: int = 1, limit: int = 20) -> List[Dict]:
    """Search CJ products - wrapper for compatibility."""
    api = CJAPI()
    result = await api.search_products(keyword, page, limit)
    if result.get("success"):
        return result.get("products", [])
    return []

async def get_cj_product_details(product_id: str) -> Optional[Dict]:
    """Get CJ product details - wrapper for compatibility."""
    api = CJAPI()
    result = await api.get_product_details(product_id)
    if result.get("success"):
        return result.get("product")
    return None

async def create_cj_order(order_data: Dict) -> Dict:
    """Create CJ order - wrapper for compatibility."""
    api = CJAPI()
    return await api.create_order(order_data)

# Store connection functions
def connect_store(email: str, platform: str, store_url: str) -> Dict:
    """
    Connect a store - wrapper for database function.
    This is used by main.py.
    """
    return db_connect_store(email, platform, store_url)

def get_user_stores(email: str) -> List[Dict]:
    """Get user stores - wrapper for database function."""
    return get_user_stores(email)

# ============ INITIALIZATION ============

print("✅ Store Manager module loaded successfully")
print("   Supported platforms: Shopify, WooCommerce, CJ Dropshipping")
print("   Features: product sync, inventory, alerts, order management")