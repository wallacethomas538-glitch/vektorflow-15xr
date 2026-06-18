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

    # Subscriptions table (ADDED)
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

    conn.commit()
    conn.close()

# Initialize the database
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

# ========== SUBSCRIPTION FUNCTIONS ==========
def get_subscription(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM subscriptions WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

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

def check_and_block_access(email: str):
    user = get_user(email)
    if not user:
        return False
    if user["tier"] == "trial" and user["trial_expires"]:
        from datetime import datetime
        trial_end = datetime.fromisoformat(user["trial_expires"])
        if trial_end < datetime.now():
            return False
    return True