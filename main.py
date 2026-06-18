from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
import json
import logging
from datetime import datetime
from urllib.parse import quote

# ============ APP SETUP ============
app = FastAPI(title="VektorFlow 15xr", version="1.0")

# ============ CORS ============
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ LOGGING ============
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vektorflow")
logger.setLevel(logging.INFO)

# ============ ADMIN API KEY ============
ADMIN_API_KEY = "vektorflow-admin-2026-secure-key"

# ============ API KEY MIDDLEWARE ============
from starlette.middleware.base import BaseHTTPMiddleware

class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Bypass API key validation for these paths
        bypass_paths = [
            "/",
            "/health",
            "/commander/login",
            "/auth/login",
            "/static",
            "/favicon.ico",
            "/docs",
            "/openapi.json"
        ]
        
        for path in bypass_paths:
            if request.url.path.startswith(path):
                return await call_next(request)
        
        # Check for API key
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
        
        if api_key and api_key.startswith("Bearer "):
            api_key = api_key[7:]
        
        if not api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API Key. Request access at vektorflow.ai")
        
        if api_key != ADMIN_API_KEY:
            raise HTTPException(status_code=403, detail="Invalid API Key")
        
        return await call_next(request)

# Add middleware (COMMENT OUT TO DISABLE TEMPORARILY)
app.add_middleware(APIKeyMiddleware)

# ============ STATIC FILES ============
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    logger.warning("Static directory not found")

# ============ SCHEMAS ============
class CommanderLogin(BaseModel):
    username: str
    password: str

class ProductInput(BaseModel):
    product_title: str
    supplier_description: str
    category: str
    raw_keywords: Optional[List[str]] = None
    price: Optional[str] = "29.99"

class SEOOutput(BaseModel):
    keywords: List[dict]
    seo_title: str
    meta_description: str
    url_slug: str
    schema_markup: dict

# ============ ENDPOINTS ============

@app.get("/")
async def root():
    return {
        "service": "VektorFlow 15xr",
        "version": "1.0",
        "status": "operational",
        "endpoints": {
            "commander_login": "/commander/login",
            "health": "/health",
            "optimize_seo": "/optimize-seo",
            "static": "/static"
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "VektorFlow 15xr",
        "timestamp": datetime.utcnow().isoformat()
    }

# ============ COMMANDER LOGIN (NO API KEY REQUIRED) ============
@app.post("/commander/login")
async def commander_login(login_data: CommanderLogin):
    """Commander login - bypasses API key requirement"""
    try:
        # HARDCODED CREDENTIALS - CHANGE THESE
        VALID_USERNAME = "commander"
        VALID_PASSWORD = "vektorflow2026"
        
        if login_data.username == VALID_USERNAME and login_data.password == VALID_PASSWORD:
            return {
                "status": "success",
                "message": "Login successful",
                "token": "commander-session-token-2026",
                "user": {
                    "username": "commander",
                    "role": "admin",
                    "permissions": ["full_access"]
                }
            }
        else:
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

# ============ SEO OPTIMIZATION ============
@app.post("/optimize-seo", response_model=SEOOutput)
async def optimize_seo(input_data: ProductInput):
    """SEO optimization endpoint"""
    try:
        # Simple implementation - can be expanded
        keywords = [
            {"keyword": input_data.product_title, "volume": 1000, "difficulty": 30},
            {"keyword": f"best {input_data.product_title}", "volume": 500, "difficulty": 45},
            {"keyword": f"{input_data.product_title} for sale", "volume": 300, "difficulty": 25}
        ]
        
        seo_title = f"{input_data.product_title} - Premium Quality"[:60]
        meta_description = input_data.supplier_description[:155]
        url_slug = quote(input_data.product_title.lower().replace(" ", "-"))
        
        schema_markup = {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": input_data.product_title,
            "description": input_data.supplier_description[:200],
            "category": input_data.category,
            "offers": {
                "@type": "Offer",
                "priceCurrency": "USD",
                "price": input_data.price or "29.99",
                "availability": "https://schema.org/InStock",
                "url": f"/products/{url_slug}"
            }
        }
        
        return SEOOutput(
            keywords=keywords,
            seo_title=seo_title,
            meta_description=meta_description,
            url_slug=url_slug,
            schema_markup=schema_markup
        )
        
    except Exception as e:
        logger.error(f"SEO optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ SAMPLE INPUT ============
SAMPLE_INPUT = {
    "product_title": "Wireless Headphones",
    "supplier_description": "High quality sound with noise cancellation and 30 hour battery life",
    "category": "Electronics"
}

# ============ RUN ============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)