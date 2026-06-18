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
            "/login",
            "/static",
            "/favicon.ico",
            "/docs",
            "/openapi.json",
            "/api/info",
            "/wakeup",
            "/dashboard"
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
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
HTML_PATH = os.path.join(STATIC_DIR, "index.html")

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

# ============ DASHBOARD ENDPOINT ============
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Dashboard page after login"""
    return HTMLResponse(content="""
    <html>
        <head>
            <title>VektorFlow Dashboard</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Inter', -apple-system, sans-serif;
                    background: linear-gradient(145deg, #0b0e1a 0%, #131a2b 100%);
                    min-height: 100vh;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: #e8edf5;
                    padding: 1.5rem;
                }
                .dashboard-card {
                    max-width: 600px;
                    width: 100%;
                    background: rgba(20, 28, 48, 0.75);
                    backdrop-filter: blur(12px);
                    border: 1px solid rgba(90, 150, 255, 0.15);
                    border-radius: 2.5rem;
                    padding: 3rem 2.5rem;
                    text-align: center;
                    box-shadow: 0 30px 60px -20px rgba(0, 0, 0, 0.8);
                }
                .logo-icon {
                    font-size: 3rem;
                    margin-bottom: 0.5rem;
                }
                h1 {
                    font-size: 2rem;
                    font-weight: 600;
                    background: linear-gradient(135deg, #f0f4ff, #b0c8ff);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                    background-clip: text;
                    margin-bottom: 0.5rem;
                }
                .sub {
                    color: #8b9bb5;
                    font-size: 1rem;
                    margin-bottom: 2rem;
                }
                .badge {
                    display: inline-block;
                    background: rgba(90, 150, 255, 0.12);
                    padding: 0.3rem 1.2rem;
                    border-radius: 30px;
                    font-size: 0.75rem;
                    color: #8bb4ff;
                    border: 1px solid rgba(90, 150, 255, 0.1);
                    margin-bottom: 1.5rem;
                }
                .feature-grid {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 1rem;
                    margin: 2rem 0;
                }
                .feature-item {
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.05);
                    border-radius: 1rem;
                    padding: 1.2rem;
                }
                .feature-item .icon { font-size: 1.5rem; display: block; margin-bottom: 0.3rem; }
                .feature-item .label { font-size: 0.8rem; color: #8b9bb5; }
                .btn-logout {
                    display: inline-block;
                    padding: 0.7rem 2rem;
                    border-radius: 60px;
                    border: 1px solid rgba(255, 100, 100, 0.2);
                    background: rgba(255, 100, 100, 0.05);
                    color: #f7a0a0;
                    text-decoration: none;
                    font-size: 0.9rem;
                    transition: 0.2s;
                    margin-top: 1rem;
                }
                .btn-logout:hover {
                    background: rgba(255, 100, 100, 0.1);
                    border-color: rgba(255, 100, 100, 0.3);
                }
                .btn-home {
                    display: inline-block;
                    padding: 0.7rem 2rem;
                    border-radius: 60px;
                    border: 1px solid rgba(90, 150, 255, 0.2);
                    background: rgba(90, 150, 255, 0.05);
                    color: #8bb4ff;
                    text-decoration: none;
                    font-size: 0.9rem;
                    transition: 0.2s;
                    margin-top: 1rem;
                    margin-right: 0.5rem;
                }
                .btn-home:hover {
                    background: rgba(90, 150, 255, 0.1);
                    border-color: rgba(90, 150, 255, 0.3);
                }
                @media (max-width: 480px) {
                    .dashboard-card { padding: 2rem 1.2rem; }
                    .feature-grid { grid-template-columns: 1fr; }
                }
            </style>
        </head>
        <body>
            <div class="dashboard-card">
                <div class="logo-icon">🚀</div>
                <div class="badge">⚡ VektorFlow 15xr</div>
                <h1>Welcome, Commander!</h1>
                <p class="sub">You are now logged in to VektorFlow 15xr.</p>
                <p style="color: #6a7f9a; font-size: 0.9rem;">Your store intelligence is ready.</p>
                
                <div class="feature-grid">
                    <div class="feature-item">
                        <span class="icon">📊</span>
                        <span class="label">Analytics</span>
                    </div>
                    <div class="feature-item">
                        <span class="icon">🔍</span>
                        <span class="label">SEO Optimizer</span>
                    </div>
                    <div class="feature-item">
                        <span class="icon">📈</span>
                        <span class="label">Performance</span>
                    </div>
                    <div class="feature-item">
                        <span class="icon">⚡</span>
                        <span class="label">Real-time</span>
                    </div>
                </div>
                
                <div>
                    <a href="/" class="btn-home">🏠 Home</a>
                    <a href="/" class="btn-logout">🚪 Logout</a>
                </div>
            </div>
        </body>
    </html>
    """)

# ============ COMMANDER LOGIN ============
@app.post("/commander/login")
async def commander_login(login_data: CommanderLogin):
    """Commander login - bypasses API key requirement"""
    try:
        # UPDATED CREDENTIALS - Email login
        VALID_USERNAME = "commander@vektorflow.com"
        VALID_PASSWORD = "vektorflow2026"
        
        logger.info(f"Login attempt: {login_data.username}")
        
        if login_data.username == VALID_USERNAME and login_data.password == VALID_PASSWORD:
            return {
                "status": "success",
                "message": "Login successful",
                "token": "commander-session-token-2026",
                "user": {
                    "username": "commander@vektorflow.com",
                    "role": "admin",
                    "permissions": ["full_access"]
                }
            }
        else:
            logger.warning(f"Failed login attempt: {login_data.username}")
            raise HTTPException(status_code=401, detail="Invalid credentials")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

# ============ LOGIN REDIRECTS (BACKWARD COMPATIBILITY) ============
@app.post("/auth/login")
async def auth_login(login_data: CommanderLogin):
    """Redirect /auth/login to /commander/login"""
    return await commander_login(login_data)

@app.post("/login")
async def login(login_data: CommanderLogin):
    """Redirect /login to /commander/login"""
    return await commander_login(login_data)

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
            "auth_login": "/auth/login",
            "login": "/login",
            "health": "/health",
            "dashboard": "/dashboard",
            "optimize_seo": "/optimize-seo",
            "static": "/static"
        }
    }

# ============ WAKEUP ENDPOINT ============
@app.get("/wakeup")
async def wakeup():
    """Prevent spin-down by keeping the app active"""
    return {"status": "awake", "timestamp": datetime.utcnow().isoformat()}

# ============ RUN ============
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)