# VektorFlow Runtime Memory and Retrieval

Postgres/Supabase is the authoritative runtime memory store. SQLite is retained only for legacy application tables and is no longer used by the runtime memory API.

## Memory paths

- `runtime_memory.py` — authoritative persistence, document ingestion, embeddings, and hybrid retrieval.
- `memory_fabric.py` — compatibility facade for existing agent imports; it delegates to Postgres.
- `database.py` — legacy database layer; its memory functions delegate to `runtime_memory.py`.
- `memory_api.py` — document ingestion and retrieval HTTP API.

## Document ingestion

`POST /api/memory/documents` accepts:

- tenant/email
- title and document content
- source URL/type/ID
- source agent
- published timestamp
- arbitrary metadata

Documents are chunked, persisted in `memory_documents` and `memory_chunks`, and timestamped with the fetch time. Re-ingesting the same tenant + source URL replaces its chunks atomically.

## Retrieval

`POST /api/memory/search` performs hybrid retrieval:

1. PostgreSQL full-text keyword matching through `tsvector` + GIN.
2. Semantic vector similarity through pgvector cosine distance + HNSW.
3. Freshness decay based on `source_fetched_at`.
4. A combined score returns the ranked result.
5. Every result includes source attribution: title, URL, type, agent, published time, and fetched time.

The database function is `public.hybrid_memory_search`.

## Embeddings

The runtime accepts real 768-dimensional embeddings from:

1. OpenAI `text-embedding-3-small` when `OPENAI_API_KEY` is configured.
2. Ollama `nomic-embed-text` when `OLLAMA_BASE_URL` is configured.
3. Keyword-only retrieval remains available if neither provider is reachable; no fake hash vectors are written.

Set `EMBEDDING_MODEL` to override the OpenAI embedding model and `OLLAMA_EMBEDDING_MODEL` to override the Ollama model.

## Source freshness

Each chunk stores:

- `source_published_at` — when the source says it was published.
- `source_fetched_at` — when VektorFlow ingested/re-fetched it.
- `source_url`, `source_type`, and `source_agent` — attribution.
- `metadata` — provider-specific provenance.

Freshness contributes 10% of the default combined retrieval score. Keyword relevance contributes 35%, semantic relevance 55%.

## Verification

Supabase currently has pgvector 0.8.2 installed. The memory chunk table has both a GIN full-text index and an HNSW cosine index, and the hybrid search function is installed. A cosine self-similarity check returns 1.0.

