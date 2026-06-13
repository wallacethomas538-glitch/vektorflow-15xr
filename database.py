import os
import json
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()

# Initialize on import
init_db()

# Helper functions
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
        INSERT INTO users (email, password_hash, store_name, trial_expires)
        VALUES (?, ?, ?, datetime('now', '+7 days'))
    """, (email, password_hash, store_name))
    conn.commit()
    conn.close()

def save_api_keys(email: str, keys: Dict):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO user_keys (email, groq_key, gemini_key, hf_key, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, (email, keys.get('groq_api_key'), keys.get('gemini_api_key'), keys.get('hf_api_key')))
    conn.commit()
    conn.close()

def get_api_keys(email: str) -> Dict:
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_keys WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else {}
