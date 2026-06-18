from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
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

# Add middleware
app.add_middleware(APIKeyMiddleware)

# ============ STATIC FILES ============
# Path to static folder
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
HTML_PATH = os.path.join(STATIC_DIR, "index.html")

# Mount static files
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"Static files mounted from {STATIC_DIR}")
else:
    logger.warning(f"Static directory not found at {STATIC_DIR}")

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

# ROOT - SERVES HTML PAGE
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page"""
    try:
        if os.path.exists(HTML_PATH):
            with open(HTML_PATH, "r", encoding="utf-8") as f:
                return f.read()
        else:
            return HTMLResponse(content=f"""
            <html>
                <body>
                    <h1>VektorFlow 15xr</h1>
                    <p>index.html not found at {HTML_PATH}</p>
                    <p>Static dir exists: {os.path.exists(STATIC_DIR)}</p>
                </body>
            </html>
            """, status_code=404)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error loading page</h1><p>{str(e)}</p>", status_code=500)

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
        # HARDCODED CREDENTIALS
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
        keywords = [
            {"keyword": input_data.product_title, "volume": 1000, "difficulty": 30},
            {"keyword": f"best {input_data.product_title}", "volume": 500, "difficulty": 45},
            {"keyword": f"{input_data.product_title} for sale", "volume": 300, "difficulty": 25}
        ]
        
        seo_title = f"{input_data.product_title} - Premium Quality"[:60]
        meta_description = input_data.supplier_description[:155] if input_data.supplier_description else f"Shop {input_data.product_title} online"
        url_slug = quote(input_data.product_title.lower().replace(" ", "-"))
        
        schema_markup = {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": input_data.product_title,
            "description": input_data.supplier_description[:200] if input_data.supplier_description else "",
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

# ============ API INFO ENDPOINT ============
@app.get("/api/info")
async def api_info():
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

# ============ FALLBACK FOR SPIN-DOWN ============
@app.get("/wakeup")
async def wakeup():
    """Prevent spin-down by keeping the app active"""
    return {"status": "awake", "timestamp": datetime.utcnow().isoformat()}

# ============ RUN ============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)