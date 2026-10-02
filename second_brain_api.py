"""HTTP API for the VektorFlow Second Brain and Termux relay."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from second_brain import run_second_brain
from postgres_connection import connect as connect_postgres

router = APIRouter(prefix="/api/second-brain", tags=["second-brain"])
RELAY_TOKEN = os.getenv("TERMUX_RELAY_TOKEN", "").strip()

class SecondBrainRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_history: Optional[list[dict[str, Any]]] = None

class RelayHeartbeat(BaseModel):
    relay_id: str = Field(min_length=1, max_length=128)
    hostname: str = Field(default="", max_length=255)
    version: str = Field(default="1", max_length=64)
    status: str = Field(default="online", max_length=32)
    executors: list[str] = Field(default_factory=list)

class RelayJobUpdate(BaseModel):
    job_id: str = Field(min_length=1, max_length=128)
    status: str = Field(pattern="^(running|completed|failed|cancelled)$")
    stdout: str = Field(default="", max_length=50000)
    stderr: str = Field(default="", max_length=20000)
    exit_code: Optional[int] = None
    result: Optional[dict[str, Any]] = None

def _authorized(token: Optional[str]) -> bool:
    return bool(RELAY_TOKEN) and token == RELAY_TOKEN

def _connect():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required")
    return connect_postgres(dsn)

@router.post("/chat")
async def second_brain_chat(request: SecondBrainRequest):
    result = await run_second_brain(request.message, request.conversation_history)
    return {"status": "success", **result, "timestamp": datetime.now(timezone.utc).isoformat()}

@router.get("/status")
async def second_brain_status():
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT relay_id, hostname, status, executors, last_seen_at, version
                   FROM public.termux_relays ORDER BY last_seen_at DESC LIMIT 1"""
            )
            row = cur.fetchone()
            relay = None
            if row:
                cols = [d.name for d in cur.description]
                relay = dict(zip(cols, row))
            cur.execute(
                """SELECT status, count(*) AS count FROM public.termux_jobs
                   GROUP BY status ORDER BY status"""
            )
            jobs = [{"status": r[0], "count": r[1]} for r in cur.fetchall()]
    return {"status": "success", "relay": relay, "jobs": jobs}

@router.post("/relay/heartbeat")
async def relay_heartbeat(payload: RelayHeartbeat, x_termux_relay_token: Optional[str] = Header(None)):
    if not _authorized(x_termux_relay_token):
        raise HTTPException(status_code=401, detail="Invalid relay token")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO public.termux_relays
                   (relay_id, hostname, status, executors, last_seen_at, version)
                   VALUES (%s,%s,%s,%s,now(),%s)
                   ON CONFLICT (relay_id) DO UPDATE SET
                     hostname=EXCLUDED.hostname, status=EXCLUDED.status,
                     executors=EXCLUDED.executors, last_seen_at=now(),
                     version=EXCLUDED.version""",
                (payload.relay_id, payload.hostname, payload.status, payload.executors, payload.version),
            )
    return {"status": "ok"}

@router.get("/relay/jobs/next")
async def relay_next_job(x_termux_relay_token: Optional[str] = Header(None)):
    if not _authorized(x_termux_relay_token):
        raise HTTPException(status_code=401, detail="Invalid relay token")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, target, action, instruction, working_dir, timeout_seconds,
                          approval_required
                   FROM public.termux_jobs
                   WHERE status='queued' AND (approval_required=false OR approved_at IS NOT NULL)
                   ORDER BY created_at ASC LIMIT 1
                   FOR UPDATE SKIP LOCKED"""
            )
            row = cur.fetchone()
            if not row:
                return {"job": None}
            cols = [d.name for d in cur.description]
            job = dict(zip(cols, row))
            cur.execute(
                "UPDATE public.termux_jobs SET status='running', started_at=now() WHERE id=%s",
                (job["id"],),
            )
    return {"job": job}

@router.post("/relay/jobs/result")
async def relay_job_result(payload: RelayJobUpdate, x_termux_relay_token: Optional[str] = Header(None)):
    if not _authorized(x_termux_relay_token):
        raise HTTPException(status_code=401, detail="Invalid relay token")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE public.termux_jobs
                   SET status=%s, stdout=%s, stderr=%s, exit_code=%s,
                       result=%s::jsonb, completed_at=CASE
                         WHEN %s IN ('completed','failed','cancelled') THEN now()
                         ELSE completed_at END
                   WHERE id=%s""",
                (
                    payload.status, payload.stdout, payload.stderr, payload.exit_code,
                    __import__("json").dumps(payload.result or {}),
                    payload.status, payload.job_id,
                ),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "ok", "job_id": payload.job_id}

@router.post("/relay/jobs/{job_id}/approve")
async def approve_job(job_id: str):
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE public.termux_jobs SET approved_at=now() WHERE id=%s AND status='queued'",
                (job_id,),
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Queued job not found")
    return {"status": "approved", "job_id": job_id}
