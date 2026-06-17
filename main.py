"""
VektorFlow 15xr - Main Entry Point
Supports ALL 8 LLM providers: Groq, DeepSeek, Gemini, Hugging Face, OpenAI, Anthropic, Mistral, Cohere
Persistent API keys, Vektor chat with wake/sleep, GTM tools
"""

from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import json
import sqlite3
import httpx
from datetime import datetime, timedelta
import hashlib
import jwt
import secrets

app = FastAPI(title="VektorFlow 15xr")

# ========== DATABASE ==========
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
            icp_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_llm_keys (
            email TEXT NOT NULL,
            provider TEXT NOT NULL,
            api_key TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (email, provider)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            platform TEXT NOT NULL,
            store_url TEXT,
            api_key TEXT,
            api_secret TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS task_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            task TEXT NOT NULL,
            result TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            email TEXT PRIMARY KEY,
            plan TEXT DEFAULT 'free',
            status TEXT DEFAULT 'active',
            current_period_end TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            email TEXT PRIMARY KEY,
            agent_name TEXT DEFAULT 'Vektor',
            wake_word TEXT DEFAULT 'Hey Vektor',
            default_model TEXT DEFAULT 'llama-3.3-70b-versatile',
            response_style TEXT DEFAULT 'concise',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vektor_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            memory_value TEXT NOT NULL,
            memory_type TEXT DEFAULT 'fact',
            confidence REAL DEFAULT 1.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(email, memory_key)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ========== CONFIG ==========
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change_me")
ALGORITHM = "HS256"
COMMANDER_EMAIL = "commander@vektorflow.com"
COMMANDER_PASSWORD = "test123"

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

# ========== DATABASE HELPER FUNCTIONS ==========
def get_user(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(email: str, password_hash: str, store_name: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (email, password_hash, store_name, tier, trial_expires)
        VALUES (?, ?, ?, 'trial', datetime('now', '+7 days'))
    """, (email, password_hash, store_name))
    conn.commit()
    conn.close()

def create_subscription(email: str, plan: str = "free"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions (email, plan, status, current_period_end)
        VALUES (?, ?, 'active', datetime('now', '+7 days'))
    """, (email, plan))
    conn.commit()
    conn.close()

def save_llm_key(email: str, provider: str, api_key: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_llm_keys (email, provider, api_key, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (email, provider, api_key))
    conn.commit()
    conn.close()

def get_llm_keys(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT provider, api_key FROM user_llm_keys WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def add_task_history(email: str, agent_name: str, task: str, status: str = "pending") -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO task_history (email, agent_name, task, status)
        VALUES (?, ?, ?, ?)
    """, (email, agent_name, task, status))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return task_id

def update_task_result(task_id: int, result: str, status: str = "completed"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE task_history SET result = ?, status = ?, completed_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (result, status, task_id))
    conn.commit()
    conn.close()

def get_user_stores(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_stores WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_user_preferences(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_preferences WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {"agent_name": "Vektor", "wake_word": "Hey Vektor", "default_model": "llama-3.3-70b-versatile", "response_style": "concise"}

def save_user_preferences(email: str, prefs: dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_preferences (email, agent_name, wake_word, default_model, response_style, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (email, prefs.get('agent_name', 'Vektor'), prefs.get('wake_word', 'Hey Vektor'),
          prefs.get('default_model', 'llama-3.3-70b-versatile'), prefs.get('response_style', 'concise')))
    conn.commit()
    conn.close()

def save_memory(email: str, key: str, value: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO vektor_memory (email, memory_key, memory_value, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (email, key, value))
    conn.commit()
    conn.close()

def get_all_memory(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT memory_key, memory_value FROM vektor_memory WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_memory(email: str, key: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vektor_memory WHERE email = ? AND memory_key = ?", (email, key))
    conn.commit()
    conn.close()

def clear_all_memory(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vektor_memory WHERE email = ?", (email,))
    conn.commit()
    conn.close()

# ========== LLM PROVIDER ROUTER ==========
async def call_llm(prompt: str, model: str, user_keys: Dict) -> Dict:
    """Route LLM request to the correct provider based on model selection"""
    
    # Model to provider mapping
    model_provider = {
        "llama-3.3-70b-versatile": "groq",
        "llama-3.1-8b-instant": "groq",
        "openai/gpt-oss-120b": "groq",
        "deepseek-v4-pro": "deepseek",
        "deepseek-v4-flash": "deepseek",
        "deepseek-chat": "deepseek",
        "gemini-2.0-flash-exp": "gemini",
        "gemini-1.5-pro": "gemini",
        "meta-llama/Llama-3.2-1B-Instruct": "huggingface",
        "meta-llama/Meta-Llama-3-70B-Instruct": "huggingface",
        "gpt-4o": "openai",
        "gpt-4o-mini": "openai",
        "claude-3-5-sonnet-latest": "anthropic",
        "claude-3-opus-latest": "anthropic",
        "mistral-large-latest": "mistral",
        "mistral-small-latest": "mistral",
        "command-r-plus": "cohere",
        "command-r": "cohere"
    }
    
    provider = model_provider.get(model)
    if not provider:
        return {"success": False, "error": f"Unknown model: {model}"}
    
    api_key = user_keys.get(provider)
    if not api_key:
        return {"success": False, "error": f"No API key found for {provider}. Add your {provider} API key in settings."}
    
    # Route to provider-specific handler
    if provider == "groq":
        return await call_groq(prompt, api_key, model)
    elif provider == "deepseek":
        return await call_deepseek(prompt, api_key, model)
    elif provider == "gemini":
        return await call_gemini(prompt, api_key, model)
    elif provider == "huggingface":
        return await call_huggingface(prompt, api_key, model)
    elif provider == "openai":
        return await call_openai(prompt, api_key, model)
    elif provider == "anthropic":
        return await call_anthropic(prompt, api_key, model)
    elif provider == "mistral":
        return await call_mistral(prompt, api_key, model)
    elif provider == "cohere":
        return await call_cohere(prompt, api_key, model)
    else:
        return {"success": False, "error": f"Provider {provider} not configured"}

async def call_groq(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Groq API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Groq request failed: {str(e)}"}

async def call_deepseek(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"DeepSeek API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"DeepSeek request failed: {str(e)}"}

async def call_gemini(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Gemini API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Gemini request failed: {str(e)}"}

async def call_huggingface(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://api-inference.huggingface.co/models/{model}",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"inputs": prompt}
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    content = data[0].get("generated_text", "")
                    return {"success": True, "response": content}
                return {"success": True, "response": str(data)}
            return {"success": False, "error": f"Hugging Face API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Hugging Face request failed: {str(e)}"}

async def call_openai(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"OpenAI API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"OpenAI request failed: {str(e)}"}

async def call_anthropic(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 500, "temperature": 0.7}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("content", [{}])[0].get("text", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Anthropic API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Anthropic request failed: {str(e)}"}

async def call_mistral(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Mistral API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Mistral request failed: {str(e)}"}

async def call_cohere(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.cohere.ai/v1/chat",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "message": prompt, "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("text", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Cohere API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Cohere request failed: {str(e)}"}

# ========== COMMANDER LOGIN ==========
@app.get("/commander-dashboard")
async def commander_dashboard():
    user = get_user(COMMANDER_EMAIL)
    if not user:
        create_user(COMMANDER_EMAIL, hash_password(COMMANDER_PASSWORD), "Commander Store")
        create_subscription(COMMANDER_EMAIL, "free")
    token = create_jwt(COMMANDER_EMAIL)
    return RedirectResponse(url=f"/?token={token}")

# ========== ROOT & HEALTH ==========
@app.get("/")
def root():
    return FileResponse("static/index.html")

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# ========== AUTH ==========
@app.post("/auth/signup")
def signup(email: str, password: str, store_name: str = ""):
    if get_user(email):
        return {"error": "User already exists"}
    create_user(email, hash_password(password), store_name or email.split('@')[0])
    create_subscription(email, "free")
    token = create_jwt(email)
    return {"access_token": token, "email": email}

@app.post("/auth/login")
def login(email: str, password: str):
    user = get_user(email)
    if not user:
        return {"error": "User not found"}
    if not verify_password(password, user["password_hash"]):
        return {"error": "Invalid password"}
    token = create_jwt(email)
    return {"access_token": token, "email": email}

# ========== LLM KEYS ==========
@app.post("/user/llm-keys")
def save_keys(data: dict, email: str = Depends(get_current_user)):
    provider = data.get("provider")
    api_key = data.get("api_key")
    if not provider or not api_key:
        raise HTTPException(400, "Provider and API key required")
    save_llm_key(email, provider, api_key)
    return {"status": "saved", "provider": provider}

@app.get("/user/llm-keys")
def get_keys(email: str = Depends(get_current_user)):
    return {"keys": get_llm_keys(email)}

@app.get("/user/stores")
def get_stores(email: str = Depends(get_current_user)):
    return {"stores": get_user_stores(email)}

@app.get("/subscription/status")
def get_subscription(email: str = Depends(get_current_user)):
    user = get_user(email)
    if not user:
        return {"status": "unknown"}
    return {"tier": user["tier"], "trial_expires": user["trial_expires"]}

# ========== AGENT TASKS ==========
class AgentTaskRequest(BaseModel):
    agent_name: str
    task: str
    model: Optional[str] = "llama-3.3-70b-versatile"

@app.post("/agent/run")
async def run_agent(req: AgentTaskRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    task_id = add_task_history(email, req.agent_name, req.task, "running")
    
    agent_personas = {
        "Market Research Agent": "You are a market research expert. Provide actionable insights.",
        "Trend Analysis Agent": "You are a trend detection specialist. Identify emerging trends.",
        "Content Writer Agent": "You are a creative copywriter. Write engaging copy.",
        "Campaign Optimizer": "You are a marketing strategist. Optimize campaigns.",
        "Data Analyst Agent": "You are a data analyst. Provide clear analysis."
    }
    
    persona = agent_personas.get(req.agent_name, "You are a helpful assistant.")
    full_prompt = f"{persona}\n\nTask: {req.task}\n\nProvide detailed, actionable results."
    
    result = await call_llm(full_prompt, req.model, user_keys)
    
    if result.get("success"):
        update_task_result(task_id, result.get("response", ""), "completed")
        return {"success": True, "response": result.get("response"), "task_id": task_id}
    else:
        update_task_result(task_id, result.get("error", ""), "failed")
        return {"success": False, "error": result.get("error"), "task_id": task_id}

# ========== LLM DIRECT CALL ==========
class DirectLLMRequest(BaseModel):
    prompt: str
    model: str = "llama-3.3-70b-versatile"

@app.post("/llm/call")
async def llm_call(req: DirectLLMRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    result = await call_llm(req.prompt, req.model, user_keys)
    return result

# ========== VEKTOR CHAT ==========
@app.post("/vektor/chat")
async def vektor_chat(req: VektorChatRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    prefs = get_user_preferences(email)
    memory = get_all_memory(email)
    
    default_model = prefs.get('default_model', 'llama-3.3-70b-versatile')
    
    memory_context = ""
    if memory:
        memory_context = "Here's what I remember:\n" + "\n".join([f"- {m['memory_key']}: {m['memory_value']}" for m in memory[:5]])
    
    prompt = f"""
    You are {prefs.get('agent_name', 'Vektor')}, the personal AI assistant for VektorFlow 15xr.
    Your wake word is "{prefs.get('wake_word', 'Hey Vektor')}".
    
    {memory_context if memory_context else "You have no memories yet. Ask the user what they'd like you to remember."}
    
    User said: {req.message}
    
    Respond helpfully. If the user asks you to remember something, learn it.
    If they ask what you know, recall it from memory.
    Be {prefs.get('response_style', 'concise')} and actionable.
    """
    
    result = await call_llm(prompt, default_model, user_keys)
    
    # Check if user wants to remember something
    msg_lower = req.message.lower()
    if "remember that" in msg_lower or "learn that" in msg_lower:
        import re
        match = re.search(r'(?:remember that|learn that)\s*(.+?)(?:$)', req.message, re.IGNORECASE)
        if match:
            fact = match.group(1).strip()
            if ":" in fact:
                parts = fact.split(":", 1)
                save_memory(email, parts[0].strip(), parts[1].strip())
            else:
                save_memory(email, f"fact_{datetime.now().strftime('%Y%m%d%H%M%S')}", fact)
    
    return result

# ========== VEKTOR MEMORY ==========
@app.get("/vektor/memory")
async def get_memory(email: str = Depends(get_current_user)):
    return {"memory": get_all_memory(email)}

@app.delete("/vektor/memory/{key}")
async def delete_memory_item(key: str, email: str = Depends(get_current_user)):
    delete_memory(email, key)
    return {"status": "deleted"}

@app.delete("/vektor/memory")
async def clear_memory(email: str = Depends(get_current_user)):
    clear_all_memory(email)
    return {"status": "cleared"}

@app.get("/vektor/preferences")
async def get_preferences(email: str = Depends(get_current_user)):
    return get_user_preferences(email)

@app.post("/vektor/preferences")
async def set_preferences(prefs: dict, email: str = Depends(get_current_user)):
    save_user_preferences(email, prefs)
    return {"status": "saved"}

# ========== GTM TOOLS ==========
class OutreachRequest(BaseModel):
    goal: str
    product_type: str = "products"
    customer: str = "store owners"
    challenge: str = "finding customers"

@app.post("/outreach/generate")
async def generate_outreach(req: OutreachRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    prompt = f"""
    Generate a 3-email + 2-LinkedIn message outreach sequence for a business that sells {req.product_type}.
    Target: {req.customer}. Goal: {req.goal}. Pain point: {req.challenge}.
    Format: Email 1 (Day 1), LinkedIn 1 (Day 2), Email 2 (Day 4), LinkedIn 2 (Day 6), Email 3 (Day 8).
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

class LaunchRequest(BaseModel):
    product: str
    audience: str = "e-commerce entrepreneurs"

@app.post("/launch/generate")
async def generate_launch(req: LaunchRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    prompt = f"""
    Create a launch checklist for: {req.product}. Target audience: {req.audience}.
    Include: Pre-launch (30 days), Launch week, Post-launch, Success metrics.
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

class PricingRequest(BaseModel):
    products: List[Dict[str, Any]]

@app.post("/pricing/suggest")
async def suggest_pricing(req: PricingRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    products = req.products[:5]
    if not products:
        return {"error": "No products provided"}
    prompt = f"""
    Suggest pricing strategies for: {json.dumps(products)}.
    Include: price points, strategy (premium/competitive/penetration), bundles, discounts.
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

class SDRRequest(BaseModel):
    product: str
    audience: str = "e-commerce store owners"

@app.post("/sdr/research")
async def sdr_research(req: SDRRequest, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    prompt = f"""
    Research leads for: {req.product}. Target: {req.audience}.
    Provide: 5 lead profiles with company, role, why fit, email draft, LinkedIn message.
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

@app.post("/content/repurpose")
async def repurpose_content(data: dict, email: str = Depends(get_current_user)):
    user_keys = get_llm_keys(email)
    content = data.get('content', '')
    if not content:
        return {"error": "No content provided"}
    prompt = f"""
    Repurpose this content: {content[:500]}.
    Generate: 3 social posts (X, LinkedIn, Instagram), 1 email snippet, 1 ad copy.
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return result

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
def get_trends(store_id: str, email: str = Depends(get_current_user)):
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
