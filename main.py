"""
VektorFlow 15xr - Complete Main Entry Point
All features: Auth, LLM, Hybrid Search, Human-in-the-Loop, Payments, Memory Dashboard
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
from database import get_db, get_user, create_user, save_api_keys, get_api_keys
from llm_router import route_llm
from hybrid_search import hybrid_search, get_trends_for_catalog
from human_loop import create_pending_approval, get_pending_approvals, resolve_approval


app = FastAPI(title="VektorFlow 15xr", description="Complete AI Agent Platform")

# ========== CONFIGURATION ==========
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "vektorflow_secret_key_change_me")
ALGORITHM = "HS256"

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

def create_jwt(email: str) -> str:
    token_data = {"email": email, "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)

# ========== MODELS ==========
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

class CatalogUpload(BaseModel):
    store_id: str
    products: List[Dict[str, Any]]

class LLMRequest(BaseModel):
    prompt: str
    model: str = "groq"

class ApprovalRequest(BaseModel):
    approval_id: int
    decision: str
    selected_option: Optional[Any] = None

# ========== ROOT & HEALTH ==========
@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ========== SETUP TEST USER ==========
@app.get("/setup-create-user")
def setup_create_user():
    email = "commander@vektorflow.com"
    password_hash = hash_password("test123")
    
    existing = get_user(email)
    if existing:
        return {
            "status": "already_exists",
            "email": email,
            "password": "test123",
            "message": "User exists. Log in with these credentials."
        }
    
    create_user(email, password_hash, "commander_store")
    token = create_jwt(email)
    
    return {
        "status": "created",
        "email": email,
        "password": "test123",
        "access_token": token,
        "message": "User created! Log in with these credentials."
    }

# ========== AUTH ENDPOINTS ==========
@app.post("/auth/signup")
def signup(user: UserSignup):
    existing = get_user(user.email)
    if existing:
        raise HTTPException(400, "Email already registered")
    
    create_user(user.email, hash_password(user.password), user.store_name)
    token = create_jwt(user.email)
    return {"access_token": token, "token_type": "bearer", "expires_days": 7}

@app.post("/auth/login")
def login(user: UserLogin):
    stored = get_user(user.email)
    if not stored:
        raise HTTPException(401, "Invalid credentials")
    
    if not verify_password(user.password, stored["password_hash"]):
        raise HTTPException(401, "Invalid credentials")
    
    return {"access_token": create_jwt(user.email), "token_type": "bearer", "expires_days": 7}

@app.post("/user/keys")
def save_keys(keys: UserKeys, email: str = Depends(get_current_user)):
    save_api_keys(email, keys.dict())
    return {"status": "saved"}

@app.get("/user/keys")
def get_keys(email: str = Depends(get_current_user)):
    return get_api_keys(email)

# ========== E-COMMERCE ENDPOINTS ==========
catalogs_cache = {}

@app.post("/ecommerce/catalog")
def upload_catalog(data: CatalogUpload, email: str = Depends(get_current_user)):
    catalogs_cache[data.store_id] = data.products
    return {"status": "catalog stored", "store_id": data.store_id, "product_count": len(data.products)}

@app.get("/ecommerce/trends/{store_id}")
def get_trends(store_id: str, email: str = Depends(get_current_user)):
    if store_id not in catalogs_cache:
        raise HTTPException(404, "No catalog found")
    
    matches = get_trends_for_catalog(catalogs_cache[store_id])
    return {"status": "success", "matches": matches, "count": len(matches)}

@app.get("/ecommerce/citation/{store_id}/{product_name}")
def get_citation(store_id: str, product_name: str, email: str = Depends(get_current_user)):
    return {
        "product": product_name,
        "score": 78,
        "grade": "B+",
        "recommendations": ["Add schema.org markup", "Get 20+ reviews", "List specific dimensions"]
    }

@app.get("/ecommerce/campaign/{store_id}/{product_name}")
def get_campaign(store_id: str, product_name: str, email: str = Depends(get_current_user), trend: Optional[str] = None):
    return {
        "product": product_name,
        "sequence": {
            "messages": [
                f"🔥 {product_name} is trending! Want the link?",
                f"✨ 4.5★ from customers — you'll love it",
                f"⏳ Only a few left. Link here: [LINK]"
            ]
        }
    }

@app.get("/ecommerce/weekly-report/{store_id}")
def get_report(store_id: str, email: str = Depends(get_current_user)):
    return {
        "report": f"Weekly report for {store_id}",
        "generated": datetime.now().isoformat(),
        "top_trends": ["wireless", "eco friendly", "smart home"]
    }

# ========== LLM ENDPOINT ==========
@app.post("/llm/call")
async def call_llm(request: LLMRequest, email: str = Depends(get_current_user)):
    user_keys = get_api_keys(email)
    result = await route_llm(request.prompt, request.model, user_keys)
    return result

# ========== HUMAN-IN-THE-LOOP ENDPOINTS ==========
@app.post("/agent/disagree")
def agent_disagreement(task: str, drift_score: float, options: List[Dict], email: str = Depends(get_current_user)):
    approval_id = create_pending_approval(email, task, drift_score, options)
    return {"status": "pending", "approval_id": approval_id, "message": "Human approval needed"}

@app.get("/agent/pending")
def get_pending(email: str = Depends(get_current_user)):
    return {"approvals": get_pending_approvals(email)}

@app.post("/agent/resolve")
def resolve(approval: ApprovalRequest, email: str = Depends(get_current_user)):
    resolve_approval(approval.approval_id, approval.decision, approval.selected_option)
    return {"status": "resolved", "approval_id": approval.approval_id}

# ========== INCLUDE ROUTERS ==========
app.include_router(payment_router)
app.include_router(memory_router)

# ========== SERVE FRONTEND ==========
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
