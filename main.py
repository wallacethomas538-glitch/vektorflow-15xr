"""
VektorFlow 15xr - Main Entry Point (All-in-One)
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
import httpx
import sqlite3
import json

app = FastAPI(title="VektorFlow 15xr")

# ========== DATABASE SETUP ==========
DB_PATH = "vektorflow.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            store_name TEXT,
            tier TEXT DEFAULT 'trial',
            trial_expires TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_keys (
            email TEXT PRIMARY KEY,
            groq_key TEXT,
            gemini_key TEXT,
            hf_key TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalogs (
            store_id TEXT,
            email TEXT,
            products TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (store_id, email)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            sku TEXT NOT NULL,
            product_name TEXT NOT NULL,
            current_stock INTEGER DEFAULT 0,
            reorder_point INTEGER DEFAULT 0,
            unit_cost REAL DEFAULT 0,
            selling_price REAL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

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

class UserKeys(BaseModel):
    groq_api_key: Optional[str] = ""
    gemini_api_key: Optional[str] = ""
    hf_api_key: Optional[str] = ""

class CatalogUpload(BaseModel):
    store_id: str
    products: List[Dict[str, Any]]

class LLMRequest(BaseModel):
    prompt: str
    model: str = "llama-3.3-70b-versatile"

# ========== DIRECT GROQ CALL FUNCTION ==========
async def call_groq_direct(prompt: str, api_key: str, model: str) -> Dict:
    """Direct Groq API call - no external router needed"""
    if not api_key:
        return {"success": False, "error": "No Groq API key provided"}
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            if response.status_code == 200:
                data = response.json()
                ai_response = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": ai_response, "model": model}
            else:
                error_text = response.text[:200] if response.text else "Unknown error"
                return {"success": False, "error": f"Groq API error {response.status_code}: {error_text}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}

# ========== ROOT ==========
@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ========== DEBUG ==========
@app.get("/debug/check-env")
def check_env():
    groq_key = os.environ.get("GROQ_API_KEY")
    return {
        "groq_key_exists": bool(groq_key),
        "groq_key_preview": groq_key[:15] + "..." if groq_key and len(groq_key) > 15 else groq_key,
        "jwt_key_exists": bool(os.environ.get("JWT_SECRET_KEY")),
        "admin_key_exists": bool(os.environ.get("ADMIN_API_KEY")),
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

# ========== API KEYS ==========
@app.post("/user/keys")
def save_keys(keys: UserKeys, email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_keys (email, groq_key, gemini_key, hf_key, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (email, keys.groq_api_key, keys.gemini_api_key, keys.hf_api_key))
    conn.commit()
    conn.close()
    return {"status": "saved"}

@app.get("/user/keys")
def get_keys(email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_keys WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

# ========== LLM ENDPOINT ==========
@app.post("/llm/call")
async def call_llm(request: LLMRequest, email: str = Depends(get_current_user)):
    # Get user's Groq key from database or environment
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT groq_key FROM user_keys WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    
    groq_key = row["groq_key"] if row else os.environ.get("GROQ_API_KEY")
    
    if not groq_key:
        return {"success": False, "error": "No Groq API key found. Add it in Your API Keys section or set GROQ_API_KEY environment variable."}
    
    # Call Groq directly
    result = await call_groq_direct(request.prompt, groq_key, request.model)
    return result

# ========== E-COMMERCE ==========
catalogs_cache = {}

@app.post("/ecommerce/catalog")
def upload_catalog(data: CatalogUpload, email: str = Depends(get_current_user)):
    catalogs_cache[data.store_id] = data.products
    return {"status": "catalog stored", "store_id": data.store_id, "product_count": len(data.products)}

@app.get("/ecommerce/trends/{store_id}")
def get_trends(store_id: str, email: str = Depends(get_current_user)):
    if store_id not in catalogs_cache:
        raise HTTPException(404, "No catalog found")
    
    products = catalogs_cache[store_id]
    trends = ["wireless", "fitness", "eco friendly", "smart", "bluetooth", "waterproof", "organic", "portable"]
    
    matches = []
    for product in products[:20]:
        name = product.get("name", "").lower()
        desc = product.get("description", "").lower()
        for trend in trends:
            if trend in name or trend in desc:
                matches.append({
                    "product": product.get("name"),
                    "trend": trend,
                    "campaign_angle": f"🔥 {product.get('name')} is trending with '{trend}' — shop now!"
                })
                break
    
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

# ========== GROQ MODELS ENDPOINT ==========
@app.get("/groq/models")
async def get_groq_models(email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT groq_key FROM user_keys WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    
    groq_key = row["groq_key"] if row else os.environ.get("GROQ_API_KEY")
    
    if not groq_key:
        return {"success": False, "models": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B"},
            {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B"}
        ]}
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {groq_key}"}
            )
            if response.status_code == 200:
                data = response.json()
                all_models = data.get("data", [])
                active_models = []
                for model in all_models:
                    model_id = model.get("id", "")
                    if any(x in model_id for x in ['llama', 'gpt-oss', 'qwen']):
                        active_models.append({
                            "id": model_id,
                            "name": model_id.replace("-", " ").title()
                        })
                return {"success": True, "models": active_models, "default": "llama-3.3-70b-versatile"}
            else:
                return {"success": False, "models": [
                    {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B"},
                    {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B"}
                ]}
    except Exception:
        return {"success": False, "models": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B"},
            {"id": "openai/gpt-oss-120b", "name": "GPT OSS 120B"}
        ]}

# ========== SERVE FRONTEND ==========
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
