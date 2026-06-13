"""
VektorFlow 15xr - Three-Tier Memory Fabric
Episodic, Semantic, and Procedural memory with pgvector
"""

import os
import json
import hashlib
import psycopg2
from pgvector.psycopg2 import register_vector
from typing import Dict, List, Any, Optional
from datetime import datetime

DATABASE_URL = os.environ.get("DATABASE_URL")

class MemoryFabric:
    def __init__(self):
        if DATABASE_URL:
            self.conn = psycopg2.connect(DATABASE_URL)
            # Enable pgvector extension
            self.cursor = self.conn.cursor()
            self.cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            self.conn.commit()
            register_vector(self.conn)
            self._init_tables()
        else:
            self.conn = None
            self.cursor = None
            self.memory_store = {}  # Fallback in-memory
    
    def _init_tables(self):
        if not self.cursor:
            return
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memory (
                id SERIAL PRIMARY KEY,
                agent_id TEXT NOT NULL,
                action TEXT NOT NULL,
                context JSONB,
                outcome TEXT,
                timestamp TIMESTAMP DEFAULT NOW()
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS shared_context (
                context_key TEXT PRIMARY KEY,
                context_value JSONB,
                source_agent TEXT,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """)
        self.conn.commit()
    
    def _embed(self, text: str, dims: int = 384) -> list:
        h = hashlib.sha256(text.encode()).digest()
        return [h[i % len(h)] / 255.0 for i in range(dims)]
    
    def store_episode(self, agent_id: str, action: str, context: Dict, outcome: str):
        if self.cursor:
            self.cursor.execute("""
                INSERT INTO episodic_memory (agent_id, action, context, outcome, timestamp)
                VALUES (%s, %s, %s, %s, %s)
            """, (agent_id, action, json.dumps(context), outcome, datetime.utcnow()))
            self.conn.commit()
        else:
            key = f"{agent_id}_{datetime.utcnow().timestamp()}"
            self.memory_store[key] = {"agent_id": agent_id, "action": action, "context": context, "outcome": outcome}
    
    def get_episodes(self, agent_id: str, limit: int = 50):
        if self.cursor:
            self.cursor.execute("""
                SELECT * FROM episodic_memory WHERE agent_id = %s
                ORDER BY timestamp DESC LIMIT %s
            """, (agent_id, limit))
            return self.cursor.fetchall()
        return []
    
    def update_shared_context(self, key: str, value: Any, source: str):
        if self.cursor:
            self.cursor.execute("""
                INSERT INTO shared_context (context_key, context_value, source_agent, last_updated)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (context_key) DO UPDATE
                SET context_value = EXCLUDED.context_value,
                    source_agent = EXCLUDED.source_agent,
                    last_updated = NOW()
            """, (key, json.dumps(value), source))
            self.conn.commit()
        else:
            self.memory_store[f"context_{key}"] = {"value": value, "source": source}
    
    def get_shared_context(self, key: str = None):
        if self.cursor:
            if key:
                self.cursor.execute("SELECT context_value FROM shared_context WHERE context_key = %s", (key,))
                row = self.cursor.fetchone()
                return json.loads(row[0]) if row else None
            else:
                self.cursor.execute("SELECT context_key, context_value FROM shared_context")
                return {row[0]: json.loads(row[1]) for row in self.cursor.fetchall()}
        return self.memory_store
    
    def get_all_shared_context(self):
        return self.get_shared_context()
    
    def close(self):
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
