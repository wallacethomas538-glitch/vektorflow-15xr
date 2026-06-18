"""
VektorFlow 15xr - Main Entry Point
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
from database import get_db, init_db, get_user, create_user, get_user_stores
from database import create_subscription, get_subscription, save_llm_key, get_llm_keys
from database import add_task_history, update_task_result, get_user_preferences, save_user_preferences
from database import save_memory, get_all_memory, delete_memory, clear_all_memory
init_db()

# ========== CONFIG ==========
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change_me")
ALGORITHM = "HS256"
COMMANDER_EMAIL = "commander@vektorflow.com"
COMMANDER_PASSWORD = "test123"
COQUI_TTS_URL = os.environ.get("COQUI_TTS_URL", "https://coqui-tts.onrender.com")
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")
WHISPER_URL = os.environ.get("WHISPER_URL", "https://whisper.onrender.com")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "https://ollama.onrender.com")

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

# ========== LLM HANDLER ==========
from llm_handler import call_llm

# ========== WHISPER HANDLER ==========
from whisper_handler import transcribe_audio, transcribe_url

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
        if N8N_WEBHOOK_URL:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    await client.post(N8N_WEBHOOK_URL, json={
                        "task_id": task_id,
                        "agent": req.agent_name,
                        "task": req.task,
                        "result": result.get("response", "")
                    })
            except:
                pass
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

# ========== WHISPER TRANSCRIPTION ==========
class WhisperRequest(BaseModel):
    audio_base64: str

class WhisperUrlRequest(BaseModel):
    audio_url: str

@app.post("/whisper/transcribe")
async def whisper_transcribe(req: WhisperRequest, email: str = Depends(get_current_user)):
    result = await transcribe_audio(req.audio_base64)
    return result

@app.post("/whisper/transcribe-url")
async def whisper_transcribe_url(req: WhisperUrlRequest, email: str = Depends(get_current_user)):
    result = await transcribe_url(req.audio_url)
    return result

# ========== VEKTOR CHAT ==========
class VektorChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict]] = []

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

# ========== N8N WEBHOOK ENDPOINT ==========
class N8NTriggerRequest(BaseModel):
    agent_name: str
    task: str
    schedule: Optional[str] = "once"

@app.post("/n8n/trigger")
async def trigger_n8n_workflow(req: N8NTriggerRequest, email: str = Depends(get_current_user)):
    if not N8N_WEBHOOK_URL:
        return {"error": "n8n webhook not configured"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(N8N_WEBHOOK_URL, json={
                "email": email,
                "agent_name": req.agent_name,
                "task": req.task,
                "schedule": req.schedule,
                "timestamp": datetime.now().isoformat()
            })
            return {"status": "triggered", "n8n_response": response.status_code}
    except Exception as e:
        return {"error": f"Failed to trigger n8n: {str(e)}"}

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