"""
VektorFlow 15xr - Database Layer
"""

import os
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

DB_PATH = "vektorflow.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
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
            icp_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # LLM keys table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_llm_keys (
            email TEXT NOT NULL,
            provider TEXT NOT NULL,
            api_key TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (email, provider)
        )
    """)

    # User stores table
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

    # Task history table
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

    # Subscriptions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            email TEXT PRIMARY KEY,
            plan TEXT DEFAULT 'free',
            status TEXT DEFAULT 'active',
            current_period_end TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # User preferences table
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

    # Vektor memory table
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

    # Conversations table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            user_message TEXT NOT NULL,
            ai_response TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

init_db()

# ========== USER FUNCTIONS ==========
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

def connect_store(email: str, platform: str, store_url: str):
    """Alias for adding a store"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_stores (email, platform, store_url)
        VALUES (?, ?, ?)
    """, (email, platform, store_url))
    conn.commit()
    conn.close()
    return {"platform": platform, "store_url": store_url}

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

# ========== ICP FUNCTIONS ==========
def get_icp_data(email: str) -> Dict:
    """Get ICP (Ideal Customer Profile) data for a user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT icp_data FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0]:
        try:
            return json.loads(row[0])
        except:
            pass
    
    # Default ICP
    return {
        "customer": "E-commerce store owners",
        "product_type": "dropshipping products",
        "target_audience": "Online shoppers aged 18-45",
        "pain_points": ["Finding winning products", "SEO optimization", "Supplier management"],
        "goals": ["Increase sales", "Automate operations", "Scale business"],
        "niche": "General merchandise"
    }

def save_icp_data(email: str, icp_data: Dict) -> Dict:
    """Save ICP data for a user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET icp_data = ? WHERE email = ?
    """, (json.dumps(icp_data), email))
    conn.commit()
    conn.close()
    return icp_data

# ========== CONVERSATION FUNCTIONS ==========
def save_conversation(email: str, user_message: str, ai_response: str, conversation_id: Optional[str] = None) -> str:
    """Save a conversation between user and AI"""
    if not conversation_id:
        conversation_id = f"conv_{datetime.utcnow().timestamp()}"
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO conversations (email, conversation_id, user_message, ai_response)
        VALUES (?, ?, ?, ?)
    """, (email, conversation_id, user_message, ai_response))
    conn.commit()
    conn.close()
    return conversation_id

def get_conversations(email: str, limit: int = 10) -> List[Dict]:
    """Get conversation history for a user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT conversation_id, user_message, ai_response, created_at
        FROM conversations
        WHERE email = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (email, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ========== MEMORY FUNCTIONS ==========
def save_memory(email: str, key: str, value: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO vektor_memory (email, memory_key, memory_value, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (email, key, value))
    conn.commit()
    conn.close()

def get_memory(email: str, key: str) -> Optional[str]:
    """Get a single memory value by key"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT memory_value FROM vektor_memory WHERE email = ? AND memory_key = ?", (email, key))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def get_all_memory(email: str) -> List[Dict]:
    """Get all memories for a user (as list of dicts)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT memory_key, memory_value, memory_type, confidence FROM vektor_memory WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_memories(email: str) -> Dict:
    """Get all memories for a user (as dict) - ALIAS for compatibility"""
    memories = get_all_memory(email)
    return {m["memory_key"]: m["memory_value"] for m in memories}

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

# ========== TASK FUNCTIONS ==========
def get_tasks(email: Optional[str] = None) -> List[Dict]:
    """
    Get tasks for a user from the database.
    Returns real tasks if they exist, otherwise returns default tasks.
    """
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        if email:
            cursor.execute("""
                SELECT id, task as title, status, created_at as created_at
                FROM task_history
                WHERE email = ?
                ORDER BY created_at DESC
                LIMIT 10
            """, (email,))
        else:
            cursor.execute("""
                SELECT id, task as title, status, created_at as created_at
                FROM task_history
                ORDER BY created_at DESC
                LIMIT 10
            """)
        rows = cursor.fetchall()
        conn.close()
        
        if rows:
            return [dict(row) for row in rows]
        
    except sqlite3.OperationalError:
        conn.close()
        pass
    
    # Return default tasks if database is empty or table doesn't exist
    return [
        {"id": 1, "title": "Optimize product descriptions", "status": "in_progress"},
        {"id": 2, "title": "Generate meta tags for 15 products", "status": "pending"},
        {"id": 3, "title": "Update schema markup", "status": "completed"}
    ]

def create_task(email: str, title: str, description: str = "", priority: str = "medium") -> Dict:
    """Create a new task"""
    task_id = add_task_history(email, "user", title, "pending")
    return {"id": str(task_id), "title": title, "status": "pending"}

# ========== SUBSCRIPTION FUNCTIONS ==========
def get_subscription(email: str):
    """Safely get subscription - returns None if table doesn't exist"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subscriptions WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None

def update_subscription(email: str, stripe_subscription_id: str, plan: str, current_period_end: datetime):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE subscriptions
            SET stripe_subscription_id = ?, plan = ?, status = 'active', current_period_end = ?, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
        """, (stripe_subscription_id, plan, current_period_end.isoformat(), email))
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        pass

def cancel_subscription(email: str):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE subscriptions
            SET status = 'canceled', cancel_at_period_end = 1, updated_at = CURRENT_TIMESTAMP
            WHERE email = ?
        """, (email,))
        conn.commit()
        conn.close()
    except sqlite3.OperationalError:
        pass

def check_and_block_access(email: str):
    user = get_user(email)
    if not user:
        return False
    if user["tier"] == "trial" and user["trial_expires"]:
        trial_end = datetime.fromisoformat(user["trial_expires"])
        if datetime.now() > trial_end:
            return False
    return True

# ========== INITIALIZE DEFAULT USER ==========
def init_default_user():
    """Create default commander user if not exists"""
    user = get_user("commander@vektorflow.com")
    if not user:
        conn = get_db()
        cursor = conn.cursor()
        # Password is "vektorflow2026" (in production, this would be hashed)
        cursor.execute("""
            INSERT INTO users (email, password_hash, store_name, tier, trial_expires)
            VALUES (?, 'vektorflow2026', 'VektorFlow Store', 'premium', datetime('now', '+365 days'))
        """, ("commander@vektorflow.com",))
        conn.commit()
        conn.close()
        print("✅ Default commander user created.")
    else:
        print("✅ Default commander user already exists.")

init_default_user()

print("✅ VektorFlow 15xr Database initialized successfully.")
print("   Username: commander@vektorflow.com")
print("   Password: vektorflow2026")