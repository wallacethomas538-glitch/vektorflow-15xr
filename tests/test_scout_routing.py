import sys
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import vektorflow_agents as va


def context():
    return va.AgentContext("test@example.com", {}, [], {}, {}, {}, params={})


def test_scout_store_counts_use_store_tools_only():
    asyncio.run(_test_scout_store_counts_use_store_tools_only())


async def _test_scout_store_counts_use_store_tools_only():
    scout = va.ScoutAgent()
    products = AsyncMock(return_value={"success": True, "count": 42})
    orders = AsyncMock(return_value={"success": True, "count": 7})
    scout.tool_handlers["get_shopify_products"] = products
    scout.tool_handlers["get_shopify_orders"] = orders
    instruction = "Report the live store product count and order count."

    async def llm(agent, prompt, *args, **kwargs):
        if "Return JSON ONLY" in prompt:
            return {"response": '{"tools":["get_shopify_products","get_shopify_orders"]}'}
        return {"response": '{"status":"completed","message":"Counts reported"}'}

    with patch.object(va, "agent_llm", side_effect=llm), patch.object(
        scout, "use_tool", wraps=scout.use_tool
    ) as use_tool:
        result = await scout.run(context(), instruction)

    assert isinstance(scout, va.RoleAgent)
    assert result["status"] == "completed"
    assert {call.args[0] for call in use_tool.call_args_list} == {
        "get_shopify_products", "get_shopify_orders"
    }
    assert "search_cj_products" not in result["tool_evidence"]


def test_scout_supplier_task_still_uses_cj_search():
    asyncio.run(_test_scout_supplier_task_still_uses_cj_search())


async def _test_scout_supplier_task_still_uses_cj_search():
    scout = va.ScoutAgent()
    search = AsyncMock(return_value={"success": True, "products": [{"id": "cj-1"}]})
    scout.tool_handlers["search_cj_products"] = search

    async def llm(agent, prompt, *args, **kwargs):
        if "Return JSON ONLY" in prompt:
            return {"response": '{"tools":["search_cj_products"]}'}
        return {"response": '{"status":"completed","message":"Supplier found"}'}

    with patch.object(va, "agent_llm", side_effect=llm):
        result = await scout.run(context(), "Find CJ supplier products for a phone stand")

    search.assert_awaited_once()
    assert result["tool_calls"] == [{"tool": "search_cj_products", "status": "completed"}]
