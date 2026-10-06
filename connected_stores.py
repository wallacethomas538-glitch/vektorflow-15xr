"""Persistent OAuth store-token storage in Supabase.

Shopify OAuth access tokens live in ``public.connected_stores`` (created once
via the SQL migration in ``supabase/migrations/``). This module reuses the
existing Supabase Postgres path (``supabase_runtime._connect`` over the
``DATABASE_URL`` Supavisor pooler) — no new client library, no new env vars.

Every function degrades gracefully: if Supabase is unreachable, the
``DATABASE_URL`` is unset, or the migration has not been run yet, the function
returns ``None``/``False`` with a log line and callers fall back to the legacy
ephemeral SQLite ``user_stores`` behavior. Nothing here may raise to callers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("vektorflow.connected_stores")

try:
    from supabase_runtime import _connect as _supabase_connect
except Exception:  # pragma: no cover - defensive import
    _supabase_connect = None  # type: ignore[assignment]


def _connection():
    """Open a Supabase Postgres connection, or return None when unavailable."""
    if _supabase_connect is None:
        return None
    try:
        return _supabase_connect()
    except Exception as exc:
        logger.warning(
            "connected_stores: Supabase connect failed, falling back to SQLite: %s",
            exc,
        )
        return None


def save_store_token(email: str, platform: str, store_url: str, access_token: str) -> bool:
    """UPSERT an OAuth access token into public.connected_stores.

    Returns True on success, False when Supabase is unavailable or the
    migration has not been run (callers then use the SQLite fallback).
    """
    conn = _connection()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into public.connected_stores
                    (email, platform, store_url, access_token, updated_at)
                values (%s, %s, %s, %s, now())
                on conflict (email, platform, store_url)
                do update set access_token = excluded.access_token,
                              updated_at = now()
                """,
                (email, platform, store_url, access_token),
            )
        conn.commit()
        return True
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        logger.warning(
            "connected_stores: Supabase upsert failed (%s), falling back to SQLite",
            type(exc).__name__,
        )
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_store_token(email: str, platform: str) -> Optional[Dict[str, Any]]:
    """Fetch the newest stored OAuth token for (email, platform) from Supabase.

    Returns a dict with email/platform/store_url/access_token, or None when
    Supabase is unavailable, the migration has not been run, or no token is
    stored (callers then use the SQLite fallback).
    """
    conn = _connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select email, platform, store_url, access_token
                from public.connected_stores
                where email = %s and platform = %s
                order by updated_at desc
                limit 1
                """,
                (email, platform),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "email": row[0],
            "platform": row[1],
            "store_url": row[2],
            "access_token": row[3],
        }
    except Exception as exc:
        logger.warning(
            "connected_stores: Supabase read failed (%s), falling back to SQLite",
            type(exc).__name__,
        )
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass
