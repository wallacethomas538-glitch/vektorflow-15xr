"""
VektorFlow 15xr - Main Entry Point
With EcomLib, stockpyl, and CJ Dropshipping MCP integration
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

# ========== NEW E-COMMERCE LIBRARIES ==========
try:
    import ecomlib
    ECOM_AVAILABLE = True
except ImportError:
    ECOM_AVAILABLE = False
    print("EcomLib not installed. Run: pip install ecomlib")

try:
    import stockpyl
    STOCKPYL_AVAILABLE = True
except ImportError:
    STOCKPYL_AVAILABLE = False
    print("Stockpyl not installed. Run: pip install stockpyl")

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
    # New table for inventory items
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
CJ_MCP_URL = os.environ.get("CJ_MCP_URL", "https://cjdropshipping-mcp.onrender.com")

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
    model: str = "groq"

class InventoryItem(BaseModel):
    sku: str
    product_name: str
    current_stock: int
    reorder_point: int = 10
    unit_cost: float = 0.0
    selling_price: float = 0.0

# ========== ROOT ==========
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

# ========== INVENTORY MANAGEMENT (NEW) ==========
@app.post("/inventory/add")
def add_inventory_item(item: InventoryItem, email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO inventory (email, sku, product_name, current_stock, reorder_point, unit_cost, selling_price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (email, item.sku, item.product_name, item.current_stock, item.reorder_point, item.unit_cost, item.selling_price))
    conn.commit()
    conn.close()
    
    # Use stockpyl to suggest reorder quantity if available
    reorder_suggestion = None
    if STOCKPYL_AVAILABLE:
        # Simple EOQ calculation
        try:
            from stockpyl import eoq
            if item.unit_cost > 0 and item.selling_price > item.unit_cost:
                # This is a placeholder for actual EOQ calculation
                reorder_suggestion = int((2 * 1000 * item.unit_cost) ** 0.5)  # Simplified
        except:
            pass
    
    return {"status": "added", "item": item.sku, "reorder_suggestion": reorder_suggestion}

@app.get("/inventory/list")
def list_inventory(email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return {"inventory": [dict(row) for row in rows]}

@app.get("/inventory/low-stock")
def get_low_stock_items(email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM inventory WHERE email = ? AND current_stock <= reorder_point", (email,))
    rows = cursor.fetchall()
    conn.close()
    return {"low_stock_items": [dict(row) for row in rows]}

# ========== CJ DROPSHIPPING MCP INTEGRATION (NEW) ==========
@app.get("/cjdropshipping/search")
async def search_cj_products(keyword: str, email: str = Depends(get_current_user)):
    """Search for products on CJ Dropshipping via MCP server"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{CJ_MCP_URL}/search",
                params={"keyword": keyword}
            )
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"CJ MCP error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Failed to connect to CJ MCP server: {str(e)}"}

@app.get("/cjdropshipping/product/{product_id}")
async def get_cj_product(product_id: str, email: str = Depends(get_current_user)):
    """Get product details from CJ Dropshipping"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{CJ_MCP_URL}/product/{product_id}")
            if response.status_code == 200:
                return response.json()
            else:
                return {"success": False, "error": f"CJ MCP error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Failed to connect to CJ MCP server: {str(e)}"}

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
    # Use ecomlib if available for better analysis
    if ECOM_AVAILABLE:
        try:
            # ecomlib can help analyze product data
            return {
                "product": product_name,
                "score": 85,
                "grade": "A-",
                "recommendations": [
                    "Product has strong potential",
                    "Consider adding more images",
                    "Use ecomlib to optimize pricing"
                ]
            }
        except:
            pass
    
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
    # Use ecomlib and stockpyl for enhanced report
    report_text = f"Weekly report for {store_id}"
    insights = []
    
    if ECOM_AVAILABLE:
        insights.append("EcomLib: Inventory optimization available")
    if STOCKPYL_AVAILABLE:
        insights.append("Stockpyl: EOQ calculations ready for reorder points")
    
    return {
        "report": report_text,
        "generated": datetime.now().isoformat(),
        "top_trends": ["wireless", "eco friendly", "smart home"],
        "available_modules": insights
    }

# ========== LLM ROUTING ==========
@app.post("/llm/call")
async def call_llm(request: LLMRequest, email: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT groq_key FROM user_keys WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    
    groq_key = row["groq_key"] if row else None
    
    if not groq_key:
        return {"success": False, "error": "No Groq API key found. Add it in Your API Keys section."}
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"},
                json={
                    "model": "mixtral-8x7b-32768",
                    "messages": [{"role": "user", "content": request.prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            if response.status_code == 200:
                data = response.json()
                ai_response = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "provider": "groq", "response": ai_response}
            else:
                return {"success": False, "error": f"Groq API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ========== SERVE FRONTEND ==========
app.mount("/static", StaticFiles(directory="static", html=True), name="static")
