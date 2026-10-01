"""Render-safe Supabase Postgres connection helper.

Supabase direct database endpoints are IPv6-only by default, while Render
currently provides an IPv4-only network path. For this deployment, prefer
Supavisor's IPv4 session pooler and retain DATABASE_URL credentials.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit, quote


def _candidate_dsns(dsn: str):
    parsed = urlsplit(dsn)
    host = parsed.hostname or ""
    if not host.endswith(".supabase.co") or not host.startswith("db."):
        yield dsn
        return

    project_ref = host[3:].split(".", 1)[0]
    username = parsed.username or "postgres"
    if username == "postgres":
        pooler_user = f"postgres.{project_ref}"
    else:
        pooler_user = username if "." in username else f"{username}.{project_ref}"

    password = parsed.password
    auth = quote(pooler_user, safe="")
    if password is not None:
        auth += ":" + quote(password, safe="")
    netloc = auth + "@"

    hosts = [
        h.strip()
        for h in os.getenv(
            "SUPABASE_POOLER_HOSTS",
            "aws-1-us-east-2.pooler.supabase.com,aws-0-us-east-2.pooler.supabase.com",
        ).split(",")
        if h.strip()
    ]

    # Supavisor session mode is IPv4-compatible and uses port 5432.
    for pooler_host in hosts:
        yield urlunsplit(
            (
                parsed.scheme or "postgresql",
                netloc + pooler_host,
                "/postgres",
                parsed.query,
                parsed.fragment,
            )
        )

    # Keep the original direct connection as a final fallback.
    yield dsn


def connect(dsn: str, timeout: int = 8):
    last_error = None
    for candidate in _candidate_dsns(dsn):
        try:
            import psycopg
            return psycopg.connect(candidate, connect_timeout=timeout)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("No PostgreSQL connection candidate was available")
