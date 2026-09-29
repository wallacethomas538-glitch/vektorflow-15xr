from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os, json, logging
from datetime import datetime

from database import get_user, get_user_stores, get_llm_keys, get_icp_data, save_conversation, get_all_memory
from vektor_agent import vektor_chat, detect_intent
from llm_handler import call_llm, DEFAULT_MODEL
from store_manager import search_cj_products, get_cj_product_details, connect_store
from trend_engine import get_tiktok_trends
from agents import run_agent_task, get_orchestrator, get_ad_specialist
from auth import verify_token, create_token
from middleware import APIKeyMiddleware
from seo_optimizer import optimize_seo
from outreach import handle_outreach
from inventory import check_inventory, get_inventory_alerts, get_reorder_recommendations
from campaign import generate_campaign
from organic_content import generate_organic_content

app = FastAPI(title="VektorFlow 15xr", version="1.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
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

class AdImageRequest(BaseModel):
    prompt: str
    model: str = "flux"
    size: str = "1024x1024"

@app.get("/", response_class=HTMLResponse)
async def root():
    if os.path.exists(HTML_PATH):
        return open(HTML_PATH, "r", encoding="utf-8").read()
    return HTMLResponse("<h1>VektorFlow 15XR API</h1>")

@app.get("/health")
async def health():
    return {"status":"healthy","service":"VektorFlow 15xr","timestamp":datetime.utcnow().isoformat()}

@app.post("/commander/login")
async def commander_login(login_data: CommanderLogin):
    try:
        user = get_user(login_data.username)
        if user and user.get("password") == login_data.password:
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

@app.get("/api/agents/{agent_name}")
async def get_agent(agent_name: str):
    agent=get_orchestrator().get_agent(agent_name)
    if not agent: raise HTTPException(status_code=404,detail="Agent not found")
    return {"status":"success","agent":agent.summary(),"timestamp":datetime.utcnow().isoformat()}

@app.post("/api/agents/{agent_name}/chat")
async def agent_specific_chat(agent_name: str, request: AgentChatRequest):
    from agents import AgentContext
    agent = get_orchestrator().get_agent(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        email=request.email or "commander@vektorflow.com"
        context=AgentContext(email=email,user=get_user(email) or {},stores=get_user_stores(email) or [],
            llm_keys=get_llm_keys(email) or {},icp=get_icp_data(email) or {},memory=get_all_memory(email) or {},
            params=request.params or {},conversation_history=request.conversation_history or [])
        result=await agent.run(context,request.message)
        return {"status":"success","agent":agent.summary(),"result":result,"timestamp":datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Individual agent chat error: %s",e)
        raise HTTPException(status_code=500,detail=str(e))
@app.post("/api/agents/run")
async def run_team(request: TeamRunRequest):
    from agents import AgentContext
    try:
        email=request.email
        context=AgentContext(email=email,user=get_user(email) or {},stores=get_user_stores(email) or [],
            llm_keys=get_llm_keys(email) or {},icp=get_icp_data(email) or {},memory={},params=request.params or {})
        result=await get_orchestrator().team_execute(request.goal,context)
        return {"status":"success",**result,"timestamp":datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("Team run error: %s",e); raise HTTPException(status_code=500,detail=str(e))

@app.post("/api/ai/chat")
async def ai_chat(message: AIChatMessage):
    try:
        result=await call_llm(prompt=message.message,model=DEFAULT_MODEL,user_keys=get_llm_keys(message.email or "commander@vektorflow.com"))
        return {"status":"success","response":result.get("response","I'm here to help."),"timestamp":datetime.utcnow().isoformat()}
    except Exception as e:
        logger.error("AI chat error: %s",e); raise HTTPException(status_code=500,detail=str(e))

@app.post("/api/products/search")
async def search_products(request: Request):
    data=await request.json(); keyword=data.get("keyword","")
    if not keyword: raise HTTPException(status_code=400,detail="Keyword required")
    products=await search_cj_products(keyword)
    return {"status":"success","products":products[:10],"count":len(products),"timestamp":datetime.utcnow().isoformat()}

@app.get("/api/trends")
async def get_trends():
    trends=await get_tiktok_trends()
    return {"status":"success","trends":trends[:10],"timestamp":datetime.utcnow().isoformat()}

@app.post("/api/store/connect")
async def store_connect(store_data: StoreConnectRequest):
    connect_store(store_data.email,store_data.platform,store_data.store_url)
    return {"status":"success","message":f"Successfully connected to {store_data.platform}","platform":store_data.platform,"store_url":store_data.store_url,"connected_at":datetime.utcnow().isoformat()}

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

@app.get("/api/info")
async def api_info():
    return {
        "service":"VektorFlow 15xr","version":"1.1","status":"operational","agent_count":15,
        "agent_roster":[{"name":n,"description":d} for n,d in __import__("agents").AGENT_ROLES],
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
