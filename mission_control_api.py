"""HTTP API for VektorFlow Mission & Control."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mission_planner import build_mission_plan
from mission_control import (
    MISSION_STATES,
    ALLOWED_TRANSITIONS,
    create_mission,
    get_mission,
    list_missions,
    transition_mission,
    add_task,
    list_tasks,
    propose_action,
    get_action_proposal,
    list_pending_actions,
    resolve_action,
    get_audit,
    mission_summary,
    init_mission_control,
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


@router.get("/summary")
async def summary(email: str = "commander@vektorflow.com"):
    return {"status": "success", **mission_summary(email)}


@router.get("/states")
async def states():
    return {"states": MISSION_STATES, "allowed_transitions": {k: sorted(v) for k, v in ALLOWED_TRANSITIONS.items()}}


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
        return {"status": "success", "mission": transition_mission(
            mission_id, data.to_state, data.actor, data.email, data.details
        )}
    except ValueError as exc:
        raise HTTPException(409, str(exc))


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
        plan = build_mission_plan(mission["objective"], mission.get("constraints") or {})
        if not existing:
            task_lookup = {}
            for spec in plan["tasks"]:
                deps = [task_lookup[d] for d in spec["dependencies"] if d in task_lookup]
                created = add_task(mission_id, spec["agent"], spec["instruction"], deps, spec["risk"])
                task_lookup[spec["id"]] = created["id"]
        if get_mission(mission_id, email)["state"] == "planning":
            transition_mission(
                mission_id, "ready", "mission-planner", email,
                {"task_count": plan["task_count"], "planner_version": plan["version"]},
            )
        return {
            "status": "success",
            "mission": get_mission(mission_id, email),
            "plan": plan,
            "tasks": list_tasks(mission_id),
        }
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.post("/missions/{mission_id}/execute")
async def execute_mission(mission_id: str, email: str = "commander@vektorflow.com"):
    """Execute an approved mission through the existing VektorFlow orchestrator."""
    mission = get_mission(mission_id, email)
    if not mission:
        raise HTTPException(404, "Mission not found")
    if mission["state"] not in {"ready", "approved"}:
        raise HTTPException(409, f"Mission must be ready or approved; current state is {mission['state']}")
    try:
        transition_mission(mission_id, "executing", "mission-control", email)
        from agents import AgentContext, get_orchestrator
        from database import get_user, get_user_stores, get_llm_keys, get_icp_data, get_all_memory
        context = AgentContext(
            email=email,
            user=get_user(email) or {},
            stores=get_user_stores(email) or [],
            llm_keys=get_llm_keys(email) or {},
            icp=get_icp_data(email) or {},
            memory=get_all_memory(email) or {},
            params={"mission_id": mission_id, "mission": mission},
        )
        result = await get_orchestrator().team_execute(mission["objective"], context)
        transition_mission(mission_id, "completed", "mission-control", email, {"agent_count": 15})
        return {"status": "success", "mission": get_mission(mission_id, email), "result": result}
    except Exception as exc:
        try:
            transition_mission(mission_id, "failed", "mission-control", email, {"error": str(exc)})
        except Exception:
            pass
        raise HTTPException(502, f"Mission execution failed: {exc}")


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
