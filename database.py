"""
VektorFlow 15xr - Database Layer
Complete with user stores, LLM keys, inventory, and tasks
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # User LLM keys table (universal - any provider)
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
    
    # User stores table (CJ Dropshipping connection)
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
    
    # Products catalog
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            product_id TEXT NOT NULL,
            name TEXT NOT NULL,
            price REAL,
            description TEXT,
            category TEXT,
            tags TEXT,
            image_url TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (store_id) REFERENCES user_stores(id)
        )
    """)
    
    # Inventory tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            current_stock INTEGER DEFAULT 0,
            reorder_point INTEGER DEFAULT 5,
            reorder_quantity INTEGER DEFAULT 10,
            unit_cost REAL DEFAULT 0,
            selling_price REAL DEFAULT 0,
            last_synced TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id)
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
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_db()

# ========== USER LLM KEYS FUNCTIONS ==========
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
        INSERT INTO user_stores (email, platform, api_key, api_secret, store_url)
        VALUES (?, ?, ?, ?, ?)
    """, (email, platform, api_key, api_secret, store_url))
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

# ========== TASK HISTORY ==========
def add_task_history(email: str, agent_name: str, task: str, status: str = "pending"):
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
