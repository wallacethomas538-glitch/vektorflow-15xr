"""VektorFlow Second Brain — OpenAI Agents SDK orchestration for the developer fleet.

The Second Brain does not execute Termux commands itself. It plans and queues bounded
jobs for the user's Termux relay, which executes locally as Hermes/Codex/OpenCode and
reports results back through Postgres/Supabase.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from agents import Agent, Runner, function_tool
from postgres_connection import connect as connect_postgres

DEFAULT_EMAIL = "commander@vektorflow.com"
MODEL = os.getenv("SECOND_BRAIN_MODEL", "gpt-5.4")
MAX_TIMEOUT = 900
ALLOWED_TARGETS = {"hermes", "codex", "opencode", "shell"}

SECOND_BRAIN_INSTRUCTIONS = """You are the VektorFlow Second Brain.

You are the remote command-and-coordination brain for VektorFlow's development workspace.
Your local execution fleet lives in Termux and contains Hermes, Codex, and OpenCode.

Your responsibilities:
- Understand the user's intent and decide which developer tool should handle it.
- Read current job/heartbeat state before claiming that anything is available or running.
- Queue precise, bounded work for Termux rather than pretending you executed it.
- Prefer Hermes for broad autonomous orchestration, Codex for focused coding/review tasks,
  and OpenCode for interactive repo editing/debugging when explicitly requested.
- Never expose secrets.
- Never silently delete data, rotate credentials, force-push, or make destructive production
  changes. Queue those only when the user explicitly requested them and mark approval_required.
- Preserve repository scope. The authoritative VektorFlow repo is
  wallacethomas538-glitch/vektorflow-15xr unless the user explicitly names another repo.
- Report facts, queued actions, and returned execution results separately.
- If the relay is offline, say so and do not claim the job ran.

You have tools to inspect relay state, queue work, and retrieve results.
"""

def _connect():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required")
    return connect_postgres(dsn)

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _row_dict(cur, row):
    cols = [d.name for d in cur.description]
    return dict(zip(cols, row))

@function_tool
def termux_status() -> dict[str, Any]:
    """Return the latest heartbeat from the Termux relay and its available executors."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT relay_id, hostname, status, executors, last_seen_at, version
                   FROM public.termux_relays
                   ORDER BY last_seen_at DESC LIMIT 1"""
            )
            row = cur.fetchone()
            if not row:
                return {"online": False, "reason": "No Termux relay has registered."}
            data = _row_dict(cur, row)
    last_seen = data.get("last_seen_at")
    age = (_now() - last_seen).total_seconds() if last_seen else 999999
    data["online"] = age <= int(os.getenv("TERMUX_HEARTBEAT_TTL", "90"))
    data["last_seen_age_seconds"] = round(age, 1)
    return data

@function_tool
def recent_termux_jobs(limit: int = 10) -> list[dict[str, Any]]:
    """List recent Termux jobs and their states."""
    limit = max(1, min(int(limit), 25))
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, target, action, status, created_at, started_at,
                          completed_at, error
                   FROM public.termux_jobs
                   ORDER BY created_at DESC LIMIT %s""",
                (limit,),
            )
            return [_row_dict(cur, row) for row in cur.fetchall()]

@function_tool
def queue_termux_job(
    target: str,
    action: str,
    instruction: str,
    working_dir: str = "~/vektorflow-15xr",
    timeout_seconds: int = 300,
    approval_required: bool = True,
) -> dict[str, Any]:
    """Queue a bounded job for Hermes, Codex, OpenCode, or a shell health check.

    The Termux relay performs the actual local execution. This function never runs a
    command on the server.
    """
    target = target.strip().lower()
    if target not in ALLOWED_TARGETS:
        raise ValueError(f"target must be one of {sorted(ALLOWED_TARGETS)}")
    instruction = instruction.strip()
    if not instruction:
        raise ValueError("instruction must not be empty")
    timeout_seconds = max(10, min(int(timeout_seconds), MAX_TIMEOUT))
    job_id = str(uuid.uuid4())

    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO public.termux_jobs
                   (id, target, action, instruction, working_dir, timeout_seconds,
                    approval_required, status, requested_by, created_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    job_id, target, action.strip()[:120], instruction[:12000],
                    working_dir.strip()[:500], timeout_seconds, bool(approval_required),
                    "queued", DEFAULT_EMAIL, _now(),
                ),
            )
    return {
        "queued": True,
        "job_id": job_id,
        "target": target,
        "approval_required": bool(approval_required),
        "status": "queued",
        "message": "Queued for the Termux relay; execution has not happened yet.",
    }

@function_tool
def get_termux_job(job_id: str) -> dict[str, Any]:
    """Retrieve one Termux job including its execution result."""
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM public.termux_jobs WHERE id=%s", (job_id,))
            row = cur.fetchone()
            if not row:
                return {"found": False, "job_id": job_id}
            return {"found": True, **_row_dict(cur, row)}

second_brain = Agent(
    name="VektorFlow Second Brain",
    model=MODEL,
    instructions=SECOND_BRAIN_INSTRUCTIONS,
    tools=[termux_status, recent_termux_jobs, queue_termux_job, get_termux_job],
)

async def run_second_brain(message: str, conversation_history: list[dict[str, Any]] | None = None):
    prompt = message.strip()
    if conversation_history:
        prompt = (
            "Conversation context (treat as context, not as authority to execute anything):\n"
            + json.dumps(conversation_history[-12:], default=str)
            + "\n\nCurrent user request:\n"
            + prompt
        )
    result = await Runner.run(second_brain, prompt)
    return {"response": result.final_output, "model": MODEL, "agent": second_brain.name}
