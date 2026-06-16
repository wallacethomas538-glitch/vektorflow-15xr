"""
VektorFlow 15xr - Main Entry Point
OAuth-first, 7-day trial, subscription enforcement, GTM Toolkit, Vektor Agent with Permanent Memory
"""

from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import json
from datetime import datetime, timedelta
import hashlib
import jwt
import secrets

app = FastAPI(title="VektorFlow 15xr")

# ========== DATABASE ==========
from database import get_db, init_db, create_user, get_user, add_user_store, get_user_stores
from database import create_subscription, get_subscription, update_subscription, cancel_subscription
from database import check_and_block_access, extend_trial, save_icp_data, get_icp_data
from database import save_llm_key, get_llm_keys, get_llm_key
from database import get_user_preferences, save_user_preferences
from database import save_memory, get_memory, get_all_memory, delete_memory, clear_all_memory
from database import add_task_history, update_task_result, get_task_history
init_db()

# ========== RATE LIMITER ==========
from rate_limiter import rate_limit, rate_limit_middleware
app.middleware("http")(rate_limit_middleware)

# ========== AUTH ==========
from auth import create_jwt, get_current_user
from middleware import subscription_middleware

app.middleware("http")(subscription_middleware)

# ========== OAUTH ==========
from oauth_handler import generate_oauth_url, exchange_code_for_token, parse_store_url

# ========== HANDLERS ==========
from llm_handler import call_llm, MODEL_PROVIDER
from agents import run_agent_task
from store_manager import search_cj_products
from trend_engine import get_tiktok_trends

# ========== VEKTOR AGENT ==========
from vektor_agent import vektor_chat

# ========== PAYMENT ==========
from payment import router as payment_router
app.include_router(payment_router)

# ========== CONFIG ==========
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change_me")
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

# ========== MODELS ==========
class StoreInitiateRequest(BaseModel):
    platform: str
    store_url: str
    redirect_uri: str

class ICPData(BaseModel):
    product_type: str
    customer: str
    challenge: str
    workflow: str
    revenue: str

class OutreachRequest(BaseModel):
    goal: str
    product_type: Optional[str] = "products"
    customer: Optional[str] = "e-commerce store owners"
    challenge: Optional[str] = "finding customers"

class LaunchRequest(BaseModel):
    product: str
    audience: Optional[str] = "e-commerce entrepreneurs"
    channels: Optional[List[str]] = ["producthunt", "hackernews", "social", "email"]

class PricingRequest(BaseModel):
    products: List[Dict[str, Any]]

class SDRRequest(BaseModel):
    product: str
    audience: Optional[str] = "e-commerce store owners"

class DirectLLMRequest(BaseModel):
    prompt: str
    model: str = "llama-3.3-70b-versatile"

class AgentTaskRequest(BaseModel):
    agent_name: str
    task: str
    model: Optional[str] = "llama-3.3-70b-versatile"

class CatalogUpload(BaseModel):
    store_id: str
    products: List[Dict[str, Any]]

class VektorChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict]] = []

class VektorPreferencesRequest(BaseModel):
    agent_name: Optional[str] = "Vektor"
    wake_word: Optional[str] = "Hey Vektor"
    voice_enabled: Optional[int] = 1
    memory_enabled: Optional[int] = 1
    default_model: Optional[str] = "llama-3.3-70b-versatile"
    response_style: Optional[str] = "concise"

# ========== ROOT & HEALTH ==========
@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ========== ICP ==========
@app.post("/user/icp")
def save_icp(data: ICPData, email: str = Depends(get_current_user)):
    save_icp_data(email, data.dict())
    return {"status": "saved"}

@app.get("/user/icp")
def get_icp(email: str = Depends(get_current_user)):
    return {"icp": get_icp_data(email)}

# ========== OAUTH ==========
@app.post("/store/initiate")
async def initiate_store_connection(request: StoreInitiateRequest):
    if not request.store_url or not request.platform:
        raise HTTPException(400, "Store URL and platform required")
    
    auth_url, state = generate_oauth_url(request.platform, request.store_url, request.redirect_uri)
    
    if not auth_url:
        raise HTTPException(400, f"Platform {request.platform} not fully configured")
    
    shop_id, _ = parse_store_url(request.store_url, request.platform)
    store_email = f"{shop_id}@vektorflow.com"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO oauth_states (email, state, platform, shop_id)
        VALUES (?, ?, ?, ?)
    """, (store_email, state, request.platform, shop_id))
    conn.commit()
    conn.close()
    
    return {"auth_url": auth_url, "state": state, "store_email": store_email}

@app.get("/store/callback")
async def store_callback(code: str, shop: str, state: str, platform: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT email FROM oauth_states WHERE state = ? AND platform = ?", (state, platform))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(400, "Invalid state parameter")
    
    store_email = row[0]
    
    token_data = await exchange_code_for_token(platform, code, shop, f"{os.environ.get('APP_URL')}/store/callback")
    
    if not token_data.get("success"):
        raise HTTPException(400, token_data.get("error", "Token exchange failed"))
    
    user = get_user(store_email)
    
    if not user:
        random_password = secrets.token_urlsafe(32)
        password_hash = hashlib.sha256(random_password.encode()).hexdigest()
        create_user(store_email, password_hash, shop)
        create_subscription(store_email, "free")
    
    add_user_store(
        email=store_email,
        platform=platform,
        api_key=token_data.get("access_token", ""),
        api_secret=token_data.get("refresh_token", ""),
        store_url=shop
    )
    
    jwt_token = create_jwt(store_email)
    
    return {"access_token": jwt_token, "store_id": shop, "email": store_email}

# ========== SUBSCRIPTION ==========
@app.get("/subscription/status")
def get_subscription_status(email: str = Depends(get_current_user)):
    user = get_user(email)
    sub = get_subscription(email)
    
    if not user or not sub:
        return {"status": "unknown"}
    
    return {
        "plan": sub.get("plan", "free"),
        "status": sub.get("status", "active"),
        "current_period_end": sub.get("current_period_end"),
        "tier": user.get("tier", "trial"),
        "trial_expires": user.get("trial_expires")
    }

# ========== USER STORES ==========
@app.get("/user/stores")
def get_stores(email: str = Depends(get_current_user)):
    stores = get_user_stores(email)
    return {"stores": stores}

# ========== USER LLM KEYS ==========
@app.post("/user/llm-keys")
def save_llm_key_route(data: dict, email: str = Depends(get_current_user)):
    provider = data.get("provider")
    api_key = data.get("api_key")
    if not provider or not api_key:
        raise HTTPException(400, "Provider and API key required")
    save_llm_key(email, provider, api_key)
    return {"status": "saved", "provider": provider}

@app.get("/user/llm-keys")
def get_user_llm_keys(email: str = Depends(get_current_user)):
    keys = get_llm_keys(email)
    return {"keys": keys}

# ========== VEKTOR AGENT ==========
@app.post("/vektor/chat")
async def vektor_chat_endpoint(req: VektorChatRequest, email: str = Depends(get_current_user)):
    result = await vektor_chat(email, req.message, req.history)
    return result

@app.get("/vektor/status")
async def vektor_status(email: str = Depends(get_current_user)):
    stores = get_user_stores(email)
    user_keys = get_llm_keys(email)
    icp = get_icp_data(email)
    prefs = get_user_preferences(email)
    memory = get_all_memory(email)
    
    return {
        "status": "online",
        "name": prefs.get("agent_name", "Vektor"),
        "wake_word": prefs.get("wake_word", "Hey Vektor"),
        "capabilities": [
            "product_search",
            "trend_analysis",
            "outreach_generation",
            "inventory_management",
            "campaign_creation",
            "sales_analysis",
            "permanent_memory"
        ],
        "connected_stores": len(stores),
        "available_providers": list(user_keys.keys()),
        "icp_complete": bool(icp),
        "memory_count": len(memory)
    }

# ========== VEKTOR PREFERENCES ==========
@app.post("/vektor/preferences")
async def set_vektor_preferences(prefs: VektorPreferencesRequest, email: str = Depends(get_current_user)):
    save_user_preferences(email, prefs.dict())
    return {"status": "saved"}

@app.get("/vektor/preferences")
async def get_vektor_preferences(email: str = Depends(get_current_user)):
    prefs = get_user_preferences(email)
    return prefs

@app.get("/vektor/memory")
async def get_vektor_memory(email: str = Depends(get_current_user)):
    memory = get_all_memory(email)
    return {"memory": memory}

@app.delete("/vektor/memory/{key}")
async def delete_vektor_memory(key: str, email: str = Depends(get_current_user)):
    delete_memory(email, key)
    return {"status": "deleted"}

@app.delete("/vektor/memory")
async def clear_vektor_memory(email: str = Depends(get_current_user)):
    clear_all_memory(email)
    return {"status": "cleared"}

# ========== GTM: OUTREACH ==========
@app.post("/outreach/generate")
@rate_limit(tier="trial")
async def generate_outreach_sequence(req: OutreachRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    prompt = f"""
    Generate a 3-email + 2-LinkedIn message outreach sequence for a business that sells {req.product_type}.
    
    Target customer: {req.customer}
    Goal: {req.goal}
    Pain point: {req.challenge}
    
    Format:
    Email 1 (Day 1): [subject] - [body]
    LinkedIn 1 (Day 2): [message]
    Email 2 (Day 4): [subject] - [body]
    LinkedIn 2 (Day 6): [message]
    Email 3 (Day 8): [subject] - [body]
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

# ========== GTM: LAUNCH ==========
@app.post("/launch/generate")
@rate_limit(tier="trial")
async def generate_launch_checklist(req: LaunchRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    channels = req.channels or ["producthunt", "hackernews", "social", "email"]
    prompt = f"""
    Create a comprehensive launch checklist for a new product launch.
    
    Product: {req.product}
    Target audience: {req.audience}
    Channels: {', '.join(channels)}
    
    Include:
    1. Pre-launch tasks (30 days before)
    2. Launch week tasks
    3. Post-launch tasks
    4. Success metrics for each channel
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

# ========== GTM: PRICING ==========
@app.post("/pricing/suggest")
@rate_limit(tier="trial")
async def suggest_pricing(req: PricingRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    products = req.products[:5]
    if not products:
        return {"error": "No products provided"}
    prompt = f"""
    Analyze these products and suggest optimal pricing strategies:
    
    Products: {json.dumps(products)}
    
    Provide:
    1. Recommended price points
    2. Pricing strategy (premium, competitive, penetration)
    3. Bundle suggestions
    4. Discount recommendations
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

# ========== GTM: SDR ==========
@app.post("/sdr/research")
@rate_limit(tier="trial")
async def sdr_research(req: SDRRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    prompt = f"""
    You are an AI SDR. Research potential leads for a business that sells {req.product}.
    
    Target audience: {req.audience}
    
    Provide:
    1. 5 specific lead profiles (company, role, why they're a fit)
    2. One personalized email draft for each
    3. LinkedIn connection message for each
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

# ========== GTM: CONTENT REPURPOSER ==========
@app.post("/content/repurpose")
@rate_limit(tier="trial")
async def repurpose_content(data: dict, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    content = data.get('content', '')
    if not content:
        return {"error": "No content provided"}
    prompt = f"""
    Repurpose this content into multiple formats:
    
    Original content: {content[:500]}
    
    Generate:
    1. 3 social media posts (X, LinkedIn, Instagram)
    2. 1 email newsletter snippet
    3. 1 ad copy variant
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

# ========== LLM ==========
@app.post("/llm/call")
@rate_limit(tier="trial")
async def llm_call(req: DirectLLMRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    result = await call_llm(req.prompt, req.model, user_keys)
    return result

# ========== AGENT TASKS ==========
@app.post("/agent/run")
@rate_limit(tier="trial")
async def run_agent(req: AgentTaskRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    result = await run_agent_task(email, req.agent_name, req.task, user_keys, req.model)
    return result

@app.get("/agent/trends")
@rate_limit(tier="trial")
async def get_trends(email: str = Depends(get_current_user)):
    trends = await get_tiktok_trends()
    return {"trends": trends}

# ========== CJ SEARCH ==========
@app.get("/cj/search")
@rate_limit(tier="trial")
async def cj_search(keyword: str, email: str = Depends(get_current_user)):
    products = await search_cj_products(keyword)
    return {"products": products}

# ========== E-COMMERCE ==========
catalogs_cache = {}

@app.post("/ecommerce/catalog")
@rate_limit(tier="trial")
def upload_catalog(data: CatalogUpload, email: str = Depends(get_current_user)):
    catalogs_cache[data.store_id] = data.products
    return {"status": "catalog stored", "store_id": data.store_id, "product_count": len(data.products)}

@app.get("/ecommerce/trends/{store_id}")
@rate_limit(tier="trial")
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
@rate_limit(tier="trial")
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
