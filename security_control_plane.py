"""VektorFlow security/control-plane adapters.

Borrowed concepts, not copied implementations:
- OPA: external policy-as-code decisions.
- OpenFGA: fine-grained relationship authorization.
- OpenGuardrails/Llama Guard: model/tool safety verdict boundary.
- OpenSandbox/gVisor/Firecracker: isolated execution substrate selection.
- OpenTelemetry/Loki: correlated traces, metrics and logs.

All adapters are optional. VektorFlow remains functional without external control-plane
services, but high-risk actions can be configured to fail closed when an adapter is required.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx


def _url(name: str) -> Optional[str]:
    value = os.getenv(name, "").strip()
    return value.rstrip("/") if value else None


async def opa_decide(input_document: Dict[str, Any], policy_path: str = "vektorflow/allow") -> Optional[Dict[str, Any]]:
    """Ask OPA for a policy decision when VF_OPA_URL is configured."""
    base = _url("VF_OPA_URL")
    if not base:
        return None
    token = os.getenv("VF_OPA_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(f"{base}/v1/data/{policy_path}", json={"input": input_document}, headers=headers)
        response.raise_for_status()
        return response.json().get("result")


async def openfga_check(
    *,
    store_id: str,
    model_id: str,
    user: str,
    relation: str,
    object_: str,
) -> Optional[Dict[str, Any]]:
    """Ask OpenFGA for relationship-based authorization when configured."""
    base = _url("VF_OPENFGA_URL")
    if not base:
        return None
    payload = {
        "tuple_key": {"user": user, "relation": relation, "object": object_},
        "authorization_model_id": model_id,
    }
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post(f"{base}/stores/{store_id}/check", json=payload)
        response.raise_for_status()
        return response.json()


async def guardrail_verdict(
    *,
    agent: str,
    action: str,
    content: str,
    context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Call an OpenGuardrails-compatible detector/gateway when configured."""
    base = _url("VF_GUARDRAILS_URL")
    if not base:
        return None
    payload = {
        "event": {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "action": action,
            "content": content,
            "context": context or {},
        }
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(f"{base}/v1/verdict", json=payload)
        response.raise_for_status()
        return response.json()


def sandbox_policy() -> Dict[str, Any]:
    """Describe the selected execution isolation backend without enabling it."""
    backend = os.getenv("VF_SANDBOX_BACKEND", "docker").strip().lower()
    supported = {"docker", "gvisor", "firecracker", "opensandbox"}
    if backend not in supported:
        backend = "docker"
    return {
        "backend": backend,
        "network_default": "none",
        "filesystem_default": "isolated",
        "host_filesystem_mounts": False,
        "enabled": os.getenv("VF_DOCKER_ENABLED", "false").lower() == "true"
            if backend == "docker" else False,
        "fail_closed_high_risk": os.getenv("VF_SANDBOX_FAIL_CLOSED", "true").lower() == "true",
    }


def telemetry_context(
    *,
    mission_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent: Optional[str] = None,
    workflow_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Stable correlation fields for OpenTelemetry/Loki/other observability backends."""
    return {
        "trace_id": str(uuid.uuid4()),
        "mission_id": mission_id,
        "task_id": task_id,
        "agent": agent,
        "workflow_id": workflow_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
