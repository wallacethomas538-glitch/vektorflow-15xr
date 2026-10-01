"""VektorFlow policy and authorization engine.

Native implementation of infrastructure patterns inspired by workflow/LLM gateways:
- agent-scoped tool permissions
- model allowlists
- risk-aware human approval
- per-agent request/token budgets
- auditable authorization decisions

This module intentionally does not copy implementation code from external projects.
"""
from __future__ import annotations
import os, time, threading
from collections import defaultdict
from typing import Any, Dict, Optional

DEFAULT_AGENT_POLICY = {
    "tools": "declared",
    "models": "*",
    "rpm": int(os.getenv("VF_AGENT_RPM", "60")),
    "tpm": int(os.getenv("VF_AGENT_TPM", "120000")),
}

# Explicitly deny host-level execution tools by default.
DENIED_TOOLS = {"host_shell", "host_exec", "host_filesystem"}

class PolicyDenied(Exception):
    pass

_lock = threading.Lock()
_requests = defaultdict(list)
_tokens = defaultdict(list)

def _tool_names(agent: str) -> set[str]:
    try:
        from agents import get_orchestrator
        a = get_orchestrator().get_agent(agent)
        return {str(t.get("name")) for t in (a.tools if a else [])}
    except Exception:
        return set()

def authorize_tool(agent: str, tool: str, *, mission_id: Optional[str]=None,
                   risk: str="medium", require_approval: bool=False) -> Dict[str, Any]:
    if tool in DENIED_TOOLS:
        return {"decision":"reject","allowed":False,"reason":"Host-level execution is prohibited by default."}
    allowed = tool in _tool_names(agent)
    if not allowed:
        return {"decision":"reject","allowed":False,"reason":f"Tool '{tool}' is not assigned to agent '{agent}'."}
    if require_approval or risk.lower() in {"high","critical"}:
        return {"decision":"ask","allowed":False,"reason":"Human approval is required before this tool action."}
    return {"decision":"allow","allowed":True,"reason":"Tool is assigned to the agent and passed policy checks."}

def authorize_model(agent: str, model: str, *, mission_id: Optional[str]=None) -> Dict[str, Any]:
    allowed = os.getenv("VF_ALLOWED_MODELS", "").strip()
    if allowed:
        models = {m.strip() for m in allowed.split(",") if m.strip()}
        if model not in models and not any(model.startswith(m.rstrip("*")) for m in models if m.endswith("*")):
            return {"decision":"reject","allowed":False,"reason":"Model is outside the configured VektorFlow allowlist."}
    return {"decision":"allow","allowed":True,"reason":"Model passed VektorFlow model policy."}

def authorize_llm_request(agent: str, model: str, estimated_tokens: int=0,
                          *, mission_id: Optional[str]=None) -> Dict[str, Any]:
    model_result = authorize_model(agent, model, mission_id=mission_id)
    if not model_result["allowed"]:
        return model_result
    key = agent.lower()
    now = time.time()
    rpm = DEFAULT_AGENT_POLICY["rpm"]
    tpm = DEFAULT_AGENT_POLICY["tpm"]
    with _lock:
        _requests[key] = [t for t in _requests[key] if t > now - 60]
        _tokens[key] = [(t,c) for t,c in _tokens[key] if t > now - 60]
        if len(_requests[key]) >= rpm:
            return {"decision":"reject","allowed":False,"reason":"Agent request-per-minute limit exceeded.","retry_after":60}
        used_tokens = sum(c for _,c in _tokens[key])
        if estimated_tokens and used_tokens + estimated_tokens > tpm:
            return {"decision":"reject","allowed":False,"reason":"Agent token-per-minute limit exceeded.","retry_after":60}
        _requests[key].append(now)
        _tokens[key].append((now, max(0, estimated_tokens)))
    return {"decision":"allow","allowed":True,"reason":"LLM request passed model and agent budget policy."}

def record_usage(agent: str, tokens: int=0) -> None:
    with _lock:
        _tokens[agent.lower()].append((time.time(), max(0, int(tokens))))

def policy_status() -> Dict[str, Any]:
    return {
        "status":"operational",
        "default_rpm": DEFAULT_AGENT_POLICY["rpm"],
        "default_tpm": DEFAULT_AGENT_POLICY["tpm"],
        "allowed_models": os.getenv("VF_ALLOWED_MODELS", "").strip() or "*",
        "host_execution_denied_by_default": True,
        "denied_tools": sorted(DENIED_TOOLS),
    }
