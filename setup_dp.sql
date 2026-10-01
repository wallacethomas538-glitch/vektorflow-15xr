-- VektorFlow 15xr Postgres runtime memory foundation.
-- The live Supabase project is migrated by the memory_search_foundation migration.
-- This file documents the schema for fresh environments.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.memory_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_email text NOT NULL,
    title text NOT NULL,
    content text NOT NULL,
    source_url text,
    source_type text NOT NULL DEFAULT 'manual',
    source_id text,
    source_agent text,
    source_published_at timestamptz,
    source_fetched_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_email, source_url)
);

CREATE TABLE IF NOT EXISTS public.memory_chunks (
    id bigserial PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES public.memory_documents(id) ON DELETE CASCADE,
    tenant_email text NOT NULL,
    chunk_index integer NOT NULL,
    content text NOT NULL,
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    embedding vector(768),
    source_url text,
    source_type text NOT NULL DEFAULT 'manual',
    source_agent text,
    source_published_at timestamptz,
    source_fetched_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_memory_documents_tenant ON public.memory_documents(tenant_email);
CREATE INDEX IF NOT EXISTS idx_memory_documents_fetched ON public.memory_documents(source_fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_chunks_tenant ON public.memory_chunks(tenant_email);
CREATE INDEX IF NOT EXISTS idx_memory_chunks_tsv ON public.memory_chunks USING gin(content_tsv);
CREATE INDEX IF NOT EXISTS idx_memory_chunks_embedding_hnsw
    ON public.memory_chunks USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

-- Existing semantic_memory remains for compatibility with older consumers.
-- New runtime memory writes use memory_documents + memory_chunks.
