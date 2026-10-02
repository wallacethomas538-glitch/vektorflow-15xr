"""VektorFlow execution gateway.

Borrowed from OpenClaw's control-plane pattern: one long-lived gateway boundary
for agent/tool requests, approval-aware execution, and server-push events.
VektorFlow keeps its own agents, policies, memory, and security controls.
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, Dict, Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel, Field

from vektorflow_agents import AgentContext, get_orchestrator
from database import get_user, get_user_stores, get_llm_keys, get_icp_data, get_all_memory
from mission_control import propose_action, get_action_proposal
from src.event_bus import get_event_bus

router = APIRouter(prefix="/api/v1/gateway", tags=["execution-gateway"])
ws_clients: Set[WebSocket] = set()
_gateway_subscriptions: Set[str] = set()
_started = False

READ_ONLY_TOOLS = {
    "read_team_results", "check_inventory", "get_inventory_alerts", "get_stores",
    "system_health", "agent_roster", "read_memory", "search_cj_products",
    "get_tiktok_trends", "get_google_trends", "brave_search", "tavily_search",
    "seo_research", "webscraping_ai",
}
MUTATING_TOOLS = {
    "generate_seo", "generate_content", "generate_campaign", "generate_outreach",
    "apify_actor",
}


class GatewayInvoke(BaseModel):
    agent: str
    tool: str
    email: str = "commander@vektorflow.com"
    mission_id: str | None = None
    task_id: str | None = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    risk: str | None = None
    reason: str = "Gateway tool request"


def _risk_for(tool: str, requested: str | None) -> str:
    if requested:
        value = requested.lower()
        if value in {"low", "medium", "high", "critical"}:
            return value
    if tool in READ_ONLY_TOOLS:
        return "low"
    if tool in MUTATING_TOOLS:
        return "medium"
    return "high"


async def _broadcast(event: Dict[str, Any]) -> None:
    stale = []
    message = json.dumps({"type": "event", "event": event["type"], "payload": event})
    for ws in list(ws_clients):
        try:
            await ws.send_text(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        ws_clients.discard(ws)


def _wire_event_bus() -> None:
    global _started
    if _started:
        return
    bus = get_event_bus()
    for event_type in (
        "agent.run.started", "agent.run.completed", "agent.run.failed",
        "agent.message.created", "action.proposed", "action.resolved",
        "mission.transitioned", "task.created",
    ):
        bus.subscribe(event_type, _broadcast)
        _gateway_subscriptions.add(event_type)
    _started = True


@router.on_event("startup")
async def gateway_startup():
    _wire_event_bus()


@router.get("/status")
async def gateway_status():
    _wire_event_bus()
    return {
        "status": "ready",
        "transport": ["http", "websocket"],
        "websocket_path": "/ws/gateway",
        "protocol": "vektorflow-gateway-v1",
        "openclaw_compatibility": {
            "pattern": "single_control_plane_gateway",
            "request_frame": {"type": "req", "id": "request-id", "method": "tool.invoke", "params": {}},
            "event_frame": {"type": "event", "event": "agent.run.started", "payload": {}},
        },
        "security": {
            "tool_boundary": True,
            "approval_boundary": True,
            "sandbox_boundary": True,
            "default_fail_closed_unknown_tools": True,
        },
        "subscriptions": sorted(_gateway_subscriptions),
        "connected_clients": len(ws_clients),
    }


@router.get("/events")
async def gateway_events(limit: int = 50):
    _wire_event_bus()
    return {"events": get_event_bus().get_history(min(max(limit, 1), 200))}


@router.post("/tools/invoke")
async def gateway_invoke(request: GatewayInvoke):
    _wire_event_bus()
    orchestrator = get_orchestrator()
    agent = orchestrator.get_agent(request.agent)
    if not agent:
        raise HTTPException(404, f"Agent '{request.agent}' not found")
    if request.tool not in {t.get("name") for t in agent.tools}:
        raise HTTPException(403, f"Tool '{request.tool}' is not assigned to {request.agent}")

    risk = _risk_for(request.tool, request.risk)
    proposal = propose_action(
        email=request.email,
        agent=agent.name,
        action=f"tool:{request.tool}",
        risk=risk,
        mission_id=request.mission_id,
        task_id=request.task_id,
        payload={"arguments": request.arguments},
        reason=request.reason,
    )

    if proposal["decision"] == "pending":
        return {
            "status": "awaiting_approval",
            "request_id": "req_" + uuid.uuid4().hex,
            "proposal": proposal,
        }
    if proposal["decision"] != "approved":
        return {
            "status": "blocked",
            "request_id": "req_" + uuid.uuid4().hex,
            "proposal": proposal,
        }

    context = AgentContext(
        email=request.email,
        user=get_user(request.email) or {},
        stores=get_user_stores(request.email) or [],
        llm_keys=get_llm_keys(request.email) or {},
        icp=get_icp_data(request.email) or {},
        memory=get_all_memory(request.email) or {},
        params={
            "mission_id": request.mission_id,
            "task_id": request.task_id,
            "gateway_request_id": "req_" + uuid.uuid4().hex,
            "agent_name": agent.name,
        },
    )
    try:
        result = await agent.use_tool(request.tool, context, **request.arguments)
        return {"status": "completed", "agent": agent.name, "tool": request.tool, "result": result, "proposal": proposal}
    except Exception as exc:
        return {"status": "failed", "agent": agent.name, "tool": request.tool, "error": str(exc), "proposal": proposal}


@router.websocket("/ws")
async def gateway_websocket(websocket: WebSocket):
    _wire_event_bus()
    await websocket.accept()
    ws_clients.add(websocket)
    client_id = "gw_" + uuid.uuid4().hex
    try:
        await websocket.send_json({
            "type": "res",
            "id": "connect",
            "ok": True,
            "payload": {
                "protocol": "vektorflow-gateway-v1",
                "client_id": client_id,
                "methods": ["health", "status", "events", "tool.invoke", "approvals"],
                "events": sorted(_gateway_subscriptions),
            },
        })
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "res", "id": "invalid", "ok": False, "error": "Invalid JSON"})
                continue
            request_id = frame.get("id", "unknown")
            method = frame.get("method")
            params = frame.get("params") or {}
            if method in {"health", "status"}:
                payload = await gateway_status()
                await websocket.send_json({"type": "res", "id": request_id, "ok": True, "payload": payload})
            elif method == "events":
                payload = await gateway_events(int(params.get("limit", 50)))
                await websocket.send_json({"type": "res", "id": request_id, "ok": True, "payload": payload})
            elif method == "tool.invoke":
                try:
                    payload = await gateway_invoke(GatewayInvoke(**params))
                    await websocket.send_json({"type": "res", "id": request_id, "ok": True, "payload": payload})
                except HTTPException as exc:
                    await websocket.send_json({"type": "res", "id": request_id, "ok": False, "error": exc.detail})
            else:
                await websocket.send_json({"type": "res", "id": request_id, "ok": False, "error": f"Unknown method: {method}"})
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)
