from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import json
import logging
from datetime import datetime

# ============ IMPORT ALL FEATURES ============
from database import get_user, get_user_stores, get_llm_keys, get_icp_data, save_conversation
from vektor_agent import vektor_chat, detect_intent
from llm_handler import call_llm
from store_manager import search_cj_products, get_cj_product_details, connect_store
from trend_engine import get_tiktok_trends
from agents import run_agent_task
from auth import verify_token, create_token
from middleware import APIKeyMiddleware
from seo_optimizer import optimize_seo
from outreach import handle_outreach
from inventory import check_inventory, get_inventory_alerts, get_reorder_recommendations
from campaign import generate_campaign
from organic_content import generate_organic_content
# from payment import check_subscription_status  # ON HOLD

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
# Temporarily disabled for testing
# app.add_middleware(APIKeyMiddleware, admin_key=ADMIN_API_KEY)

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

class OutreachRequest(BaseModel):
    product_type: str
    target_audience: Optional[str] = None
    platform: str = "email"
    sequence_length: int = 3
    email: Optional[str] = None

class CampaignRequest(BaseModel):
    product_type: str
    goal: str
    target_audience: Optional[str] = None
    channels: Optional[List[str]] = None
    budget: int = 1000
    timeline_days: int = 30
    email: Optional[str] = None

class OrganicContentRequest(BaseModel):
    product_name: str
    product_description: Optional[str] = None
    platforms: Optional[List[str]] = None
    tone: str = "casual"
    number_of_options: int = 3
    email: Optional[str] = None

class StoreConnectRequest(BaseModel):
    platform: str
    store_url: str
    email: str = "commander@vektorflow.com"

# ============ ROOT & HEALTH ============
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
        user = get_user(login_data.username)
        if user and user.get("password") == login_data.password:
            token = create_token({"email": login_data.username, "role": "admin"})
            return {
                "status": "success",
                "message": "Login successful",
                "token": token,
                "user": {"username": login_data.username, "role": "admin", "permissions": ["full_access"]}
            }
        else:
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
        
        result = await vektor_chat(
            email=message.email,
            message=message.message,
            conversation_history=message.context
        )
        
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
    """Execute a command through the agent - uses agents.py orchestrator"""
    try:
        email = "commander@vektorflow.com"
        user_keys = get_llm_keys(email)
        intent = detect_intent(command.command, {})
        
        result = await run_agent_task(
            email=email,
            agent_name="Vektor",
            command=command.command,
            params=command.params or {}
        )
        
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
async def store_connect(store_data: StoreConnectRequest):
    """Connect a store platform - uses store_manager.py"""
    try:
        result = connect_store(store_data.email, store_data.platform, store_data.store_url)
        return {
            "status": "success",
            "message": f"Successfully connected to {store_data.platform}",
            "platform": store_data.platform,
            "store_url": store_data.store_url,
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
        return {
            "status": "success",
            "tasks": [
                {"id": "1", "title": "Optimize product descriptions", "status": "in_progress"},
                {"id": "2", "title": "Generate meta tags for 15 products", "status": "pending"},
                {"id": "3", "title": "Update schema markup", "status": "completed"},
            ]
        }

# ============ SEO OPTIMIZATION ============
@app.post("/optimize-seo", response_model=SEOOutput)
async def optimize_seo_endpoint(input_data: ProductInput):
    """Optimize product SEO - uses seo_optimizer.py"""
    try:
        result = await optimize_seo(
            product_title=input_data.product_title,
            supplier_description=input_data.supplier_description,
            category=input_data.category,
            raw_keywords=input_data.raw_keywords,
            price=input_data.price,
            email="commander@vektorflow.com"
        )
        return SEOOutput(
            keywords=result.get("keywords", []),
            seo_title=result.get("seo_title", ""),
            meta_description=result.get("meta_description", ""),
            url_slug=result.get("url_slug", ""),
            schema_markup=result.get("schema_markup", {})
        )
    except Exception as e:
        logger.error(f"SEO optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ OUTREACH GENERATOR ============
@app.post("/api/outreach/generate")
async def generate_outreach(request: OutreachRequest):
    """Generate outreach sequence - uses outreach.py"""
    try:
        email = request.email or "commander@vektorflow.com"
        user_keys = get_llm_keys(email)
        icp = get_icp_data(email)
        
        result = await handle_outreach(
            message=f"Generate {request.platform} outreach for {request.product_type}",
            user_keys=user_keys,
            icp=icp,
            email=email
        )
        
        return {
            "status": "success",
            "sequence": result.get("sequence", []),
            "best_time": result.get("best_time"),
            "follow_up_days": result.get("follow_up_days"),
            "task_id": result.get("task_id"),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Outreach generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ INVENTORY MONITORING ============
@app.get("/api/inventory/check")
async def inventory_check(email: str = "commander@vektorflow.com"):
    """Check inventory across all stores - uses inventory.py"""
    try:
        result = await check_inventory(email)
        return {
            "status": "success",
            "inventory": result.get("inventory", {}),
            "alerts": result.get("alerts", []),
            "alert_count": result.get("alert_count", 0),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Inventory check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/inventory/alerts")
async def inventory_alerts(email: str = "commander@vektorflow.com"):
    """Get inventory alerts - uses inventory.py"""
    try:
        result = await get_inventory_alerts(email)
        return {
            "status": "success",
            "total_alerts": result.get("total_alerts", 0),
            "by_type": result.get("by_type", {}),
            "by_severity": result.get("by_severity", {}),
            "alerts": result.get("alerts", []),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Inventory alerts error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/inventory/reorder")
async def inventory_reorder(email: str = "commander@vektorflow.com"):
    """Get reorder recommendations - uses inventory.py"""
    try:
        result = await get_reorder_recommendations(email)
        return {
            "status": "success",
            "recommendations": result.get("recommendations", {}),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Reorder recommendations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ CAMPAIGN GENERATOR ============
@app.post("/api/campaign/generate")
async def generate_campaign_endpoint(request: CampaignRequest):
    """Generate marketing campaign - uses campaign.py"""
    try:
        email = request.email or "commander@vektorflow.com"
        
        result = await generate_campaign(
            email=email,
            product_type=request.product_type,
            goal=request.goal,
            target_audience=request.target_audience,
            channels=request.channels,
            budget=request.budget,
            timeline_days=request.timeline_days
        )
        
        return {
            "status": "success" if result.get("success") else "error",
            "campaign": result.get("campaign", {}),
            "campaign_id": result.get("campaign_id"),
            "task_id": result.get("task_id"),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Campaign generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ ORGANIC CONTENT GENERATOR ============
@app.post("/api/content/organic")
async def generate_organic_content_endpoint(request: OrganicContentRequest):
    """Generate organic social content - uses organic_content.py"""
    try:
        email = request.email or "commander@vektorflow.com"
        
        result = await generate_organic_content(
            email=email,
            product_name=request.product_name,
            product_description=request.product_description,
            platforms=request.platforms,
            tone=request.tone,
            number_of_options=request.number_of_options
        )
        
        return {
            "status": "success" if result.get("success") else "error",
            "content": result.get("content", {}),
            "content_id": result.get("content_id"),
            "task_id": result.get("task_id"),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Organic content generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ API INFO ============
@app.get("/api/info")
async def api_info():
    """Get API information with all endpoints"""
    return {
        "service": "VektorFlow 15xr",
        "version": "1.0",
        "status": "operational",
        "features": {
            "agent": "Vektor Agent with orchestrator",
            "seo": "SEO optimization",
            "store": "Store auto-connect",
            "outreach": "Outreach generator",
            "inventory": "Inventory monitoring",
            "campaign": "Campaign generator",
            "organic_content": "Organic content generator"
        },
        "endpoints": {
            "login": "/commander/login",
            "agent_chat": "/api/agent/chat",
            "agent_command": "/api/agent/command",
            "ai_chat": "/api/ai/chat",
            "search_products": "/api/products/search",
            "trends": "/api/trends",
            "store_connect": "/api/store/connect",
            "tasks": "/api/tasks",
            "optimize_seo": "/optimize-seo",
            "outreach": "/api/outreach/generate",
            "inventory_check": "/api/inventory/check",
            "inventory_alerts": "/api/inventory/alerts",
            "inventory_reorder": "/api/inventory/reorder",
            "campaign": "/api/campaign/generate",
            "organic_content": "/api/content/organic"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

# ============ WAKEUP ============
@app.get("/wakeup")
async def wakeup():
    return {"status": "awake", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)