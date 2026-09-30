"""Optional n8n adapter for the VektorFlow EventBus.

n8n is an external workflow/tool executor. This module does not replace the
EventBus; it forwards selected EventBus events to an n8n webhook.

Configuration:
  N8N_EVENT_WEBHOOK_URL   Production webhook URL. If unset, adapter is disabled.
  N8N_EVENT_TYPES         Comma-separated event types to forward. Empty = all.
  N8N_SHARED_SECRET       Optional HMAC-SHA256 secret.
  N8N_WEBHOOK_TIMEOUT     Request timeout seconds (default 10).
  N8N_MAX_RETRIES         Bounded retries (default 3).
  N8N_RETRY_BACKOFF       Base backoff seconds (default 1).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict

logger = logging.getLogger("vektorflow.n8n")


def _csv(name: str) -> set[str]:
    return {x.strip() for x in os.getenv(name, "").split(",") if x.strip()}


def _config() -> Dict[str, Any]:
    return {
        "url": os.getenv("N8N_EVENT_WEBHOOK_URL", "").strip(),
        "types": _csv("N8N_EVENT_TYPES"),
        "secret": os.getenv("N8N_SHARED_SECRET", ""),
        "timeout": max(1.0, float(os.getenv("N8N_WEBHOOK_TIMEOUT", "10"))),
        "retries": max(0, int(os.getenv("N8N_MAX_RETRIES", "3"))),
        "backoff": max(0.1, float(os.getenv("N8N_RETRY_BACKOFF", "1"))),
    }


def enabled_for(event_type: str) -> bool:
    cfg = _config()
    return bool(cfg["url"]) and (not cfg["types"] or event_type in cfg["types"])


def _post(url: str, body: bytes, headers: Dict[str, str], timeout: float) -> int:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return int(response.status)


def forward_event(event: Dict[str, Any]) -> bool:
    event_type = str(event.get("type", "unknown"))
    if not enabled_for(event_type):
        return True

    cfg = _config()
    payload = {
        "event_id": event.get("event_id"),
        "event_type": event_type,
        "source": event.get("source", "system"),
        "timestamp": event.get("timestamp"),
        "data": event.get("data") or {},
    }
    body = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    sent_at = str(int(time.time()))
    headers = {
        "Content-Type": "application/json",
        "X-VektorFlow-Event-Id": str(payload["event_id"] or ""),
        "X-VektorFlow-Timestamp": sent_at,
        "User-Agent": "VektorFlow-EventBus/1.0",
    }
    if cfg["secret"]:
        signing_input = sent_at.encode("utf-8") + b"." + body
        digest = hmac.new(cfg["secret"].encode("utf-8"), signing_input, hashlib.sha256).hexdigest()
        headers["X-VektorFlow-Signature"] = "sha256=" + digest

    for attempt in range(cfg["retries"] + 1):
        try:
            status = _post(cfg["url"], body, headers, cfg["timeout"])
            if 200 <= status < 300:
                return True
            if status not in (429,) and status < 500:
                logger.error("n8n rejected event %s with HTTP %s", payload["event_id"], status)
                return False
            raise RuntimeError(f"n8n HTTP {status}")
        except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as exc:
            if attempt >= cfg["retries"]:
                logger.error("n8n delivery exhausted for %s after %s attempts: %s", payload["event_id"], attempt + 1, exc)
                return False
            delay = cfg["backoff"] * (2 ** attempt)
            logger.warning("n8n delivery failed for %s; retrying in %.1fs: %s", payload["event_id"], delay, exc)
            time.sleep(delay)
    return False


async def forward_event_async(event: Dict[str, Any]) -> bool:
    return await asyncio.to_thread(forward_event, event)
