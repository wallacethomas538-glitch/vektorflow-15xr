"""LLM-driven mission planning with a validated typed task envelope.

Planner output envelope (what ``_validate`` enforces, what agents consume)::

    {"tasks": [{
        "agent": "Scout",            # one of the 15 roster names, case-exact
        "instruction": "non-empty",  # the agent's actual task
        "dependencies": [0, 2],      # indices into this same tasks array
        "risk": "low|medium|high|critical",
    }]}

Any malformed envelope raises ``ValueError``; callers fall back to
``_safe_plan`` (a single Scout task carrying the objective). The sync
``build_mission_plan`` is the documented minimal-safe fallback only: it never
attempts an LLM call and always returns the safe plan.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List

try:
    from vektorflow_agents import AGENT_ROLES
except Exception:
    AGENT_ROLES = []

TASK_FIELDS = ("agent", "instruction", "dependencies", "risk")
RISKS = {"low", "medium", "high", "critical"}


def _safe_plan(objective: str) -> Dict[str, Any]:
    return {"tasks": [{"agent": "Scout", "instruction": objective, "dependencies": [], "risk": "low"}]}


def _roster() -> List[Dict[str, Any]]:
    """Live roster (names, descriptions, real tool lists) for the LLM prompt."""
    try:
        from vektorflow_agents import get_orchestrator
        return [
            {"name": a.get("name"), "description": a.get("description"), "tools": list(a.get("tools") or [])}
            for a in get_orchestrator().roster()
        ]
    except Exception:
        return [{"name": name, "description": desc, "tools": []} for name, desc in AGENT_ROLES]


def _validate_dependencies(deps: list, own_index: int, task_count: int) -> List[int]:
    indices: List[int] = []
    for dep in deps:
        if isinstance(dep, bool):
            raise ValueError("dependencies must be task indices")
        if isinstance(dep, int):
            dep_index = dep
        elif isinstance(dep, str) and re.fullmatch(r"\d+", dep.strip()):
            dep_index = int(dep.strip())
        else:
            raise ValueError("dependencies must be task indices")
        if dep_index == own_index:
            raise ValueError("task cannot depend on itself")
        if not 0 <= dep_index < task_count:
            raise ValueError("dependency index out of range")
        indices.append(dep_index)
    return indices


def _validate(plan: Any, objective: str) -> Dict[str, Any]:
    roster = {name for name, _ in AGENT_ROLES}
    if not isinstance(plan, dict) or not isinstance(plan.get("tasks"), list):
        raise ValueError("planner response must contain tasks[]")
    tasks: List[Dict[str, Any]] = []
    for raw in plan["tasks"]:
        if not isinstance(raw, dict) or not set(TASK_FIELDS) <= raw.keys():
            raise ValueError("invalid task envelope")
        if raw["agent"] not in roster or not isinstance(raw["dependencies"], list):
            raise ValueError("unknown agent or invalid dependencies")
        instruction = str(raw["instruction"]).strip()
        if not instruction:
            raise ValueError("task instruction must be non-empty")
        risk = str(raw["risk"]).lower()
        if risk not in RISKS:
            raise ValueError("invalid risk")
        tasks.append({
            "agent": raw["agent"],
            "instruction": instruction,
            "dependencies": raw["dependencies"],
            "risk": risk,
        })
    for index, task in enumerate(tasks):
        task["dependencies"] = _validate_dependencies(task["dependencies"], index, len(tasks))
    return {"tasks": tasks or _safe_plan(objective)["tasks"]}


async def build_mission_plan_async(objective: str, constraints: Dict[str, Any] | None = None) -> Dict[str, Any]:
    constraints = constraints or {}
    prompt = ("Return JSON only with tasks[]. Each task has agent, instruction, dependencies, risk. "
              "Use only roster agent names; dependencies reference task indices.\n" +
              json.dumps({"objective": objective, "roster": _roster(), "constraints": constraints}))
    try:
        from llm_handler import call_llm, DEFAULT_MODEL
        response = await call_llm(prompt, DEFAULT_MODEL, constraints.get("llm_keys", {}), None)
        text = response.get("response", "{}")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        return _validate(json.loads(match.group(0) if match else text), objective)
    except Exception:
        return _safe_plan(objective)


def build_mission_plan(objective: str, constraints: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Minimal-safe sync fallback: never calls an LLM; returns the safe plan."""
    return _safe_plan(objective)
