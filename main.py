from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import json
import logging
from datetime import datetime

# ============ IMPORT YOUR EXISTING FILES ============
from database import get_user, get_user_stores, get_llm_keys, get_icp_data, save_conversation
from vektor_agent import vektor_chat, detect_intent
from llm_handler import call_llm
from store_manager import search_cj_products, get_cj_product_details
from trend_engine import get_tiktok_trends
from agents import run_agent_task
from auth import verify_token, create_token
from middleware import APIKeyMiddleware
from rate_limiter import rate_limit
from payment import check_subscription_status

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
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "vektorflow-admin-2026-secure-key")

# ============ MIDDLEWARE ============
app.add_middleware(APIKeyMiddleware, admin_key=ADMIN_API_KEY)

# ============ STATIC FILES ============
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
HTML_PATH = os.path.join(STATIC_DIR, "index.html")

if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    logger.info(f"Static files mounted from {STATIC_DIR}")

# ============ SCHEMAS ============
class CommanderLogin(BaseModel):
    username: str
    password: str

class AgentCommand(BaseModel):
    command: str
    params: Optional[Dict[str, Any]] = {}

class AIChatMessage(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = {}
    email: Optional[str] = None
    conversation_id: Optional[str] = None

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

# ============ ROOT ============
@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        if os.path.exists(HTML_PATH):
            with open(HTML_PATH, "r", encoding="utf-8") as f:
                return f.read()
        return HTMLResponse("<h1>index.html not found</h1>", status_code=404)
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "VektorFlow 15xr", "timestamp": datetime.utcnow().isoformat()}

# ============ LOGIN ============
@app.post("/commander/login")
async def commander_login(login_data: CommanderLogin):
    try:
        # Check against database
        user = get_user(login_data.username)
        if user and user.get("password") == login_data.password:
            token = create_token({"email": login_data.username, "role": "admin"})
            return {
                "status": "success",
                "message": "Login successful",
                "token": token,
                "user": {
                    "username": login_data.username,
                    "role": "admin",
                    "permissions": ["full_access"]
                }
            }
        else:
            # Fallback hardcoded credentials
            VALID_USERNAME = "commander@vektorflow.com"
            VALID_PASSWORD = "vektorflow2026"
            if login_data.username == VALID_USERNAME and login_data.password == VALID_PASSWORD:
                token = create_token({"email": VALID_USERNAME, "role": "admin"})
                return {
                    "status": "success",
                    "message": "Login successful",
                    "token": token,
                    "user": {"username": VALID_USERNAME, "role": "admin"}
                }
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/login")
async def auth_login(login_data: CommanderLogin):
    return await commander_login(login_data)

@app.post("/login")
async def login(login_data: CommanderLogin):
    return await commander_login(login_data)

# ============ VEKTOR AGENT CHAT ============
@app.post("/api/agent/chat")
async def agent_chat(message: AIChatMessage):
    """Chat with the Vektor Agent - uses vektor_agent.py"""
    try:
        if not message.email:
            message.email = "commander@vektorflow.com"
        
        # Call the Vektor Agent
        result = await vektor_chat(
            email=message.email,
            message=message.message,
            conversation_history=message.context
        )
        
        # Save conversation if database available
        try:
            save_conversation(message.email, message.message, result.get("response", ""), message.conversation_id)
        except:
            pass
        
        return {
            "status": "success",
            "response": result.get("response", "I'm here to help, Commander."),
            "action": result.get("action", "chat"),
            "data": result.get("data", {}),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Agent chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ AGENT COMMAND ============
@app.post("/api/agent/command")
async def agent_command(command: AgentCommand):
    """Execute a command through the agent"""
    try:
        # Use the detect_intent from vektor_agent.py
        intent = detect_intent(command.command, {})
        
        # Execute using agents.py
        result = await run_agent_task(command.command, command.params)
        
        return {
            "status": "success",
            "intent": intent,
            "result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Agent command error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ AI CHAT ============
@app.post("/api/ai/chat")
async def ai_chat(message: AIChatMessage):
    """Chat with AI using llm_handler.py"""
    try:
        user_keys = get_llm_keys(message.email or "commander@vektorflow.com")
        
        result = await call_llm(
            prompt=message.message,
            model="llama-3.3-70b-versatile",
            api_keys=user_keys,
            context=message.context
        )
        
        return {
            "status": "success",
            "response": result.get("response", "I'm here to help."),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ PRODUCT SEARCH ============
@app.post("/api/products/search")
async def search_products(request: Request):
    """Search CJ Dropshipping products using store_manager.py"""
    try:
        data = await request.json()
        keyword = data.get("keyword", "")
        if not keyword:
            raise HTTPException(status_code=400, detail="Keyword required")
        
        products = await search_cj_products(keyword)
        return {
            "status": "success",
            "products": products[:10],
            "count": len(products),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Product search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ TRENDS ============
@app.get("/api/trends")
async def get_trends():
    """Get trending products using trend_engine.py"""
    try:
        trends = await get_tiktok_trends()
        return {
            "status": "success",
            "trends": trends[:10],
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ STORE CONNECT ============
@app.post("/api/store/connect")
async def connect_store(request: Request):
    """Connect a store platform"""
    try:
        data = await request.json()
        platform = data.get("platform")
        store_url = data.get("store_url")
        email = data.get("email", "commander@vektorflow.com")
        
        # Use database.py to save store connection
        from database import connect_store
        result = connect_store(email, platform, store_url)
        
        return {
            "status": "success",
            "message": f"Successfully connected to {platform}",
            "platform": platform,
            "store_url": store_url,
            "connected_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Connect store error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ TASKS ============
@app.get("/api/tasks")
async def get_tasks():
    """Get tasks from database.py"""
    try:
        from database import get_tasks
        tasks = get_tasks()
        return {"status": "success", "tasks": tasks}
    except:
        # Fallback tasks
        return {
            "status": "success",
            "tasks": [
                {"id": "1", "title": "Optimize product descriptions", "status": "in_progress", "priority": "high"},
                {"id": "2", "title": "Generate meta tags for 15 products", "status": "pending", "priority": "medium"},
                {"id": "3", "title": "Update schema markup", "status": "completed", "priority": "low"},
            ]
        }

# ============ SEO OPTIMIZATION ============
@app.post("/optimize-seo", response_model=SEOOutput)
async def optimize_seo(input_data: ProductInput):
    try:
        from urllib.parse import quote
        keywords = [
            {"keyword": input_data.product_title, "volume": 1000, "difficulty": 30},
            {"keyword": f"best {input_data.product_title}", "volume": 500, "difficulty": 45},
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
            "offers": {"@type": "Offer", "priceCurrency": "USD", "price": input_data.price or "29.99"}
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

# ============ API INFO ============
@app.get("/api/info")
async def api_info():
    return {
        "service": "VektorFlow 15xr",
        "version": "1.0",
        "status": "operational",
        "endpoints": {
            "login": "/commander/login",
            "agent_chat": "/api/agent/chat",
            "agent_command": "/api/agent/command",
            "ai_chat": "/api/ai/chat",
            "search_products": "/api/products/search",
            "trends": "/api/trends",
            "store_connect": "/api/store/connect",
            "tasks": "/api/tasks",
            "optimize_seo": "/optimize-seo"
        }
    }

# ============ WAKEUP ============
@app.get("/wakeup")
async def wakeup():
    return {"status": "awake", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
