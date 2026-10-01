"""Authoritative Postgres runtime memory and hybrid retrieval for VektorFlow."""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import psycopg


EMBEDDING_DIMENSIONS = 768
DEFAULT_EMAIL = "commander@vektorflow.com"


def _dsn() -> str:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required: Postgres is the authoritative VektorFlow runtime memory store.")
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


def _connect():
    return psycopg.connect(_dsn(), connect_timeout=8)


def _vector_literal(values: List[float]) -> str:
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Embedding must contain exactly {EMBEDDING_DIMENSIONS} dimensions; got {len(values)}")
    return "[" + ",".join(f"{float(v):.8g}" for v in values) + "]"


def _openai_embedding(text: str) -> Optional[List[float]]:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    response = httpx.post(
        "https://api.openai.com/v1/embeddings",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "input": text, "dimensions": EMBEDDING_DIMENSIONS},
        timeout=30,
    )
    response.raise_for_status()
    vector = response.json()["data"][0]["embedding"]
    return vector if len(vector) == EMBEDDING_DIMENSIONS else None


def _ollama_embedding(text: str) -> Optional[List[float]]:
    base = os.getenv("OLLAMA_BASE_URL")
    if not base:
        return None
    model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    base = base.rstrip("/")
    response = httpx.post(
        f"{base}/api/embed",
        json={"model": model, "input": [text]},
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    vector = (payload.get("embeddings") or [None])[0]
    return vector if isinstance(vector, list) and len(vector) == EMBEDDING_DIMENSIONS else None


def embed_text(text: str) -> Optional[List[float]]:
    """Return a real 768-dim embedding when an embedding provider is configured."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        vector = _openai_embedding(text)
        if vector:
            return vector
    except Exception:
        pass
    try:
        vector = _ollama_embedding(text)
        if vector:
            return vector
    except Exception:
        pass
    return None


def _chunk_text(text: str, size: int = 1400, overlap: int = 200) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def ingest_document(
    *,
    email: str,
    title: str,
    content: str,
    source_url: Optional[str] = None,
    source_type: str = "manual",
    source_id: Optional[str] = None,
    source_agent: Optional[str] = None,
    source_published_at: Optional[datetime] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Ingest a document into Postgres, replacing its chunks atomically."""
    email = email or DEFAULT_EMAIL
    if not title.strip() or not content.strip():
        raise ValueError("title and content are required")
    metadata = metadata or {}
    fetched_at = datetime.now(timezone.utc)

    with _connect() as conn:
        with conn.cursor() as cur:
            if source_url:
                cur.execute(
                    "SELECT id FROM public.memory_documents WHERE tenant_email=%s AND source_url=%s",
                    (email, source_url),
                )
                existing = cur.fetchone()
            else:
                existing = None

            if existing:
                document_id = existing[0]
                cur.execute(
                    """
                    UPDATE public.memory_documents
                    SET title=%s, content=%s, source_type=%s, source_id=%s,
                        source_agent=%s, source_published_at=%s, source_fetched_at=%s,
                        metadata=%s::jsonb, updated_at=now()
                    WHERE id=%s
                    """,
                    (title, content, source_type, source_id, source_agent,
                     source_published_at, fetched_at, json.dumps(metadata), document_id),
                )
                cur.execute("DELETE FROM public.memory_chunks WHERE document_id=%s", (document_id,))
            else:
                cur.execute(
                    """
                    INSERT INTO public.memory_documents
                      (tenant_email,title,content,source_url,source_type,source_id,
                       source_agent,source_published_at,source_fetched_at,metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    RETURNING id
                    """,
                    (email, title, content, source_url, source_type, source_id,
                     source_agent, source_published_at, fetched_at, json.dumps(metadata)),
                )
                document_id = cur.fetchone()[0]

            chunks = _chunk_text(content)
            embedded = 0
            for index, chunk in enumerate(chunks):
                vector = embed_text(chunk)
                if vector:
                    embedded += 1
                    cur.execute(
                        """
                        INSERT INTO public.memory_chunks
                          (document_id,tenant_email,chunk_index,content,embedding,source_url,
                           source_type,source_agent,source_published_at,source_fetched_at,metadata)
                        VALUES (%s,%s,%s,%s,%s::vector,%s,%s,%s,%s,%s,%s::jsonb)
                        """,
                        (document_id, email, index, chunk, _vector_literal(vector), source_url,
                         source_type, source_agent, source_published_at, fetched_at, json.dumps(metadata)),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO public.memory_chunks
                          (document_id,tenant_email,chunk_index,content,source_url,
                           source_type,source_agent,source_published_at,source_fetched_at,metadata)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                        """,
                        (document_id, email, index, chunk, source_url, source_type,
                         source_agent, source_published_at, fetched_at, json.dumps(metadata)),
                    )

    return {
        "document_id": str(document_id),
        "title": title,
        "chunks": len(chunks),
        "embedded_chunks": embedded,
        "embedding_provider": (
            "openai" if os.getenv("OPENAI_API_KEY") else
            "ollama" if os.getenv("OLLAMA_BASE_URL") else
            "keyword_only"
        ),
        "source": {
            "url": source_url,
            "type": source_type,
            "agent": source_agent,
            "published_at": source_published_at.isoformat() if source_published_at else None,
            "fetched_at": fetched_at.isoformat(),
        },
    }


def hybrid_search(
    *,
    email: str,
    query: str,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Keyword + semantic + freshness retrieval with source attribution."""
    query = (query or "").strip()
    if not query:
        return []

    vector = embed_text(query)
    vector_literal = _vector_literal(vector) if vector else None

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM public.hybrid_memory_search(%s,%s,%s::vector,%s)",
                (email or DEFAULT_EMAIL, query, vector_literal, max(1, min(limit, 100))),
            )
            columns = [d.name for d in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]

    now = datetime.now(timezone.utc)
    for row in rows:
        fetched = row.get("source_fetched_at")
        if fetched and fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - fetched).total_seconds() / 86400.0) if fetched else None
        row["freshness"] = {
            "fetched_at": fetched.isoformat() if fetched else None,
            "age_days": round(age_days, 2) if age_days is not None else None,
        }
        row["attribution"] = {
            "title": row.get("title"),
            "url": row.get("source_url"),
            "type": row.get("source_type"),
            "agent": row.get("source_agent"),
            "published_at": row.get("source_published_at").isoformat()
            if row.get("source_published_at") else None,
        }
    return rows


def save_memory(
    email: str,
    key: str,
    value: str,
    *,
    source_agent: str = "runtime",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    ingest_document(
        email=email,
        title=key,
        content=value,
        source_url=f"memory://{email}/{key}",
        source_type="runtime_memory",
        source_id=key,
        source_agent=source_agent,
        metadata=metadata,
    )


def get_memory(email: str, key: str) -> Optional[str]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content FROM public.memory_documents WHERE tenant_email=%s AND source_url=%s",
                (email, f"memory://{email}/{key}"),
            )
            row = cur.fetchone()
            return row[0] if row else None


def get_all_memory(email: str) -> List[Dict[str, Any]]:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_id AS memory_key, content AS memory_value,
                       metadata, source_agent, source_fetched_at
                FROM public.memory_documents
                WHERE tenant_email=%s AND source_type='runtime_memory'
                ORDER BY source_fetched_at DESC
                """,
                (email,),
            )
            columns = [d.name for d in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def delete_memory(email: str, key: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.memory_documents WHERE tenant_email=%s AND source_url=%s",
                (email, f"memory://{email}/{key}"),
            )


def clear_all_memory(email: str) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.memory_documents WHERE tenant_email=%s AND source_type='runtime_memory'",
                (email,),
            )
