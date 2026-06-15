"""
VektorFlow 15xr - Main Entry Point
Complete with universal LLM support, store integration, and autonomous agents
"""

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
from datetime import datetime, timedelta
import hashlib
import jwt

app = FastAPI(title="VektorFlow 15xr")

# ========== DATABASE SETUP ==========
from database import get_db, init_db, save_llm_key, get_llm_keys, get_llm_key
from database import add_user_store, get_user_stores
init_db()

# ========== IMPORTS FOR AGENTS AND HANDLERS ==========
from llm_handler import call_llm, MODEL_PROVIDER, PROVIDER_CONFIG
from agents import run_agent_task
from store_manager import search_cj_products, get_cj_product_details
from trend_engine import get_tiktok_trends

# ========== CONFIG ==========
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change_me")
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

def create_jwt(email: str) -> str:
    token_data = {"email": email, "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(api_key: str = Header(...)):
    try:
        payload = jwt.decode(api_key, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("email")
        if not email:
            raise HTTPException(401, "Invalid token")
        return email
    except:
        raise HTTPException(401, "Invalid or expired token")

# ========== MODELS ==========
class UserSignup(BaseModel):
    email: str
    password: str
    store_name: str

class UserLogin(BaseModel):
    email: str
    password: str

class LLMKeySave(BaseModel):
    provider: str
    api_key: str

class ConnectStoreRequest(BaseModel):
    platform: str
    api_key: str
    api_secret: Optional[str] = ""
    store_url: Optional[str] = ""

class AgentTaskRequest(BaseModel):
    agent_name: str
    task: str
    model: Optional[str] = "llama-3.3-70b-versatile"

class DirectLLMRequest(BaseModel):
    prompt: str
    model: str = "llama-3.3-70b-versatile"

# ========== ROOT & HEALTH ==========
@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/debug/check-env")
def check_env():
    return {
        "jwt_key_exists": bool(os.environ.get("JWT_SECRET_KEY")),
        "admin_key_exists": bool(os.environ.get("ADMIN_API_KEY")),
        "cj_mcp_url": os.environ.get("CJ_MCP_URL", "NOT SET"),
        "database_url_exists": bool(os.environ.get("DATABASE_URL"))
    }

# ========== SETUP TEST USER ==========
@app.get("/setup-create-user")
def setup_create_user():
    email = "commander@vektorflow.com"
    password_hash = hash_password("test123")
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    existing = cursor.fetchone()
    
    if existing:
        conn.close()
        return {"status": "already_exists", "email": email, "password": "test123"}
    
    cursor.execute("""
        INSERT INTO users (email, password_hash, store_name, trial_expires)
        VALUES (?, ?, ?, datetime('now', '+7 days'))
    """, (email, password_hash, "commander_store"))
    conn.commit()
    conn.close()
    
    return {"status": "created", "email": email, "password": "test123", "access_token": create_jwt(email)}

# ========== AUTH ==========
@app.post("/auth/signup")
def signup(user: UserSignup):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (user.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(400, "Email already registered")
    
    cursor.execute("""
        INSERT INTO users (email, password_hash, store_name, trial_expires)
        VALUES (?, ?, ?, datetime('now', '+7 days'))
    """, (user.email, hash_password(user.password), user.store_name))
    conn.commit()
    conn.close()
    
    return {"access_token": create_jwt(user.email), "token_type": "bearer", "expires_days": 7}

@app.post("/auth/login")
def login(user: UserLogin):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (user.email,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(401, "Invalid credentials")
    
    if not verify_password(user.password, row["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    
    return {"access_token": create_jwt(user.email), "token_type": "bearer", "expires_days": 7}

# ========== USER LLM KEYS ==========
@app.post("/user/llm-keys")
def save_llm_key_route(key_data: LLMKeySave, email: str = Depends(get_current_user)):
    """Save API key for any LLM provider"""
    save_llm_key(email, key_data.provider, key_data.api_key)
    return {"status": "saved", "provider": key_data.provider}

@app.get("/user/llm-keys")
def get_user_llm_keys(email: str = Depends(get_current_user)):
    """Get all API keys for the user"""
    keys = get_llm_keys(email)
    return {"keys": keys}

@app.get("/llm/providers")
def get_available_providers():
    """Return list of supported LLM providers"""
    providers = list(PROVIDER_CONFIG.keys())
    models = list(MODEL_PROVIDER.keys())
    return {"providers": providers, "models": models}

# ========== STORE CONNECTION ==========
@app.post("/user/connect-store")
def connect_store(req: ConnectStoreRequest, email: str = Depends(get_current_user)):
    """Connect a dropshipping store (CJ Dropshipping, etc.)"""
    store_id = add_user_store(email, req.platform, req.api_key, req.api_secret, req.store_url)
    return {"status": "connected", "store_id": store_id, "platform": req.platform}

@app.get("/user/stores")
def get_stores(email: str = Depends(get_current_user)):
    """List all connected stores"""
    stores = get_user_stores(email)
    return {"stores": stores}

# ========== AGENT TASKS ==========
@app.post("/agent/run")
async def run_agent(req: AgentTaskRequest, email: str = Depends(get_current_user)):
    """Run a task with the specified agent"""
    result = await run_agent_task(email, req.agent_name, req.task, req.model)
    return result

@app.get("/agent/trends")
async def get_trends(email: str = Depends(get_current_user)):
    """Get current trending products"""
    trends = await get_tiktok_trends()
    return {"trends": trends}

# ========== DIRECT LLM CALL ==========
@app.post("/llm/call")
async def llm_call(req: DirectLLMRequest, email: str = Depends(get_current_user)):
    """Direct LLM call using user's saved keys"""
    from database import get_llm_keys
    user_keys = get_llm_keys(email)
    result = await call_llm(req.prompt, req.model, user_keys)
    return result

# ========== CJ DROPSHIPPING ==========
@app.get("/cj/search")
async def cj_search(keyword: str, email: str = Depends(get_current_user)):
    """Search products on CJ Dropshipping"""
    products = await search_cj_products(keyword)
    return {"products": products}

@app.get("/cj/product/{product_id}")
async def cj_product(product_id: str, email: str = Depends(get_current_user)):
    """Get product details from CJ"""
    product = await get_cj_product_details(product_id)
    return {"product": product}

# ========== E-COMMERCE ==========
catalogs_cache = {}

class CatalogUpload(BaseModel):
    store_id: str
    products: List[Dict[str, Any]]

@app.post("/ecommerce/catalog")
def upload_catalog(data: CatalogUpload, email: str = Depends(get_current_user)):
    catalogs_cache[data.store_id] = data.products
    return {"status": "catalog stored", "store_id": data.store_id, "product_count": len(data.products)}

@app.get("/ecommerce/trends/{store_id}")
def get_trends_route(store_id: str, email: str = Depends(get_current_user)):
    if store_id not in catalogs_cache:
        raise HTTPException(404, "No catalog found")
    
    products = catalogs_cache[store_id]
    trends = ["wireless", "fitness", "eco friendly", "smart", "bluetooth", "waterproof", "organic", "portable"]
    
    matches = []
    for product in products[:20]:
        name = product.get("name", "").lower()
        for trend in trends:
            if trend in name:
                matches.append({
                    "product": product.get("name"),
                    "trend": trend,
                    "campaign_angle": f"🔥 {product.get('name')} is trending with '{trend}'!"
                })
                break
    
    return {"success": True, "matches": matches, "count": len(matches)}

@app.get("/ecommerce/campaign/{store_id}/{product_name}")
def get_campaign(store_id: str, product_name: str, email: str = Depends(get_current_user)):
    return {
        "product": product_name,
        "messages": [
            f"🔥 {product_name} is trending! Want the link?",
            f"✨ 4.5★ from customers — you'll love it",
            f"⏳ Only a few left. Link here: [LINK]"
        ]
    }

# ========== SERVE FRONTEND ==========
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
