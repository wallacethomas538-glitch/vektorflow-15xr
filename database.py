import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

DB_PATH = "vektorflow.db"

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize all database tables"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
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
    
    # API keys table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_keys (
            email TEXT PRIMARY KEY,
            groq_key TEXT,
            gemini_key TEXT,
            hf_key TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Catalogs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalogs (
            store_id TEXT,
            email TEXT,
            products TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (store_id, email)
        )
    """)
    
    # Agent memory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Pending approvals table (human-in-the-loop)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            task TEXT NOT NULL,
            drift_score REAL,
            options TEXT,
            status TEXT DEFAULT 'pending',
            decision TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

# Initialize database on import
init_db()

# ========== USER FUNCTIONS ==========

def get_user(email: str) -> Optional[Dict]:
    """Get user by email"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_user(email: str, password_hash: str, store_name: str):
    """Create a new user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (email, password_hash, store_name, trial_expires)
        VALUES (?, ?, ?, ?)
    """, (email, password_hash, store_name, (datetime.now() + timedelta(days=7)).isoformat()))
    conn.commit()
    conn.close()

def update_user_tier(email: str, tier: str):
    """Update user's subscription tier"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tier = ? WHERE email = ?", (tier, email))
    conn.commit()
    conn.close()

# ========== API KEY FUNCTIONS ==========

def save_api_keys(email: str, keys: Dict):
    """Save user's API keys"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_keys (email, groq_key, gemini_key, hf_key, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (email, keys.get('groq_api_key'), keys.get('gemini_api_key'), keys.get('hf_api_key')))
    conn.commit()
    conn.close()

def get_api_keys(email: str) -> Dict:
    """Get user's API keys"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_keys WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}

# ========== CATALOG FUNCTIONS ==========

def save_catalog(email: str, store_id: str, products: List[Dict]):
    """Save product catalog"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO catalogs (store_id, email, products)
        VALUES (?, ?, ?)
    """, (store_id, email, json.dumps(products)))
    conn.commit()
    conn.close()

def get_catalog(email: str, store_id: str) -> Optional[List[Dict]]:
    """Get product catalog"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT products FROM catalogs WHERE store_id = ? AND email = ?", (store_id, email))
    row = cursor.fetchone()
    conn.close()
    return json.loads(row[0]) if row else None

def get_all_catalogs(email: str) -> List[Dict]:
    """Get all catalogs for a user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT store_id, products FROM catalogs WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [{"store_id": row[0], "products": json.loads(row[1])} for row in rows]

# ========== MEMORY FUNCTIONS ==========

def store_agent_memory(agent_id: str, memory_type: str, content: str):
    """Store agent memory"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO agent_memory (agent_id, memory_type, content)
        VALUES (?, ?, ?)
    """, (agent_id, memory_type, content))
    conn.commit()
    conn.close()

def get_agent_memory(agent_id: str, limit: int = 50) -> List[Dict]:
    """Get agent memory"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT memory_type, content, timestamp FROM agent_memory
        WHERE agent_id = ?
        ORDER BY timestamp DESC
        LIMIT ?
    """, (agent_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ========== APPROVAL FUNCTIONS ==========

def create_pending_approval(email: str, task: str, drift_score: float, options: List[Dict]) -> int:
    """Create a human-in-the-loop approval request"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pending_approvals (email, task, drift_score, options)
        VALUES (?, ?, ?, ?)
    """, (email, task, drift_score, json.dumps(options)))
    conn.commit()
    approval_id = cursor.lastrowid
    conn.close()
    return approval_id

def get_pending_approvals(email: str) -> List[Dict]:
    """Get all pending approvals for a user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM pending_approvals
        WHERE email = ? AND status = 'pending'
        ORDER BY created_at DESC
    """, (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def resolve_approval(approval_id: int, decision: str, selected_option: Any = None):
    """Resolve a pending approval"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE pending_approvals
        SET status = ?, decision = ?, resolved_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (decision, json.dumps(selected_option) if selected_option else None, approval_id))
    conn.commit()
    conn.close()
