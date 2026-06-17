"""
VektorFlow 15xr - Database Layer with ChromaDB support
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

# ========== CHROMADB SETUP ==========
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_ENABLED = True
    chroma_client = chromadb.Client(Settings(
        chroma_db_impl="duckdb+parquet",
        persist_directory="./chroma_db"
    ))
except ImportError:
    CHROMA_ENABLED = False
    chroma_client = None

def get_memory_collection(email: str):
    if not CHROMA_ENABLED or not chroma_client:
        return None
    collection_name = f"memory_{email.replace('@', '_').replace('.', '_')}"
    return chroma_client.get_or_create_collection(name=collection_name)

def save_vector_memory(email: str, key: str, value: str):
    if not CHROMA_ENABLED or not chroma_client:
        return
    collection = get_memory_collection(email)
    if collection:
        try:
            collection.add(
                documents=[value],
                metadatas=[{"key": key}],
                ids=[key]
            )
        except Exception as e:
            print(f"ChromaDB save error: {e}")

def search_vector_memory(email: str, query: str, limit: int = 5):
    if not CHROMA_ENABLED or not chroma_client:
        return []
    collection = get_memory_collection(email)
    if collection:
        try:
            results = collection.query(query_texts=[query], n_results=limit)
            return results.get('documents', []) if results else []
        except Exception as e:
            print(f"ChromaDB search error: {e}")
    return []

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
    save_vector_memory(email, key, value)

def get_all_memory(email: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT memory_key, memory_value FROM vektor_memory WHERE email = ?", (email,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def search_memory(email: str, query: str):
    vector_results = search_vector_memory(email, query)
    if vector_results:
        return vector_results
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT memory_value FROM vektor_memory 
        WHERE email = ? AND memory_value LIKE ?
        LIMIT 5
    """, (email, f'%{query}%'))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

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
