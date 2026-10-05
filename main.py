from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os, json, logging, asyncio
from datetime import datetime

from database import get_user, get_user_stores, get_llm_keys, get_icp_data, save_conversation, get_all_memory, save_store_token
from vektor_agent import vektor_chat, detect_intent
from llm_handler import call_llm, DEFAULT_MODEL
from store_manager import search_cj_products, get_cj_product_details, connect_store, ShopifyAPI
from oauth_handler import generate_oauth_url, exchange_code_for_token
from trend_engine import get_tiktok_trends
from vektorflow_agents import run_agent_task, get_orchestrator, get_ad_specialist
from auth import verify_token, create_token, authenticate_user
from middleware import APIKeyMiddleware
from seo_optimizer import optimize_seo
from outreach import handle_outreach
from inventory import check_inventory, get_inventory_alerts, get_reorder_recommendations
from campaign import generate_campaign
from organic_content import generate_organic_content
from mission_control_api import router as mission_control_router
from memory_api import router as memory_router
from ai_observability import observability_status
from workflow_runs import new_run as _new_workflow_run, get_run as _get_workflow_run, \
    list_runs as _list_workflow_runs, request_cancel as _request_workflow_cancel, \
    public_view as _workflow_run_view
from execution_gateway import router as execution_gateway_router
from second_brain_api import router as second_brain_router

app = FastAPI(title="VektorFlow 15xr", version="1.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(mission_control_router)
app.include_router(memory_router)
app.include_router(execution_gateway_router)
app.include_router(second_brain_router)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vektorflow")
ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY", "")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
HTML_PATH = os.path.join(STATIC_DIR, "index.html")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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
    temperature: Optional[float] = None
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
class TeamRunRequest(BaseModel):
    goal: str
    email: str = "commander@vektorflow.com"
    params: Optional[Dict[str, Any]] = {}
class AgentChatRequest(BaseModel):
    message: str
    email: str = "commander@vektorflow.com"
    conversation_history: Optional[List[Dict[str, Any]]] = []
    params: Optional[Dict[str, Any]] = {}
    temperature: Optional[float] = None

class AgentToolRequest(BaseModel):
    email: str = "commander@vektorflow.com"
    arguments: Optional[Dict[str, Any]] = {}

class AdImageRequest(BaseModel):
    prompt: str
    model: str = "flux"
    size: str = "1024x1024"

def _validate_temperature(value):
    """Return a clamped-validated temperature, or None. Raises 400 if out of range."""
    if value is None:
        return None
    try:
        t = float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="temperature must be a number between 0.0 and 2.0")
    if not 0.0 <= t <= 2.0:
        raise HTTPException(status_code=400, detail="temperature must be between 0.0 and 2.0")
    return t

@app.get("/", response_class=HTMLResponse)
async def root():
    if os.path.exists(HTML_PATH):
        return open(HTML_PATH, "r", encoding="utf-8").read()
    return HTMLResponse("<h1>VektorFlow 15XR API</h1>")

@app.get("/health")
async def health():
    return {"status":"healthy","service":"VektorFlow 15xr","timestamp":datetime.utcnow().isoformat()}

@app.get("/health/supabase")
async def supabase_health():
    configured = bool(os.environ.get("DATABASE_URL"))
    connected = False
    if configured:
        try:
            from supabase_runtime import _connect
            conn = _connect()
            connected = conn is not None
            if conn is not None:
                conn.close()
        except Exception:
            connected = False
    return {"status":"ok" if connected else "not_connected","database_url_configured":configured,"supabase_postgres_connected":connected}

@app.post("/commander/login")
async def commander_login(login_data: CommanderLogin):
    try:
        user = authenticate_user(login_data.username, login_data.password, get_user)
        if user:
            token=create_token({"email":login_data.username,"role":"admin"})
            return {"status":"success","message":"Login successful","token":token,"user":{"username":login_data.username,"role":"admin","permissions":["full_access"]}}
        valid=os.environ.get("VEKTORFLOW_ADMIN_PASSWORD","")
        if login_data.username=="commander@vektorflow.com" and login_data.password==valid:
            token=create_token({"email":login_data.username,"role":"admin"})
            return {"status":"success","message":"Login successful","token":token,"user":{"username":login_data.username,"role":"admin"}}
        raise HTTPException(status_code=401,detail="Invalid credentials")
    except HTTPException: raise
    except Exception as e:
        logger.error("Login error: %s",e); raise HTTPException(status_code=500,detail=str(e))

@app.post("/auth/login")
async def auth_login(login_data: CommanderLogin): return await commander_login(login_data)
@app.post("/login")
async def login(login_data: CommanderLogin): return await commander_login(login_data)

@app.post("/api/agent/chat")
async def agent_chat(message: AIChatMessage):
    email=message.email or "commander@vektorflow.com"
    try:
        result=await vektor_chat(email=email,message=message.message,conversation_history=message.context)
        try: save_conversation(email,message.message,result.get("response",""),message.conversation_id)
        except Exception: pass
        return {"status":"success","response":result.get("response","I'm here to help, Commander."),"action":result.get("action","chat"),"data":result.get("data",{}),"timestamp":datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Agent chat error: %s",e); raise HTTPException(status_code=500,detail=str(e))

@app.post("/api/agent/command")
async def agent_command(command: AgentCommand):
    try:
        intent = detect_intent(command.command, {})
        if intent == "general":
            result = await vektor_chat(
                email="commander@vektorflow.com",
                message=command.command,
                conversation_history=None,
            )
            return {
                "status": "success",
                "intent": intent,
                "response": result.get("response", "I'm here to help."),
                "action": result.get("action", "chat"),
                "data": result.get("data", {}),
                "timestamp": datetime.utcnow().isoformat(),
            }

        result = await run_agent_task(
            "commander@vektorflow.com",
            "Vektor",
            command.command,
            command.params or {},
        )
        return {
            "status": "success",
            "intent": intent,
            "response": result.get("message", result.get("response", "")) if isinstance(result, dict) else str(result),
            "result": result,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        logger.error("Agent command error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agents")
async def list_agents():
    roster=get_orchestrator().roster()
    return {"status":"success","count":len(roster),"agents":roster,"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/agents/runs")
async def list_team_runs():
    return {"status":"success","runs":_list_workflow_runs(),"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/agents/runs/{run_id}")
async def get_team_run(run_id: str):
    run=_get_workflow_run(run_id)
    if not run:
        raise HTTPException(status_code=404,detail="Run not found")
    view=_workflow_run_view(run)
    if run["status"] in ("completed","cancelled","failed") and run.get("result") is not None:
        view["result"]=run["result"]
    return {"status":"success","run":view,"timestamp":datetime.utcnow().isoformat()}

@app.delete("/api/agents/runs/{run_id}")
async def cancel_team_run(run_id: str):
    run=_request_workflow_cancel(run_id)
    if not run:
        raise HTTPException(status_code=404,detail="Run not found or already finished")
    return {"status":"cancel_requested","run_id":run_id,"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/agents/{agent_name}")
async def get_agent(agent_name: str):
    agent=get_orchestrator().get_agent(agent_name)
    if not agent: raise HTTPException(status_code=404,detail="Agent not found")
    return {"status":"success","agent":agent.summary(),"timestamp":datetime.utcnow().isoformat()}

@app.post("/api/agents/{agent_name}/tools/{tool_name}")
async def agent_tool(agent_name: str, tool_name: str, request: AgentToolRequest):
    from vektorflow_agents import AgentContext
    agent = get_orchestrator().get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if tool_name not in {t.get("name") for t in agent.tools}:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' is not available to {agent_name}")
    email=request.email or "commander@vektorflow.com"
    context=AgentContext(email=email,user=get_user(email) or {},stores=get_user_stores(email) or [],
        llm_keys=get_llm_keys(email) or {},icp=get_icp_data(email) or {},memory=get_all_memory(email) or {},
        params=request.arguments or {})
    context.params["agent_name"]=agent.name
    try:
        result=await agent.use_tool(tool_name,context,**(request.arguments or {}))
        return {"status":"success","agent":agent.name,"tool":tool_name,"result":result,"timestamp":datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Agent tool error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/agents/{agent_name}/chat")
async def agent_specific_chat(agent_name: str, request: AgentChatRequest):
    from vektorflow_agents import AgentContext
    agent = get_orchestrator().get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        email=request.email or "commander@vektorflow.com"
        temperature=_validate_temperature(request.temperature)
        params={**(request.params or {}), "conversation_mode": "direct", "agent_name": agent.name}
        if temperature is not None:
            params["temperature"]=temperature
        context=AgentContext(email=email,user=get_user(email) or {},stores=get_user_stores(email) or [],
            llm_keys=get_llm_keys(email) or {},icp=get_icp_data(email) or {},memory=get_all_memory(email) or {},
            params=params,conversation_history=request.conversation_history or [])
        result=await agent.run(context,request.message)
        if isinstance(result, dict) and result.get("status") == "failed":
            raise HTTPException(status_code=502, detail=result.get("error", "Agent execution failed"))
        return {"status":"success","agent":agent.summary(),"result":result,"timestamp":datetime.utcnow().isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Individual agent chat error: %s",e)
        raise HTTPException(status_code=500,detail=str(e))

async def _run_team_workflow(run_id,goal,context):
    """Background body for a team workflow run; records outcome in the run registry."""
    run=_get_workflow_run(run_id)
    try:
        run["status"]="running"
        result=await get_orchestrator().team_execute(goal,context,cancel_event=run["cancel_event"])
        run["status"]=result.get("status","completed")
        run["result"]=result
    except asyncio.CancelledError:
        # team_execute normally converts cancellation into a partial "cancelled"
        # result; this guards the case where it propagates instead.
        if run["status"] != "cancelled":
            run["status"]="cancelled"
        raise
    except Exception as e:
        logger.error("Team run %s failed: %s",run_id,e)
        run["status"]="failed"
        run["error"]=str(e)
    finally:
        run["completed_at"]=datetime.utcnow().isoformat()

@app.post("/api/agents/run")
async def run_team(request: TeamRunRequest, wait: bool = False):
    from vektorflow_agents import AgentContext
    try:
        email=request.email
        context=AgentContext(email=email,user=get_user(email) or {},stores=get_user_stores(email) or [],
            llm_keys=get_llm_keys(email) or {},icp=get_icp_data(email) or {},memory={},params=request.params or {})
        if wait:
            # Legacy synchronous behavior: await the full 15-agent workflow.
            result=await get_orchestrator().team_execute(request.goal,context)
            return {"status":"success",**result,"timestamp":datetime.utcnow().isoformat()}
        run=_new_workflow_run(request.goal)
        run["task"]=asyncio.create_task(_run_team_workflow(run["run_id"],request.goal,context))
        return {"status":"started","run_id":run["run_id"],"timestamp":datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Team run error: %s",e); raise HTTPException(status_code=500,detail=str(e))

@app.post("/api/ai/chat")
async def ai_chat(message: AIChatMessage):
    try:
        temperature=_validate_temperature(message.temperature)
        result=await call_llm(prompt=message.message,model=DEFAULT_MODEL,user_keys=get_llm_keys(message.email or "commander@vektorflow.com"),temperature=temperature)
        return {"status":"success","response":result.get("response","I'm here to help."),"timestamp":datetime.utcnow().isoformat()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("AI chat error: %s",e); raise HTTPException(status_code=500,detail=str(e))

@app.get("/api/ai/debug")
async def ai_debug():
    """Diagnostic: run a minimal LLM call and return the raw result including errors."""
    import os
    try:
        result=await call_llm(prompt="Say OK",model=DEFAULT_MODEL,user_keys=get_llm_keys("commander@vektorflow.com"),temperature=None)
        safe=dict(result)
        # never leak key material
        safe.pop("api_key",None)
        return {"status":"success","default_model":DEFAULT_MODEL,
                "openrouter_key_present":bool(os.getenv("OPENROUTER_API_KEY")),
                "openrouter_key_len":len(os.getenv("OPENROUTER_API_KEY","")),
                "llm_result":safe,"timestamp":datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("AI debug error: %s",e); raise HTTPException(status_code=500,detail=str(e))

@app.post("/api/products/search")
async def search_products(request: Request):
    data=await request.json(); keyword=data.get("keyword","")
    if not keyword: raise HTTPException(status_code=400,detail="Keyword required")
    products=await search_cj_products(keyword)
    if not products:
        raise HTTPException(status_code=502, detail="CJ product search returned no results or CJ credentials are not configured.")
    return {"status":"success","products":products[:10],"count":len(products),"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/trends")
async def get_trends():
    trends=await get_tiktok_trends()
    return {"status":"success","trends":trends[:10],"timestamp":datetime.utcnow().isoformat()}

@app.post("/api/store/connect")
async def store_connect(store_data: StoreConnectRequest):
    connect_store(store_data.email,store_data.platform,store_data.store_url)
    return {"status":"success","message":f"Successfully connected to {store_data.platform}","platform":store_data.platform,"store_url":store_data.store_url,"connected_at":datetime.utcnow().isoformat()}

# ============ SHOPIFY OAUTH + READ-ONLY SHOP DATA ============
def _shopify_oauth_configured() -> bool:
    return bool(os.environ.get("SHOPIFY_CLIENT_ID") and os.environ.get("SHOPIFY_CLIENT_SECRET"))

def _shopify_redirect_uri(request: Request) -> str:
    configured = os.environ.get("SHOPIFY_OAUTH_REDIRECT_URI", "").strip()
    if configured:
        return configured
    return f"{str(request.base_url).rstrip('/')}/api/shopify/oauth/callback"

def _get_shopify_store(email: str) -> Optional[Dict[str, Any]]:
    for store in get_user_stores(email) or []:
        if (store.get("platform") or "").lower() == "shopify" and store.get("access_token"):
            return store
    return None

@app.get("/api/shopify/oauth/start")
async def shopify_oauth_start(request: Request, shop: str, email: str = "commander@vektorflow.com"):
    if not _shopify_oauth_configured():
        raise HTTPException(status_code=500, detail="SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET are not configured on the server.")
    redirect_uri = _shopify_redirect_uri(request)
    oauth_url, _state = generate_oauth_url("shopify", shop, redirect_uri)
    if not oauth_url:
        raise HTTPException(status_code=500, detail="Could not build the Shopify OAuth URL.")
    return RedirectResponse(url=oauth_url)

@app.get("/api/shopify/oauth/callback")
async def shopify_oauth_callback(request: Request, code: Optional[str] = None, shop: Optional[str] = None, email: str = "commander@vektorflow.com"):
    if not _shopify_oauth_configured():
        raise HTTPException(status_code=500, detail="SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET are not configured on the server.")
    if not code or not shop:
        raise HTTPException(status_code=400, detail="Missing required query params: code and shop.")
    result = await exchange_code_for_token("shopify", code, shop)
    if not result.get("success") or not result.get("access_token"):
        raise HTTPException(status_code=502, detail=f"Shopify token exchange failed: {result.get('error', 'unknown error')}")
    store_url = shop if "://" in shop else f"https://{shop}"
    save_store_token(email, "shopify", store_url, result["access_token"])
    return {"status":"success","message":"Shopify store connected","shop":shop,"store_url":store_url,"connected_at":datetime.utcnow().isoformat()}

@app.get("/api/shopify/products")
async def shopify_products(email: str = "commander@vektorflow.com", limit: int = 50):
    store = _get_shopify_store(email)
    if not store:
        raise HTTPException(status_code=400, detail="No Shopify store with an access token is connected. Complete OAuth via /api/shopify/oauth/start first.")
    api = ShopifyAPI(store_url=store["store_url"], access_token=store["access_token"])
    try:
        result = await api.get_products(limit=limit)
    finally:
        await api.client.aclose()
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=f"Shopify API error: {result.get('error')}")
    return {"status":"success","shop":store["store_url"],"count":len(result.get("products",[])),"products":result.get("products",[]),"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/shopify/orders")
async def shopify_orders(email: str = "commander@vektorflow.com", limit: int = 50):
    store = _get_shopify_store(email)
    if not store:
        raise HTTPException(status_code=400, detail="No Shopify store with an access token is connected. Complete OAuth via /api/shopify/oauth/start first.")
    api = ShopifyAPI(store_url=store["store_url"], access_token=store["access_token"])
    try:
        result = await api.get_orders(limit=limit)
    finally:
        await api.client.aclose()
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=f"Shopify API error: {result.get('error')}")
    return {"status":"success","shop":store["store_url"],"count":len(result.get("orders",[])),"orders":result.get("orders",[]),"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/tasks")
async def get_tasks():
    try:
        from database import get_tasks
        return {"status":"success","tasks":get_tasks()}
    except Exception:
        return {"status":"success","tasks":[]}

@app.post("/optimize-seo",response_model=SEOOutput)
async def optimize_seo_endpoint(input_data: ProductInput):
    result=await optimize_seo(product_title=input_data.product_title,supplier_description=input_data.supplier_description,category=input_data.category,raw_keywords=input_data.raw_keywords,price=input_data.price,email="commander@vektorflow.com")
    return SEOOutput(keywords=result.get("keywords",[]),seo_title=result.get("seo_title",""),meta_description=result.get("meta_description",""),url_slug=result.get("url_slug",""),schema_markup=result.get("schema_markup",{}))

@app.post("/api/outreach/generate")
async def generate_outreach(request: OutreachRequest):
    email=request.email or "commander@vektorflow.com"
    result=await handle_outreach(message=f"Generate {request.platform} outreach for {request.product_type}",user_keys=get_llm_keys(email),icp=get_icp_data(email),email=email)
    return {"status":"success","sequence":result.get("sequence",[]),"best_time":result.get("best_time"),"follow_up_days":result.get("follow_up_days"),"task_id":result.get("task_id"),"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/inventory/check")
async def inventory_check(email: str="commander@vektorflow.com"):
    result=await check_inventory(email); return {"status":"success",**result,"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/inventory/alerts")
async def inventory_alerts(email: str="commander@vektorflow.com"):
    result=await get_inventory_alerts(email); return {"status":"success",**result,"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/inventory/reorder")
async def inventory_reorder(email: str="commander@vektorflow.com"):
    result=await get_reorder_recommendations(email); return {"status":"success",**result,"timestamp":datetime.utcnow().isoformat()}

@app.post("/api/campaign/generate")
async def generate_campaign_endpoint(request: CampaignRequest):
    result=await generate_campaign(email=request.email or "commander@vektorflow.com",product_type=request.product_type,goal=request.goal,target_audience=request.target_audience,channels=request.channels,budget=request.budget,timeline_days=request.timeline_days)
    return {"status":"success" if result.get("success") else "error","campaign":result.get("campaign",{}),"campaign_id":result.get("campaign_id"),"task_id":result.get("task_id"),"timestamp":datetime.utcnow().isoformat()}

@app.post("/api/content/organic")
async def generate_organic_content_endpoint(request: OrganicContentRequest):
    result=await generate_organic_content(email=request.email or "commander@vektorflow.com",product_name=request.product_name,product_description=request.product_description,platforms=request.platforms,tone=request.tone,number_of_options=request.number_of_options)
    return {"status":"success" if result.get("success") else "error","content":result.get("content",{}),"content_id":result.get("content_id"),"task_id":result.get("task_id"),"timestamp":datetime.utcnow().isoformat()}



@app.get("/api/analytics/metrics")
async def get_analytics_metrics():
    from src.analytics import AnalyticsClient
    analytics = AnalyticsClient()
    analytics.increment_metric("api_calls")
    return JSONResponse(status_code=200, content=analytics.get_metrics())

@app.get("/api/observability")
async def observability():
    """Report configured AI observability backends without exposing credentials."""
    return {"status": "success", "observability": observability_status(), "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/tools")
async def list_external_tools():
    from external_tools import tool_status
    return {"status": "success", "tools": tool_status(), "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/info")
async def api_info():
    return {
        "service":"VektorFlow 15xr","version":"1.1","status":"operational","agent_count":15,
        "agent_roster":[{"name":n,"description":d} for n,d in __import__("vektorflow_agents").AGENT_ROLES],
        "features":{"agent":"15-agent cooperative orchestrator","seo":"SEO optimization","store":"Store auto-connect","outreach":"Outreach generator","inventory":"Inventory monitoring","campaign":"Campaign generator","organic_content":"Organic content generator"},
        "endpoints":{"login":"/commander/login","agent_chat":"/api/agent/chat","agent_command":"/api/agent/command","agents":"/api/agents","agent_detail":"/api/agents/{agent_name}","agent_chat":"/api/agents/{agent_name}/chat","team_run":"/api/agents/run","ai_chat":"/api/ai/chat","search_products":"/api/products/search","trends":"/api/trends","store_connect":"/api/store/connect","tasks":"/api/tasks","optimize_seo":"/optimize-seo","outreach":"/api/outreach/generate","inventory_check":"/api/inventory/check","inventory_alerts":"/api/inventory/alerts","inventory_reorder":"/api/inventory/reorder","campaign":"/api/campaign/generate","organic_content":"/api/content/organic"},
        "timestamp":datetime.utcnow().isoformat()
    }

@app.post("/api/ads/generate-image")
async def generate_ad_image(request_data: AdImageRequest):
    """Generate advertisement imagery exclusively through the VektorFlow AdSpecialist."""
    try:
        return await get_ad_specialist().generate_image(
            prompt=request_data.prompt,
            model=request_data.model,
            size=request_data.size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.error("AdSpecialist image generation failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected AdSpecialist image error")
        raise HTTPException(status_code=502, detail="AdSpecialist image generation failed")

@app.get("/wakeup")
async def wakeup(): return {"status":"awake","timestamp":datetime.utcnow().isoformat()}

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("PORT",10000)))
