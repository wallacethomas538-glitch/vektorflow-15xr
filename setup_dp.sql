-- Enable pgvector extension (for semantic memory)
CREATE EXTENSION IF NOT EXISTS vector;

-- Shared Context table (stores users, API keys, catalog references, etc.)
CREATE TABLE IF NOT EXISTS shared_context (
    context_key TEXT PRIMARY KEY,
    context_value JSONB NOT NULL,
    source_agent TEXT,
    last_updated TIMESTAMP DEFAULT NOW()
);

-- Episodic Memory table (agent history)
CREATE TABLE IF NOT EXISTS episodic_memory (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL,
    action TEXT NOT NULL,
    context JSONB,
    outcome TEXT,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Semantic Memory table (facts with vector search)
CREATE TABLE IF NOT EXISTS semantic_memory (
    id SERIAL PRIMARY KEY,
    fact_key TEXT UNIQUE NOT NULL,
    fact_value TEXT NOT NULL,
    confidence FLOAT DEFAULT 1.0,
    source_agent TEXT,
    embedding vector(384),
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Procedural Memory table (task patterns)
CREATE TABLE IF NOT EXISTS procedural_memory (
    id SERIAL PRIMARY KEY,
    task_type TEXT UNIQUE NOT NULL,
    success_pattern JSONB,
    failure_patterns JSONB,
    agent_id TEXT,
    attempt_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    success_rate FLOAT DEFAULT 0,
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_shared_context_key ON shared_context(context_key);
CREATE INDEX IF NOT EXISTS idx_episodic_agent ON episodic_memory(agent_id);
CREATE INDEX IF NOT EXISTS idx_episodic_timestamp ON episodic_memory(timestamp);
CREATE INDEX IF NOT EXISTS idx_semantic_key ON semantic_memory(fact_key);
CREATE INDEX IF NOT EXISTS idx_procedural_task ON procedural_memory(task_type);
