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
    
    # Users
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
    
    # User stores
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
    
    # Subscriptions
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
    
    # OAuth states
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
    
    # Task history
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
    
    # Payment history
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

def extend_trial(email: str, days: int = 7):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET trial_expires = datetime('now', ?) WHERE email = ?", (f'+{days} days', email))
    conn.commit()
    conn.close()

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

def is_trial_active(email: str) -> bool:
    user = get_user(email)
    if not user:
        return False
    if user["tier"] != "trial":
        return True
    if user["trial_expires"]:
        from datetime import datetime
        trial_end = datetime.fromisoformat(user["trial_expires"])
        if trial_end < datetime.now():
            return False
    return True

def check_and_block_access(email: str) -> bool:
    """Returns True if access is allowed, False if blocked"""
    user = get_user(email)
    if not user:
        return False
    
    # Check trial expiration
    if user["tier"] == "trial" and user["trial_expires"]:
        from datetime import datetime
        trial_end = datetime.fromisoformat(user["trial_expires"])
        if trial_end < datetime.now():
            return False
    
    return True
