"""VektorFlow Mission Planner.

Borrow/adapt pattern: explicit DAG planning with deterministic dependencies.
The planner produces a canonical plan; it does not execute external actions.
"""
from __future__ import annotations

from typing import Any, Dict, List

try:
    from vektorflow_agents import AGENT_ROLES
except Exception:
    AGENT_ROLES = []

# The sequence is intentional: discovery/economics/security/policy establish
# evidence and guardrails before execution-oriented roles act.
DEFAULT_PHASES = {
    "Scout": 0,
    "ViralDet": 0,
    "Shadow": 0,
    "Smaug": 1,
    "Aegis": 1,
    "Arbiter": 2,
    "Architect": 2,
    "Cerebrum": 2,
    "DaVinci": 3,
    "Rook": 3,
    "Echo": 3,
    "Bundler": 3,
    "Pivot": 4,
    "Sentinel": 4,
    "Oracle": 5,
}

def build_mission_plan(objective: str, constraints: Dict[str, Any] | None = None) -> Dict[str, Any]:
    constraints = constraints or {}
    descriptions = dict(AGENT_ROLES)
    names = [name for name, _ in AGENT_ROLES]
    tasks: List[Dict[str, Any]] = []
    for name in names:
        phase = DEFAULT_PHASES.get(name, 0)
        deps = [t["id"] for t in tasks if t["phase"] < phase]
        # Keep the DAG bounded: depend on the immediately preceding phase.
        if deps:
            max_phase = max(t["phase"] for t in tasks if t["id"] in deps)
            deps = [t["id"] for t in tasks if t["phase"] == max_phase]
        tasks.append({
            "id": f"plan_{name.lower()}",
            "agent": name,
            "instruction": f"{objective} — {descriptions.get(name, '')}",
            "dependencies": deps,
            "phase": phase,
            "risk": "medium",
        })
    return {
        "version": "1.0",
        "objective": objective,
        "constraints": constraints,
        "task_count": len(tasks),
        "tasks": tasks,
    }
