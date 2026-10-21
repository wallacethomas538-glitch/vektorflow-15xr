"""The agent layer reaches the provider only through the authorized gateway.

Covers:
  * every agent LLM call is authorized under that agent's OWN name,
  * the kill switch ON for that agent denies the request at the gateway and
    the provider is never called — the agent reports the block instead of
    inventing work,
  * with the kill switch OFF the very same call goes through to the provider,
  * a caller-supplied temperature is forwarded to the provider, not dropped,
  * the retired plan-and-execute alias is gone and ``run_agent_task``
    routes through the unified team path.

Run:
    pytest tests/test_agent_llm_gateway.py -v
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import vektorflow_agents as va
from kill_switch import get_kill_switch

AGENT = "Echo"
# Built at runtime so this file never contains the retired name literally and
# can therefore scan the whole repository for it.
RETIRED_NAME = "plan" + "_and_execute"


def _context(params=None, results=None):
    return va.AgentContext(
        email="agent-gateway-test@vektorflow.com",
        user={},
        stores=[],
        llm_keys={},
        icp={},
        memory={},
        params=params or {},
        results=results or {},
    )


def _agent(name=AGENT):
    return va.RoleAgent(name, "Customer communications", va._tools(), {})


def _allowed(*args, **kwargs):
    return {"allowed": True, "decision": "allow", "reason": "ok"}


# --- authorization identity -------------------------------------------

def test_agent_llm_request_is_authorized_under_the_agents_own_name():
    provider = AsyncMock(return_value={"success": True, "response": "I checked the inbox."})
    with patch("llm_gateway.authorize_llm_request", side_effect=_allowed) as authorizer, \
         patch("llm_gateway.call_llm", provider):
        message = asyncio.run(_agent()._llm_role(_context(), "check the inbox"))
    assert message == "I checked the inbox."
    assert authorizer.call_args.args[0] == AGENT
    provider.assert_awaited_once()


def test_structured_agent_llm_request_is_authorized_under_the_agents_own_name():
    provider = AsyncMock(return_value={
        "success": True,
        "response": '{"status":"completed","message":"Two replies drafted.","actions":[],"handoff":"","evidence":""}',
    })
    with patch("llm_gateway.authorize_llm_request", side_effect=_allowed) as authorizer, \
         patch("llm_gateway.call_llm", provider):
        result = asyncio.run(_agent()._llm_structured(_context(), "draft replies"))
    assert authorizer.call_args.args[0] == AGENT
    assert result["message"] == "Two replies drafted."
    provider.assert_awaited_once()


# --- kill switch ON: denied, provider untouched -----------------------

def test_kill_switch_on_denies_the_agent_llm_call_without_calling_the_provider():
    provider = AsyncMock()
    switch = get_kill_switch()
    switch.kill(AGENT)
    try:
        with patch("llm_gateway.call_llm", provider):
            message = asyncio.run(_agent()._llm_role(_context(), "check the inbox"))
            structured = asyncio.run(_agent()._llm_structured(_context(), "check the inbox"))
    finally:
        switch.revive(AGENT)
    provider.assert_not_awaited()
    assert "Blocked by policy" in message
    assert "Kill switch" in message
    assert structured["status"] == "blocked"
    assert structured["blocked"] is True
    assert structured["actions"] == []
    assert not structured["evidence"]


def test_kill_switch_on_does_not_leak_fake_work_into_the_agent_result():
    provider = AsyncMock()
    switch = get_kill_switch()
    switch.kill(AGENT)
    try:
        with patch("llm_gateway.call_llm", provider):
            result = asyncio.run(_agent()._execute(_context(), "check the inbox"))
    finally:
        switch.revive(AGENT)
    provider.assert_not_awaited()
    assert result["status"] == "blocked"
    assert result["blocked"] is True
    assert result["error"]
    assert "Blocked by policy" in result["message"]


# --- kill switch OFF: the same call goes through ----------------------

def test_kill_switch_off_allows_the_agent_llm_call_through_the_gateway():
    provider = AsyncMock(return_value={"success": True, "response": "Order #7 shipped."})
    switch = get_kill_switch()
    switch.revive(AGENT)
    with patch.dict(os.environ, {"VF_ALLOWED_MODELS": ""}), \
         patch("llm_gateway.call_llm", provider):
        message = asyncio.run(_agent()._llm_role(_context(), "check orders"))
    assert message == "Order #7 shipped."
    provider.assert_awaited_once()


def test_kill_switch_off_allows_the_structured_agent_llm_call():
    provider = AsyncMock(return_value={
        "success": True,
        "response": '{"status":"completed","message":"Three carts found.","actions":[],"handoff":"","evidence":"carts"}',
    })
    switch = get_kill_switch()
    switch.revive(AGENT)
    with patch.dict(os.environ, {"VF_ALLOWED_MODELS": ""}), \
         patch("llm_gateway.call_llm", provider):
        result = asyncio.run(_agent()._llm_structured(_context(), "check carts"))
    assert result["status"] == "completed"
    assert result["message"] == "Three carts found."
    provider.assert_awaited_once()


# --- temperature is forwarded, never dropped --------------------------

def test_requested_temperature_is_forwarded_to_the_provider():
    provider = AsyncMock(return_value={"success": True, "response": "ok"})
    with patch("llm_gateway.authorize_llm_request", side_effect=_allowed), \
         patch("llm_gateway.call_llm", provider):
        asyncio.run(_agent()._llm_role(_context({"temperature": 0.25}), "hi"))
    assert provider.await_args.args[3] == 0.25


def test_missing_temperature_is_forwarded_as_none():
    provider = AsyncMock(return_value={"success": True, "response": "ok"})
    with patch("llm_gateway.authorize_llm_request", side_effect=_allowed), \
         patch("llm_gateway.call_llm", provider):
        asyncio.run(_agent()._llm_role(_context(), "hi"))
    assert provider.await_args.args[3] is None


# --- the retired alias is gone, the unified path is used ---------------

def test_retired_alias_no_longer_exists_on_the_orchestrator():
    orchestrator = va.get_orchestrator()
    assert not hasattr(orchestrator, RETIRED_NAME)
    assert not hasattr(va.Orchestrator, RETIRED_NAME)


def test_retired_alias_has_no_definitions_or_callers_left_in_the_repository():
    offenders = []
    for path in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if RETIRED_NAME in path.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_team_execute_is_the_unified_path_behind_run_agent_task():
    runner = AsyncMock(return_value={"status": "completed", "results": {}})
    with patch.object(va.Orchestrator, "_run_mission_team", new=runner):
        asyncio.run(va.get_orchestrator().team_execute("grow the store", _context()))
    runner.assert_awaited_once()


def test_run_agent_task_routes_orchestrator_requests_through_the_unified_path():
    team_execute = AsyncMock(return_value={"status": "completed", "results": {}})
    stub = SimpleNamespace(team_execute=team_execute, get_agent=lambda name: None)
    with patch.object(va, "_orchestrator", stub), \
         patch("vektorflow_agents.get_user", return_value=None), \
         patch("vektorflow_agents.get_user_stores", return_value=[]), \
         patch("vektorflow_agents.get_llm_keys", return_value={}), \
         patch("vektorflow_agents.get_icp_data", return_value={}), \
         patch("vektorflow_agents.get_all_memory", return_value={}):
        result = asyncio.run(va.run_agent_task("nobody@vektorflow.com", "orchestrator", "grow the store"))
    assert result == {"status": "completed", "results": {}}
    team_execute.assert_awaited_once()
    assert team_execute.await_args.args[0] == "grow the store"


def test_run_agent_task_falls_back_to_the_unified_path_for_unknown_agents():
    team_execute = AsyncMock(return_value={"status": "completed", "results": {}})
    stub = SimpleNamespace(team_execute=team_execute, get_agent=lambda name: None)
    with patch.object(va, "_orchestrator", stub), \
         patch("vektorflow_agents.get_user", return_value=None), \
         patch("vektorflow_agents.get_user_stores", return_value=[]), \
         patch("vektorflow_agents.get_llm_keys", return_value={}), \
         patch("vektorflow_agents.get_icp_data", return_value={}), \
         patch("vektorflow_agents.get_all_memory", return_value={}):
        asyncio.run(va.run_agent_task("nobody@vektorflow.com", "Nobody", "grow the store"))
    team_execute.assert_awaited_once()
    assert team_execute.await_args.args[0] == "grow the store"
