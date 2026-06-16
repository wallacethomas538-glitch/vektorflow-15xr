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
    
    # User LLM keys table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_llm_keys (
            email TEXT NOT NULL,
            provider TEXT NOT NULL,
            api_key TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (email, provider),
            FOREIGN KEY (email) REFERENCES users(email)
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
            is_primary INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)
    
    # Subscriptions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            stripe_customer_id TEXT,
            stripe_subscription_id TEXT,
            plan TEXT DEFAULT 'free',
            status TEXT DEFAULT 'active',
            current_period_start TIMESTAMP,
            current_period_end TIMESTAMP,
            cancel_at_period_end INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)
    
    # OAuth states table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS oauth_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            state TEXT NOT NULL,
            platform TEXT NOT NULL,
            shop_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email) REFERENCES users(email)
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
            completed_at TIMESTAMP,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)
    
    # Payment history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            stripe_payment_id TEXT,
            amount REAL,
            currency TEXT DEFAULT 'usd',
            status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (email) REFERENCES users(email)
        )
    """)
    
    # Rate limit usage table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rate_limit_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            request_count INTEGER DEFAULT 0,
            window_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tier TEXT DEFAULT 'trial',
            UNIQUE(key, window_start)
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_db()

# ========== USER FUNCTIONS ==========
def get_user(email: str) -> Optional[Dict]:
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

def save_icp_data(email: str, icp_data: Dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET icp_data = ? WHERE email = ?", (json.dumps(icp_data), email))
    conn.commit()
    conn.close()

def get_icp_data(email: str) -> Optional[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT icp_data FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return json.loads(row[0]) if row and row[0] else None

# ========== LLM KEY FUNCTIONS ==========
def save_llm_key(email: str, provider: str, api_key: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_llm_keys (email, provider, api_key, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """, (email, provider, api_key))
    conn.commit()
    conn.close()

def get_llm_keys(email: str) -> Dict[str, str]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT provider, api_key FROM user_llm_keys WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return {row[0]: row[1] for row in rows}

def get_llm_key(email: str, provider: str) -> Optional[str]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT api_key FROM user_llm_keys WHERE email = ? AND provider = ?", (email, provider))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

# ========== STORE FUNCTIONS ==========
def add_user_store(email: str, platform: str, api_key: str, api_secret: str = "", store_url: str = "") -> int:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_stores (email, platform, store_url, api_key, api_secret)
        VALUES (?, ?, ?, ?, ?)
    """, (email, platform, store_url, api_key, api_secret))
    store_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return store_id

def get_user_stores(email: str) -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_stores WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ========== SUBSCRIPTION FUNCTIONS ==========
def get_subscription(email: str) -> Optional[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscriptions WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_subscription(email: str, plan: str = "free"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO subscriptions (email, plan, status, current_period_end)
        VALUES (?, ?, 'active', datetime('now', '+7 days'))
    """, (email, plan))
    conn.commit()
    conn.close()

def update_subscription(email: str, stripe_subscription_id: str, plan: str, current_period_end: datetime):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE subscriptions 
        SET stripe_subscription_id = ?, plan = ?, status = 'active', current_period_end = ?, updated_at = CURRENT_TIMESTAMP
        WHERE email = ?
    """, (stripe_subscription_id, plan, current_period_end.isoformat(), email))
    conn.commit()
    conn.close()

def cancel_subscription(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE subscriptions 
        SET status = 'canceled', cancel_at_period_end = 1, updated_at = CURRENT_TIMESTAMP
        WHERE email = ?
    """, (email,))
    conn.commit()
    conn.close()

def check_and_block_access(email: str) -> bool:
    user = get_user(email)
    if not user:
        return False
    if user["tier"] == "trial" and user["trial_expires"]:
        from datetime import datetime
        trial_end = datetime.fromisoformat(user["trial_expires"])
        if trial_end < datetime.now():
            return False
    return True

# ========== TASK HISTORY FUNCTIONS ==========
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

def get_task_history(email: str, limit: int = 20) -> List[Dict]:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM task_history WHERE email = ? ORDER BY created_at DESC LIMIT ?
    """, (email, limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
