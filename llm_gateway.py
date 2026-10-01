"""VektorFlow agent LLM gateway.

Provides one controlled request surface for agents while preserving the existing
provider implementation in llm_handler.py. It can transparently use the optional
external LiteLLM-compatible gateway through the existing gateway/ model prefix.
"""
from __future__ import annotations
import json
from typing import Any, Dict

from llm_handler import call_llm, DEFAULT_MODEL
from policy_engine import authorize_llm_request, record_usage

async def agent_llm(agent: str, prompt: str, model: str | None,
                    user_keys: Dict[str, str], mission_id: str | None = None) -> Dict[str, Any]:
    requested_model = model or DEFAULT_MODEL
    estimate = max(1, len(prompt) // 4)
    decision = authorize_llm_request(agent, requested_model, estimate, mission_id=mission_id)
    if not decision["allowed"]:
        return {"success":False, "error":decision["reason"], "policy":decision}
    result = await call_llm(prompt, requested_model, user_keys)
    response_text = str(result.get("response",""))
    actual = max(estimate, (len(prompt) + len(response_text)) // 4)
    record_usage(agent, actual)
    result["gateway"] = "vektorflow-agent-gateway"
    result["agent"] = agent
    result["mission_id"] = mission_id
    result["policy"] = decision
    result["usage_estimate_tokens"] = actual
    return result
