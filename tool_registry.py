"""VektorFlow 15XR canonical agent/tool registry.

Agent definitions remain the source of truth for available handlers. This
registry exposes their declared capabilities with authorization metadata so
Mission Control and the dashboard can inspect the same contract.
"""
from __future__ import annotations
from typing import Any, Dict, List
from policy_engine import DEFAULT_AGENT_POLICY, DENIED_TOOLS

def list_agent_tools(agent: Any) -> List[Dict[str, Any]]:
    result=[]
    for item in getattr(agent, "tools", []) or []:
        name=item.get("name") if isinstance(item, dict) else str(item)
        result.append({
            "name": name,
            "description": item.get("description","") if isinstance(item, dict) else "",
            "authorization": "declared" if name not in DENIED_TOOLS else "denied",
        })
    return result

def build_registry(orchestrator: Any) -> Dict[str, Any]:
    agents={}
    for agent in getattr(orchestrator, "agents", {}).values():
        agents[agent.name]={
            "description": agent.description,
            "tools": list_agent_tools(agent),
            "policy": dict(DEFAULT_AGENT_POLICY),
        }
    return {"version":"1.0","authority":"mission-control","agents":agents}

def agent_can_use_tool(orchestrator: Any, agent_name: str, tool_name: str) -> bool:
    agent=orchestrator.get_agent(agent_name)
    if not agent or tool_name in DENIED_TOOLS:
        return False
    return tool_name in {
        item.get("name") for item in getattr(agent, "tools", [])
        if isinstance(item, dict)
    }
