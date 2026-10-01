"""Durable runtime bridge for VektorFlow agent events and runs.

Uses the Supabase Postgres connection in DATABASE_URL when configured.
The shared Postgres helper prefers Supavisor's IPv4 session pooler on Render.
"""

import json
import os
from typing import Any, Dict, Optional

from postgres_connection import connect as connect_postgres


def _dsn() -> Optional[str]:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        return None
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    return dsn


def _connect():
    dsn = _dsn()
    if not dsn:
        return None
    try:
        return connect_postgres(dsn, timeout=5)
    except Exception:
        return None


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def persist_event(event: Dict[str, Any]) -> None:
    conn = _connect()
    if conn is None:
        return
    try:
        data = event.get("data") or {}
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.agent_events
                    (event_type, source, run_id, task_id, source_agent, target_agent, data, delivery_status)
                values (%s,%s,%s,%s,%s,%s,%s::jsonb,'published')
                """,
                (
                    event.get("type", "unknown"),
                    event.get("source", "system"),
                    data.get("run_id"),
                    data.get("task_id"),
                    data.get("source_agent") or data.get("agent"),
                    data.get("target_agent"),
                    _json(data),
                ),
            )

            event_type = event.get("type", "")
            run_id = data.get("run_id")
            if run_id and event_type == "agent.run.started":
                cur.execute(
                    """
                    insert into public.agent_runs
                        (id, task_id, email, agent_name, goal, status, started_at)
                    values (%s,%s,%s,%s,%s,'running',now())
                    on conflict (id) do update
                    set status='running', started_at=coalesce(public.agent_runs.started_at, now())
                    """,
                    (
                        run_id,
                        data.get("task_id"),
                        data.get("email"),
                        data.get("agent") or data.get("source_agent"),
                        data.get("instruction") or data.get("goal") or "",
                    ),
                )
            elif run_id and event_type in {"agent.run.completed", "agent.run.failed"}:
                status = "completed" if event_type.endswith("completed") else "failed"
                cur.execute(
                    """
                    update public.agent_runs
                    set status=%s, result=case when %s='completed' then %s::jsonb else result end,
                        error=%s, completed_at=now()
                    where id=%s
                    """,
                    (
                        status,
                        status,
                        _json(data.get("result")),
                        data.get("error"),
                        run_id,
                    ),
                )
            elif run_id and event_type == "agent.message.created":
                cur.execute(
                    """
                    insert into public.agent_messages
                        (run_id, task_id, source_agent, target_agent, message_type, payload)
                    values (%s,%s,%s,%s,%s,%s::jsonb)
                    """,
                    (
                        run_id,
                        data.get("task_id"),
                        data.get("source_agent") or data.get("agent") or event.get("source"),
                        data.get("target_agent"),
                        data.get("message_type", "handoff"),
                        _json(data.get("payload") or data),
                    ),
                )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass
