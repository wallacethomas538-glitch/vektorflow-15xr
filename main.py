"""
VektorFlow 15xr - Main Entry Point
15 agents. Memory fabric. Cognition sharing. E-commerce intelligence.
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

# Import all modules
from memory_fabric import MemoryFabric
from agent_with_memory import VektorAgent
from kill_switch import KillSwitch
from free_tier_router import FreeTierRouter
from monitor_agent import MonitorAgent
from interference_merge import InterferenceMerge
from semantic_pattern_operator import SemanticPatternOperator
from cognition_fabric import CognitionFabric
from trend_to_catalog_mapper import TrendToCatalogMapper
from ai_citation_optimizer import AICitationOptimizer
from click_to_message_builder import ClickToMessageBuilder
from social_commerce_connector import SocialCommerceConnector
from weekly_report_generator import WeeklyReportGenerator

app = FastAPI(title="VektorFlow 15xr", description="15 agents with memory fabric + e-commerce intelligence")

# ========== CONFIGURATION ==========
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "vektorflow_secret_key_change_me")
ALGORITHM = "HS256"

# ========== INITIALIZATION ==========
agents: Dict[str, VektorAgent] = {}
kill_switch = KillSwitch()
memory = MemoryFabric()
catalogs = {}

# ========== HELPER FUNCTIONS ==========
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed

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
class TaskRequest(BaseModel):
    agent_id: str
    task: str
    data: Dict[str, Any]

class CatalogUpdate(BaseModel):
    store_id: str
    products: List[Dict[str, Any]]

class UserSignup(BaseModel):
    email: str
    password: str
    store_name: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserKeys(BaseModel):
    groq_api_key: Optional[str] = ""
    gemini_api_key: Optional[str] = ""
    hf_api_key: Optional[str] = ""

class LLMRequest(BaseModel):
    prompt: str
    model: str = "groq"
    fallback: bool = True

class MergeRequest(BaseModel):
    responses: List[Dict[str, Any]]

class PatternRequest(BaseModel):
    events: List[Dict[str, Any]]
    pattern: List[str]

# ========== ROOT & HEALTH ==========
@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ========== ONE-TIME SETUP: CREATE TEST USER (NO ADMIN KEY NEEDED) ==========
# After you run this once, you can delete this endpoint or keep it.
# Go to: https://vektorflow-15xr.onrender.com/setup-create-user
@app.get("/setup-create-user")
def setup_create_user():
    email = "commander@vektorflow.com"
    password_hash = hash_password("test123")
    
    # Check if user already exists
    existing = memory.get_shared_context(f"user_{email}")
    if existing:
        return {
            "status": "already_exists",
            "email": email,
            "password": "test123",
            "message": "User already exists. Just log in with these credentials."
        }
    
    # Create the user
    user_data = {
        "email": email,
        "password_hash": password_hash,
        "store_name": "commander_store",
        "tier": "trial",
        "trial_expires": (datetime.utcnow() + timedelta(days=7)).isoformat(),
        "created_at": datetime.utcnow().isoformat()
    }
    memory.update_shared_context(f"user_{email}", user_data, "setup")
    
    # Create a JWT token for immediate use
    token_data = {
        "email": email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    return {
        "status": "created",
        "email": email,
        "password": "test123",
        "access_token": token,
        "message": "User created! Use these credentials to log in."
    }

# ========== AUTHENTICATION ENDPOINTS ==========
@app.post("/auth/signup")
def signup(user: UserSignup):
    # Check if user exists
    existing = memory.get_shared_context(f"user_{user.email}")
    if existing:
        raise HTTPException(400, "Email already registered")
    
    user_data = {
        "email": user.email,
        "password_hash": hash_password(user.password),
        "store_name": user.store_name,
        "tier": "trial",
        "trial_expires": (datetime.utcnow() + timedelta(days=7)).isoformat(),
        "created_at": datetime.utcnow().isoformat()
    }
    memory.update_shared_context(f"user_{user.email}", user_data, "signup")
    
    # Create JWT token
    token_data = {
        "email": user.email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    return {"access_token": token, "token_type": "bearer", "expires_days": 7}

@app.post("/auth/login")
def login(user: UserLogin):
    stored = memory.get_shared_context(f"user_{user.email}")
    if not stored:
        raise HTTPException(401, "Invalid credentials")
    
    if not verify_password(user.password, stored["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    
    # Check trial expiration
    expires_at = datetime.fromisoformat(stored["trial_expires"])
    if expires_at < datetime.utcnow():
        raise HTTPException(403, "Trial expired. Please upgrade.")
    
    token_data = {
        "email": user.email,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    
    return {"access_token": token, "token_type": "bearer", "expires_days": 7}

# ========== USER API KEYS ENDPOINTS ==========
@app.post("/user/keys")
def save_user_keys(keys: UserKeys, email: str = Depends(get_current_user)):
    memory.update_shared_context(f"user_{email}_api_keys", keys.dict(), "user")
    return {"status": "saved"}

@app.get("/user/keys")
def get_user_keys(email: str = Depends(get_current_user)):
    keys = memory.get_shared_context(f"user_{email}_api_keys")
    return keys or {}

# ========== CORE AGENT ENDPOINTS ==========
@app.post("/agent/register")
def register_agent(agent_id: str, email: str = Depends(get_current_user)):
    if agent_id not in agents:
        agents[agent_id] = VektorAgent(agent_id)
    return {"status": "registered", "agent_id": agent_id, "total_agents": len(agents)}

@app.post("/agent/run")
def run_agent(request: TaskRequest, email: str = Depends(get_current_user)):
    if kill_switch.is_killed(request.agent_id):
        raise HTTPException(403, f"Agent {request.agent_id} is killed")
    
    if request.agent_id not in agents:
        agents[request.agent_id] = VektorAgent(request.agent_id)
    
    result = agents[request.agent_id].run(request.task, request.data)
    return result

@app.get("/agents")
def list_agents(email: str = Depends(get_current_user)):
    return {"agents": list(agents.keys()), "count": len(agents)}

# ========== ADMIN ENDPOINTS ==========
@app.post("/admin/kill/{agent_id}")
def kill_agent(agent_id: str, x_admin_key: str = Header(...)):
    if x_admin_key != os.environ.get("ADMIN_API_KEY", "change_me"):
        raise HTTPException(401, "Invalid admin key")
    kill_switch.kill(agent_id)
    return {"status": "killed", "agent_id": agent_id}

@app.post("/admin/revive/{agent_id}")
def revive_agent(agent_id: str, x_admin_key: str = Header(...)):
    if x_admin_key != os.environ.get("ADMIN_API_KEY", "change_me"):
        raise HTTPException(401, "Invalid admin key")
    kill_switch.revive(agent_id)
    return {"status": "revived", "agent_id": agent_id}

# ========== MEMORY ENDPOINTS ==========
@app.get("/memory/{agent_id}")
def get_agent_memory(agent_id: str, email: str = Depends(get_current_user), limit: int = 50):
    episodes = memory.get_episodes(agent_id, limit)
    return {"agent_id": agent_id, "episodes": episodes, "count": len(episodes)}

@app.get("/context")
def get_shared_context(email: str = Depends(get_current_user)):
    return memory.get_all_shared_context()

# ========== E-COMMERCE ENDPOINTS ==========
@app.post("/ecommerce/catalog")
def upload_catalog(data: CatalogUpdate, email: str = Depends(get_current_user)):
    catalogs[data.store_id] = data.products
    memory.update_shared_context(f"catalog_{data.store_id}", data.products, "api")
    memory.update_shared_context(f"user_{email}_catalog", data.store_id, "api")
    return {"status": "catalog stored", "store_id": data.store_id, "product_count": len(data.products)}

@app.get("/ecommerce/trends/{store_id}")
def get_trending_matches(store_id: str, email: str = Depends(get_current_user)):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found. Upload catalog first.")
    mapper = TrendToCatalogMapper(catalogs[store_id])
    result = mapper.run_weekly()
    mapper.close()
    return result

@app.get("/ecommerce/citation/{store_id}/{product_name}")
def get_citation_score(store_id: str, product_name: str, email: str = Depends(get_current_user)):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found")
    product = next((p for p in catalogs[store_id] if p.get("name", "").lower() == product_name.lower()), None)
    if not product:
        raise HTTPException(404, "Product not found")
    optimizer = AICitationOptimizer()
    return optimizer.calculate_citation_score(product)

@app.get("/ecommerce/campaign/{store_id}/{product_name}")
def generate_campaign(store_id: str, product_name: str, email: str = Depends(get_current_user), trend: Optional[str] = None):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found")
    product = next((p for p in catalogs[store_id] if p.get("name", "").lower() == product_name.lower()), None)
    if not product:
        raise HTTPException(404, "Product not found")
    builder = ClickToMessageBuilder()
    sequence = builder.generate_sequence(product, trend)
    ad_copy = builder.generate_ad_copy(product, trend)
    return {"product": product.get("name"), "sequence": sequence, "ad_copy": ad_copy}

@app.get("/ecommerce/weekly-report/{store_id}")
def get_weekly_report(store_id: str, email: str = Depends(get_current_user)):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found")
    generator = WeeklyReportGenerator(catalogs[store_id])
    report = generator.generate_full_report()
    generator.close()
    return {"report": report, "store_id": store_id}

@app.get("/ecommerce/social-export/{store_id}")
def export_social_csv(store_id: str, email: str = Depends(get_current_user), platform: str = "tiktok"):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found")
    connector = SocialCommerceConnector()
    if platform == "tiktok":
        csv_data = connector.generate_tiktok_shop_csv(catalogs[store_id])
        return {"csv": csv_data, "format": "csv"}
    elif platform == "instagram":
        return connector.generate_instagram_product_tags(catalogs[store_id])
    else:
        raise HTTPException(400, "Platform must be 'tiktok' or 'instagram'")

# ========== LLM ROUTING ENDPOINT ==========
@app.post("/llm/call")
async def call_llm(request: LLMRequest, email: str = Depends(get_current_user)):
    user_keys = memory.get_shared_context(f"user_{email}_api_keys") or {}
    router = FreeTierRouter()
    result = await router.call(request.prompt, request.model, request.fallback, user_keys)
    return result

# ========== INTERFERENCE MERGE ENDPOINT ==========
@app.post("/merge")
def merge_responses(request: MergeRequest, email: str = Depends(get_current_user)):
    result = InterferenceMerge.merge(request.responses)
    return result

# ========== PATTERN DETECTION ENDPOINT ==========
@app.post("/pattern/detect")
def detect_pattern(request: PatternRequest, email: str = Depends(get_current_user)):
    operator = SemanticPatternOperator()
    for event in request.events:
        operator.add_event(event)
    detected = operator.detect_pattern(request.pattern)
    return {"pattern": request.pattern, "detected": detected}

# ========== SERVE FRONTEND ==========
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
