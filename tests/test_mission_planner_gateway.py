import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mission_planner import build_mission_plan_async


def allowed(*args, **kwargs):
    return {"allowed": True, "decision": "allow"}


def denied(*args, **kwargs):
    return {"allowed": False, "decision": "reject", "reason": "Kill switch is on"}


def test_planner_llm_call_routes_through_authorized_gateway():
    provider = AsyncMock(return_value={
        "success": True,
        "response": '{"tasks": [{"agent": "Scout", "instruction": "find trends", "dependencies": [], "risk": "low"}]}'
    })
    with patch("llm_gateway.authorize_llm_request", side_effect=allowed), \
         patch("llm_gateway.call_llm", provider):
        plan = asyncio.run(build_mission_plan_async("find trends", {"llm_keys": {}}))
    assert plan["tasks"][0]["agent"] == "Scout"
    provider.assert_awaited_once()
    assert provider.await_args.args[1] == "openrouter/free"


def test_planner_denied_by_kill_switch_uses_safe_plan_without_provider_call():
    provider = AsyncMock()
    with patch("llm_gateway.authorize_llm_request", side_effect=denied), \
         patch("llm_gateway.call_llm", provider):
        plan = asyncio.run(build_mission_plan_async("find trends", {"llm_keys": {}}))
    assert plan == {
        "tasks": [{"agent": "Scout", "instruction": "find trends", "dependencies": [], "risk": "low"}]
    }
    provider.assert_not_awaited()
