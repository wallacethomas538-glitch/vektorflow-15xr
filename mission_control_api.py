"""HTTP API for VektorFlow Mission & Control."""
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mission_planner import build_mission_plan, build_mission_plan_async
from ai_observability import start_span
from mission_control import (
    MISSION_STATES,
    can_transition,
    create_mission,
    get_mission,
    list_missions,
    transition_mission,
    add_task,
    list_tasks,
    transition_task,
    set_mission_result,
    propose_action,
    get_action_proposal,
    list_pending_actions,
    resolve_action,
    get_audit,
    mission_summary,
    init_mission_control,
    _open_db,
    _cursor,
)

router = APIRouter(prefix="/api/v1/mission-control", tags=["mission-control"])


class MissionCreate(BaseModel):
    objective: str
    email: str = "commander@vektorflow.com"
    constraints: Dict[str, Any] = Field(default_factory=dict)
    priority: str = "normal"
    success_criteria: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TransitionRequest(BaseModel):
    to_state: str
    actor: str = "commander"
    email: str = "commander@vektorflow.com"
    details: Dict[str, Any] = Field(default_factory=dict)


class TaskCreate(BaseModel):
    agent: str
    instruction: str
    dependencies: List[str] = Field(default_factory=list)
    risk: str = "medium"


class ActionProposalCreate(BaseModel):
    agent: str
    action: str
    risk: str = "medium"
    email: str = "commander@vektorflow.com"
    mission_id: Optional[str] = None
    task_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ActionDecision(BaseModel):
    decision: str
    actor: str = "commander"
    email: str = "commander@vektorflow.com"
    note: str = ""


@router.on_event("startup")
async def startup():
    init_mission_control()
    _resume_approved_missions()


def _approved_missions_pending():
    """(id, email) pairs for missions stuck in 'approved' without execution.

    Approvals used to only flip the state flag, so missions approved before the
    auto-execute fix (or stranded by a restart) sit in 'approved' forever.
    """
    conn, _pg = _open_db()
    cur = _cursor(conn, _pg)
    try:
        cur.execute("SELECT id, email FROM missions WHERE state = 'approved'")
        rows = cur.fetchall() or []
        return [
            (r["id"], r["email"]) if isinstance(r, dict) else (r[0], r[1])
            for r in rows
        ]
    except Exception:
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _resume_approved_missions() -> None:
    """Launch background execution for approved-but-never-executed missions."""
    for mission_id, email in _approved_missions_pending():
        asyncio.create_task(_execute_mission_background(mission_id, email))


@router.get("/summary")
async def summary(email: str = "commander@vektorflow.com"):
    return {"status": "success", **mission_summary(email)}


@router.get("/states")
async def states():
    return {"states": MISSION_STATES, "policy": "can_transition(from_state, to_state)"}


@router.get("/missions")
async def missions(email: str = "commander@vektorflow.com", state: Optional[str] = None, limit: int = 50):
    return {"status": "success", "missions": list_missions(email, state, min(limit, 200))}


@router.post("/missions")
async def create(data: MissionCreate):
    return {"status": "success", "mission": create_mission(
        email=data.email, objective=data.objective, constraints=data.constraints,
        priority=data.priority, success_criteria=data.success_criteria, metadata=data.metadata,
    )}


@router.get("/missions/{mission_id}")
async def detail(mission_id: str, email: str = "commander@vektorflow.com"):
    mission = get_mission(mission_id, email)
    if not mission:
        raise HTTPException(404, "Mission not found")
    return {"status": "success", "mission": mission, "tasks": list_tasks(mission_id), "audit": get_audit(mission_id)}


@router.post("/missions/{mission_id}/transition")
async def transition(mission_id: str, data: TransitionRequest):
    try:
        mission = transition_mission(
            mission_id, data.to_state, data.actor, data.email, data.details
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    # Approval now kicks off real execution: the 15-agent team runs in the
    # background and the mission record carries the honest per-task outcome,
    # instead of sitting in 'approved' with nothing happening.
    if mission.get("state") == "approved":
        asyncio.create_task(_execute_mission_background(mission_id, data.email))
        mission = get_mission(mission_id, data.email)
    return {"status": "success", "mission": mission}


@router.post("/missions/{mission_id}/plan")
async def plan_mission(mission_id: str, email: str = "commander@vektorflow.com"):
    """Create the canonical 15-agent task plan without executing external actions."""
    mission = get_mission(mission_id, email)
    if not mission:
        raise HTTPException(404, "Mission not found")
    try:
        if mission["state"] == "draft":
            transition_mission(mission_id, "planning", "mission-planner", email)
        existing = list_tasks(mission_id)
        plan = await build_mission_plan_async(mission["objective"], mission.get("constraints") or {})
        if not existing:
            _create_plan_tasks(mission_id, plan)
        if get_mission(mission_id, email)["state"] == "planning":
            transition_mission(
                mission_id, "ready", "mission-planner", email,
                {"task_count": len(plan["tasks"]), "planner_version": "llm-envelope-v2"},
            )
        return {
            "status": "success",
            "mission": get_mission(mission_id, email),
            "plan": plan,
            "tasks": list_tasks(mission_id),
        }
    except ValueError as exc:
        raise HTTPException(409, str(exc))


def _create_plan_tasks(mission_id: str, plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Create mission_tasks rows from a planner plan, translating spec ids to real task ids."""
    task_lookup: Dict[str, str] = {}
    for index, spec in enumerate(plan["tasks"]):
        deps = [task_lookup[d] for d in spec["dependencies"] if d in task_lookup]
        created = add_task(mission_id, spec["agent"], spec["instruction"], deps, spec["risk"])
        task_lookup[str(index)] = created["id"]
    return list_tasks(mission_id)


def _dependency_order(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order tasks so every task runs after its dependencies (planner DAG).

    Dependencies reference real task ids. Unknown dep ids are ignored;
    a cycle degrades to plan order rather than deadlocking.
    """
    by_id = {t["id"]: t for t in tasks}
    ordered: List[Dict[str, Any]] = []
    placed = set()
    remaining = list(tasks)
    while remaining:
        progressed = False
        for task in list(remaining):
            deps = task.get("dependencies") or []
            if all(d in placed or d not in by_id for d in deps):
                ordered.append(task)
                placed.add(task["id"])
                remaining.remove(task)
                progressed = True
        if not progressed:
            task = remaining.pop(0)
            ordered.append(task)
            placed.add(task["id"])
    return ordered


# Agent outputs that prove nothing was actually done. A task may only be
# marked completed when its agent produced real evidence — never on one of
# these placeholders.
_EMPTY_AGENT_MESSAGES = {
    "i am ready to help, but i do not have enough information to answer that yet.",
}


# Tools that only re-read shared context: they never count as the agent's own work.
_CONTEXT_READ_TOOLS = {"read_team_results", "read_memory"}


def _agent_work_succeeded(agent_result: Any) -> tuple:
    """Decide whether an agent's returned payload counts as real completed work.

    Returns (ok, reason). agent.run() itself never raises for agent-level
    failures — it returns an honest error/blocked dict — so this guard is what
    stops an empty, placeholder, or work-free response from being recorded as
    completed. Merely re-reading shared team context is not work.
    """
    if not isinstance(agent_result, dict):
        text = str(agent_result or "").strip()
        return (bool(text), "" if text else "agent returned no usable output")
    status = str(agent_result.get("status", "")).lower()
    error = agent_result.get("error")
    if status in {"failed", "blocked"} or error:
        return False, str(error or f"agent reported status '{status or 'unknown'}'")
    message = str(agent_result.get("message", "")).strip()
    if message and message.lower() not in _EMPTY_AGENT_MESSAGES:
        return True, ""
    if message:
        # Non-empty but a known placeholder response.
        return False, "agent returned a placeholder response instead of doing the work"
    own_output = (
        agent_result.get("evidence")
        or agent_result.get("data")
        or agent_result.get("actions")
        or agent_result.get("handoff")
    )
    if own_output:
        return True, ""
    tool_calls = agent_result.get("tool_calls") or []
    real_tool_work = any(
        isinstance(tc, dict)
        and tc.get("status") == "completed"
        and tc.get("tool") not in _CONTEXT_READ_TOOLS
        for tc in tool_calls
    )
    if real_tool_work:
        return True, ""
    return False, "agent completed with no message and no evidence of its own work"


async def _execute_mission_task(orchestrator, context, mission_id: str, objective: str,
                               task: Dict[str, Any], outcomes: Dict[str, str]) -> None:
    """Run ONE planned task through its real agent and persist the real outcome.

    Transitions the task row pending -> running -> completed/failed and stores
    the agent's actual output as the task result. A task is only marked
    completed when its agent genuinely did the work.
    """
    task_id = task["id"]
    if task.get("status") == "completed":
        # Idempotent re-run: real work was already done and recorded on an
        # earlier run. Keep the result, do not redo or fake anything.
        outcomes[task_id] = "completed"
        return
    agent_name = task.get("agent") or ""
    agent = orchestrator.get_agent(agent_name)
    if agent is None:
        transition_task(task_id, "failed", actor="mission-control", result={
            "agent": agent_name,
            "error": f"Unknown agent '{agent_name}': not on the 15-agent roster, so no work was done.",
        })
        outcomes[task_id] = "failed"
        return

    transition_task(task_id, "running", actor="mission-control")
    context.params = {**(context.params or {}), "task_id": task_id}

    failed_deps = [d for d in (task.get("dependencies") or []) if outcomes.get(d) == "failed"]
    dep_note = ""
    if failed_deps:
        dep_note = (f"\n\nNote: these earlier tasks failed: {', '.join(failed_deps)}. "
                    f"Do your part with the evidence that IS available and state clearly what is missing.")

    instruction = (
        f"Mission objective: {objective}\n\n"
        f"Your assigned task: {task.get('instruction', '')}{dep_note}\n\n"
        f"Do the work for THIS task now. Return concrete findings, actions taken, "
        f"and evidence. Never claim work was completed unless you actually perform it."
    )
    agent_result = await agent.run(context, instruction)

    ok, reason = _agent_work_succeeded(agent_result)
    # The shared team record carries the adjudicated outcome — never a raw
    # placeholder masquerading as good evidence for downstream agents.
    recorded = {
        "agent": agent_name,
        "task_status": "completed" if ok else "failed",
        "outcome": agent_result,
    }
    if ok:
        transition_task(task_id, "completed", actor="mission-control", result=recorded)
        outcomes[task_id] = "completed"
    else:
        recorded["error"] = reason
        transition_task(task_id, "failed", actor="mission-control", result=recorded)
        outcomes[task_id] = "failed"
    context.results[agent_name.lower()] = recorded


def _best_effort(label: str, fn, default):
    """Run a context lookup; on failure return the default and keep going.

    Enrichment (memory, stores, keys) must never kill a mission run — the team
    works with whatever context is actually available.
    """
    try:
        value = fn()
        return value if value is not None else default
    except Exception as exc:
        print(f"[mission-control] context '{label}' unavailable ({exc}); continuing without it")
        return default


async def _run_mission_team(mission_id: str, email: str):
    """Run the 15-agent team task-by-task through the real orchestrator.

    Each planned task row transitions pending -> running -> completed/failed as
    its assigned agent genuinely does the work, in planner dependency order.
    The mission-level result is synthesized from the real per-task records.
    Shared by both execute modes.
    """
    mission = get_mission(mission_id, email)
    objective = (mission or {}).get("objective", "")
    try:
        from vektorflow_agents import AgentContext, get_orchestrator
        from database import get_user, get_user_stores, get_llm_keys, get_icp_data, get_all_memory
        context = AgentContext(
            email=email,
            user=_best_effort("user", lambda: get_user(email), {}),
            stores=_best_effort("stores", lambda: get_user_stores(email), []),
            llm_keys=_best_effort("llm_keys", lambda: get_llm_keys(email), {}),
            icp=_best_effort("icp", lambda: get_icp_data(email), {}),
            memory=_best_effort("memory", lambda: get_all_memory(email), {}),
            params={"mission_id": mission_id, "mission": mission},
        )
        tasks = list_tasks(mission_id)
        if not tasks:
            # Approved without a plan: build the canonical 15-agent plan now
            # so there are real task rows for the team to execute.
            plan = build_mission_plan(objective, (mission or {}).get("constraints") or {})
            tasks = _create_plan_tasks(mission_id, plan)
        else:
            # Re-run safety: reconcile task rows left over from an earlier
            # interrupted run. Leftover "pending" tasks run as-is. Anything
            # non-terminal (failed / cancelled / running-stuck-after-crash)
            # is requeued to pending for an honest retry through the normal
            # flow. Tasks already "completed" are left untouched — their
            # agents genuinely did the work, so it is never redone and never
            # faked; _execute_mission_task skips them idempotently.
            reconciled: List[Dict[str, Any]] = []
            for task in tasks:
                status = task["status"]
                if status in ("completed", "pending"):
                    reconciled.append(task)
                else:
                    reconciled.append(
                        transition_task(task["id"], "pending", actor="mission-control")
                    )
            tasks = reconciled
        orchestrator = get_orchestrator()
        outcomes: Dict[str, str] = {}
        replans = 0
        with start_span("vektorflow.mission", {"vf.mission_id": mission_id, "vf.workflow_id": mission_id, "vf.objective": objective}):
            for task in _dependency_order(tasks):
                await _execute_mission_task(orchestrator, context, mission_id, objective, task, outcomes)
                if outcomes.get(task["id"]) == "failed" and replans < 3:
                    replans += 1
                    # Safe retry: preserve the honest failure record, then let the
                    # planner choose a fresh envelope on the next execution pass.
                    transition_task(task["id"], "pending", actor="mission-planner")
                    await _execute_mission_task(orchestrator, context, mission_id, objective, task, outcomes)
        final_tasks = list_tasks(mission_id)
        failed = [t for t in final_tasks if t["status"] == "failed"]
        completed = [t for t in final_tasks if t["status"] == "completed"]
        result = {
            "status": "failed" if failed else "completed",
            "goal": objective,
            "task_count": len(final_tasks),
            "completed_count": len(completed),
            "failed_count": len(failed),
            "failed_tasks": [
                {"task_id": t["id"], "agent": t.get("agent"),
                 "error": (t.get("result") or {}).get("error")}
                for t in failed
            ],
            "replans": replans,
            "summary": context.results.get("oracle", {}),
            "tasks": [
                {"task_id": t["id"], "agent": t.get("agent"),
                 "instruction": t.get("instruction"), "status": t.get("status"),
                 "result": t.get("result")}
                for t in final_tasks
            ],
        }
        set_mission_result(mission_id, result)
        transition_mission(
            mission_id, "failed" if failed else "completed", "mission-control", email,
            {"task_count": len(final_tasks), "completed": len(completed), "failed": len(failed)},
        )
        return result
    except Exception as exc:
        try:
            set_mission_result(mission_id, {"status": "failed", "goal": objective, "error": str(exc)})
            transition_mission(mission_id, "failed", "mission-control", email, {"error": str(exc)})
        except Exception:
            pass
        raise


async def _execute_mission_background(mission_id: str, email: str) -> None:
    """Background wrapper: never let an exception escape an asyncio task."""
    try:
        await _run_mission_team(mission_id, email)
    except Exception:
        pass  # mission already transitioned to failed inside _run_mission_team


@router.post("/missions/{mission_id}/execute")
async def execute_mission(mission_id: str, email: str = "commander@vektorflow.com", wait: bool = True):
    """Execute an approved mission through the existing VektorFlow orchestrator.

    wait=true (default): run inline and return the result (original behavior).
    wait=false: transition to executing, launch a background job, return 202-style
    acceptance immediately; poll GET /missions/{mission_id} for completion.
    """
    mission = get_mission(mission_id, email)
    if not mission:
        raise HTTPException(404, "Mission not found")
    if mission["state"] not in {"ready", "approved"}:
        raise HTTPException(409, f"Mission must be ready or approved; current state is {mission['state']}")
    try:
        transition_mission(mission_id, "executing", "mission-control", email)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if not wait:
        asyncio.create_task(_execute_mission_background(mission_id, email))
        return {"status": "accepted", "mission": get_mission(mission_id, email)}
    try:
        result = await _run_mission_team(mission_id, email)
    except Exception as exc:
        raise HTTPException(502, f"Mission execution failed: {exc}")
    return {"status": "success", "mission": get_mission(mission_id, email), "result": result}


@router.post("/missions/{mission_id}/tasks")
async def task(mission_id: str, data: TaskCreate):
    if not get_mission(mission_id):
        raise HTTPException(404, "Mission not found")
    return {"status": "success", "task": add_task(
        mission_id, data.agent, data.instruction, data.dependencies, data.risk
    )}


@router.get("/missions/{mission_id}/tasks")
async def tasks(mission_id: str):
    return {"status": "success", "tasks": list_tasks(mission_id)}


@router.post("/actions/propose")
async def action_propose(data: ActionProposalCreate):
    return {"status": "success", "proposal": propose_action(
        email=data.email, agent=data.agent, action=data.action, risk=data.risk,
        mission_id=data.mission_id, task_id=data.task_id, payload=data.payload, reason=data.reason,
    )}


@router.get("/actions/pending")
async def pending(email: str = "commander@vektorflow.com"):
    return {"status": "success", "actions": list_pending_actions(email)}


@router.get("/actions/{proposal_id}")
async def action_detail(proposal_id: str, email: str = "commander@vektorflow.com"):
    proposal = get_action_proposal(proposal_id, email)
    if not proposal:
        raise HTTPException(404, "Action proposal not found")
    return {"status": "success", "proposal": proposal}


@router.post("/actions/{proposal_id}/decision")
async def action_decision(proposal_id: str, data: ActionDecision):
    try:
        return {"status": "success", "proposal": resolve_action(
            proposal_id, data.decision, data.actor, data.email, data.note
        )}
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get("/missions/{mission_id}/audit")
async def audit(mission_id: str, limit: int = 100):
    return {"status": "success", "audit": get_audit(mission_id, min(limit, 500))}
