"""API endpoints for document ingestion and hybrid memory retrieval."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from runtime_memory import DEFAULT_EMAIL, get_all_memory, hybrid_search, ingest_document


router = APIRouter(prefix="/api/memory", tags=["memory"])


class DocumentIngestRequest(BaseModel):
    email: str = DEFAULT_EMAIL
    title: str
    content: str
    source_url: Optional[str] = None
    source_type: str = "manual"
    source_id: Optional[str] = None
    source_agent: Optional[str] = None
    source_published_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemorySearchRequest(BaseModel):
    email: str = DEFAULT_EMAIL
    query: str
    limit: int = Field(default=10, ge=1, le=100)


@router.post("/documents")
async def ingest(request: DocumentIngestRequest):
    try:
        return {"status": "success", **ingest_document(**request.model_dump())}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/search")
async def search(request: MemorySearchRequest):
    try:
        results = hybrid_search(email=request.email, query=request.query, limit=request.limit)
        return {
            "status": "success",
            "query": request.query,
            "retrieval": "hybrid_keyword_semantic_freshness",
            "results": results,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("")
async def list_runtime_memory(email: str = DEFAULT_EMAIL):
    try:
        return {
            "status": "success",
            "backend": "supabase_postgres",
            "authoritative": True,
            "items": get_all_memory(email),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
