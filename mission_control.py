"""VektorFlow 15XR Mission & Control layer.

Concepts adapted from open-source agent orchestration patterns:
- explicit mission lifecycle/state machine
- policy-governed autonomy
- risk-tiered action proposals
- human approval gates
- execution/audit timeline
- workflow task dependencies
- budget/cap controls

This module is a native VektorFlow implementation; it does not copy FleetQ source code.
The current persistence adapter uses VektorFlow's existing database layer so the
feature does not replace or delete the existing SQLite/Supabase paths.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import get_db


MISSION_STATES = [
    "draft",
    "planning",
    "ready",
    "awaiting_approval",
    "approved",
    "executing",
    "paused",
    "blocked",
    "completed",
    "failed",
    "cancelled",
]

ALLOWED_TRANSITIONS = {
    "draft": {"planning", "cancelled"},
    "planning": {"ready", "blocked", "failed", "cancelled"},
    "ready": {"awaiting_approval", "approved", "executing", "cancelled"},
    "awaiting_approval": {"approved", "blocked", "cancelled"},
    "approved": {"executing", "paused", "cancelled"},
    "executing": {"paused", "completed", "failed", "blocked", "awaiting_approval", "cancelled"},
    "paused": {"executing", "cancelled"},
    "blocked": {"planning", "ready", "awaiting_approval", "cancelled"},
    "completed": set(),
    "failed": {"planning", "cancelled"},
    "cancelled": set(),
}

RISK_POLICIES = {
    "low": "auto",
    "medium": "ask",
    "high": "ask",
    "critical": "reject",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, default=str)


def init_mission_control() -> None:
    """Create only the Mission & Control tables if they do not already exist."""
    conn = get_db()
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS missions (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            objective TEXT NOT NULL,
            constraints TEXT NOT NULL DEFAULT '{}',
            priority TEXT NOT NULL DEFAULT 'normal',
            success_criteria TEXT NOT NULL DEFAULT '{}',
            state TEXT NOT NULL DEFAULT 'draft',
            workflow TEXT NOT NULL DEFAULT '{}',
            metadata TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS mission_tasks (
            id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL,
            agent TEXT NOT NULL,
            instruction TEXT NOT NULL,
            dependencies TEXT NOT NULL DEFAULT '[]',
            risk TEXT NOT NULL DEFAULT 'medium',
            status TEXT NOT NULL DEFAULT 'pending',
            result TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS action_proposals (
            id TEXT PRIMARY KEY,
            mission_id TEXT,
            task_id TEXT,
            email TEXT NOT NULL,
            agent TEXT NOT NULL,
            action TEXT NOT NULL,
            risk TEXT NOT NULL DEFAULT 'medium',
            decision TEXT NOT NULL DEFAULT 'pending',
            policy TEXT NOT NULL DEFAULT 'ask',
            reason TEXT NOT NULL DEFAULT '',
            payload TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            resolved_at TEXT
        );

        CREATE TABLE IF NOT EXISTS mission_audit (
            id TEXT PRIMARY KEY,
            mission_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            event_type TEXT NOT NULL,
            from_state TEXT,
            to_state TEXT,
            details TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_missions_email_state ON missions(email, state);
        CREATE INDEX IF NOT EXISTS idx_tasks_mission ON mission_tasks(mission_id);
        CREATE INDEX IF NOT EXISTS idx_proposals_mission ON action_proposals(mission_id);
        CREATE INDEX IF NOT EXISTS idx_audit_mission ON mission_audit(mission_id, created_at);
        """
    )
    conn.commit()
    conn.close()


def _row(row: Any) -> Dict[str, Any]:
    if row is None:
        return {}
    result = dict(row)
    for key in ("constraints", "success_criteria", "workflow", "metadata", "dependencies", "result", "payload", "details"):
        if key in result:
            try:
                result[key] = json.loads(result[key] or "{}")
            except Exception:
                pass
    return result


def _audit(cur, mission_id: str, actor: str, event_type: str, details: Dict[str, Any],
           from_state: Optional[str] = None, to_state: Optional[str] = None) -> None:
    cur.execute(
        """INSERT INTO mission_audit
        (id, mission_id, actor, event_type, from_state, to_state, details, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (uuid.uuid4().hex, mission_id, actor, event_type, from_state, to_state, _json(details), _now()),
    )


def create_mission(
    email: str,
    objective: str,
    constraints: Optional[Dict[str, Any]] = None,
    priority: str = "normal",
    success_criteria: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    init_mission_control()
    mission_id = "msn_" + uuid.uuid4().hex
    now = _now()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO missions
        (id,email,objective,constraints,priority,success_criteria,state,workflow,metadata,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            mission_id, email, objective, _json(constraints), priority,
            _json(success_criteria), "draft", _json({}), _json(metadata), now, now,
        ),
    )
    _audit(cur, mission_id, email, "mission.created", {"objective": objective}, None, "draft")
    conn.commit()
    conn.close()
    return get_mission(mission_id, email)


def get_mission(mission_id: str, email: Optional[str] = None) -> Dict[str, Any]:
    init_mission_control()
    conn = get_db()
    cur = conn.cursor()
    if email:
        cur.execute("SELECT * FROM missions WHERE id = ? AND email = ?", (mission_id, email))
    else:
        cur.execute("SELECT * FROM missions WHERE id = ?", (mission_id,))
    row = cur.fetchone()
    conn.close()
    return _row(row)


def list_missions(email: str, state: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    init_mission_control()
    conn = get_db()
    cur = conn.cursor()
    if state:
        cur.execute("SELECT * FROM missions WHERE email = ? AND state = ? ORDER BY created_at DESC LIMIT ?", (email, state, limit))
    else:
        cur.execute("SELECT * FROM missions WHERE email = ? ORDER BY created_at DESC LIMIT ?", (email, limit))
    rows = cur.fetchall()
    conn.close()
    return [_row(row) for row in rows]


def transition_mission(mission_id: str, to_state: str, actor: str, email: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    init_mission_control()
    mission = get_mission(mission_id, email)
    if not mission:
        raise ValueError("Mission not found")
    from_state = mission["state"]
    if to_state not in ALLOWED_TRANSITIONS.get(from_state, set()):
        raise ValueError(f"Invalid mission transition: {from_state} -> {to_state}")
    now = _now()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE missions SET state = ?, updated_at = ?, completed_at = ? WHERE id = ?",
        (to_state, now, now if to_state == "completed" else None, mission_id),
    )
    _audit(cur, mission_id, actor, "mission.transitioned", details or {}, from_state, to_state)
    conn.commit()
    conn.close()
    return get_mission(mission_id, email)


def add_task(mission_id: str, agent: str, instruction: str, dependencies: Optional[List[str]] = None, risk: str = "medium") -> Dict[str, Any]:
    init_mission_control()
    task_id = "tsk_" + uuid.uuid4().hex
    now = _now()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO mission_tasks
        (id,mission_id,agent,instruction,dependencies,risk,status,result,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (task_id, mission_id, agent, instruction, _json(dependencies or []), risk, "pending", _json({}), now, now),
    )
    _audit(cur, mission_id, agent, "task.created", {"task_id": task_id, "agent": agent, "risk": risk})
    conn.commit()
    conn.close()
    return get_task(task_id)


def get_task(task_id: str) -> Dict[str, Any]:
    init_mission_control()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mission_tasks WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    return _row(row)


def list_tasks(mission_id: str) -> List[Dict[str, Any]]:
    init_mission_control()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mission_tasks WHERE mission_id = ? ORDER BY created_at ASC", (mission_id,))
    rows = cur.fetchall()
    conn.close()
    return [_row(row) for row in rows]


def propose_action(
    email: str,
    agent: str,
    action: str,
    risk: str = "medium",
    mission_id: Optional[str] = None,
    task_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    reason: str = "",
) -> Dict[str, Any]:
    init_mission_control()
    risk = risk.lower()
    policy = RISK_POLICIES.get(risk, "ask")
    proposal_id = "apr_" + uuid.uuid4().hex
    decision = "approved" if policy == "auto" else ("rejected" if policy == "reject" else "pending")
    now = _now()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO action_proposals
        (id,mission_id,task_id,email,agent,action,risk,decision,policy,reason,payload,created_at,resolved_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (proposal_id, mission_id, task_id, email, agent, action, risk, decision, policy, reason, _json(payload), now, now if decision != "pending" else None),
    )
    if mission_id:
        _audit(cur, mission_id, agent, "action.proposed", {
            "proposal_id": proposal_id, "action": action, "risk": risk, "policy": policy, "decision": decision,
        })
    conn.commit()
    conn.close()
    return get_action_proposal(proposal_id, email)


def get_action_proposal(proposal_id: str, email: Optional[str] = None) -> Dict[str, Any]:
    init_mission_control()
    conn = get_db()
    cur = conn.cursor()
    if email:
        cur.execute("SELECT * FROM action_proposals WHERE id = ? AND email = ?", (proposal_id, email))
    else:
        cur.execute("SELECT * FROM action_proposals WHERE id = ?", (proposal_id,))
    row = cur.fetchone()
    conn.close()
    return _row(row)


def list_pending_actions(email: str, limit: int = 50) -> List[Dict[str, Any]]:
    init_mission_control()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM action_proposals WHERE email = ? AND decision = 'pending' ORDER BY created_at DESC LIMIT ?", (email, limit))
    rows = cur.fetchall()
    conn.close()
    return [_row(row) for row in rows]


def resolve_action(proposal_id: str, decision: str, actor: str, email: Optional[str] = None, note: str = "") -> Dict[str, Any]:
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected")
    proposal = get_action_proposal(proposal_id, email)
    if not proposal:
        raise ValueError("Action proposal not found")
    if proposal["decision"] != "pending":
        raise ValueError("Action proposal is already resolved")
    now = _now()
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE action_proposals SET decision = ?, resolved_at = ? WHERE id = ?",
        (decision, now, proposal_id),
    )
    if proposal.get("mission_id"):
        _audit(cur, proposal["mission_id"], actor, "action.resolved", {
            "proposal_id": proposal_id, "decision": decision, "note": note,
        })
    conn.commit()
    conn.close()
    return get_action_proposal(proposal_id, email)


def get_audit(mission_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    init_mission_control()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM mission_audit WHERE mission_id = ? ORDER BY created_at ASC LIMIT ?", (mission_id, limit))
    rows = cur.fetchall()
    conn.close()
    return [_row(row) for row in rows]


def mission_summary(email: str) -> Dict[str, Any]:
    missions = list_missions(email, limit=100)
    pending = list_pending_actions(email)
    return {
        "mission_count": len(missions),
        "active": sum(m["state"] in {"planning", "ready", "awaiting_approval", "approved", "executing", "paused", "blocked"} for m in missions),
        "awaiting_approval": sum(m["state"] == "awaiting_approval" for m in missions),
        "completed": sum(m["state"] == "completed" for m in missions),
        "failed": sum(m["state"] == "failed" for m in missions),
        "pending_actions": len(pending),
        "states": {state: sum(m["state"] == state for m in missions) for state in MISSION_STATES},
    }
