import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(tempfile.mkdtemp(prefix="vektorflow-tests-"))

import store_ops
import vektorflow_agents as va
from kill_switch import KillSwitch, get_kill_switch
from policy_engine import authorize_tool
from execution_gateway import _risk_for


def make_context(params=None, results=None):
    return va.AgentContext(
        email="commander@example.com",
        user={},
        stores=[],
        llm_keys={},
        icp={},
        memory={},
        params=params or {},
        results=results or {},
    )


class StoreOpsMappingTests(unittest.TestCase):
    def test_map_complete_cj_product_is_ready(self):
        mapped = store_ops.map_cj_product_to_shopify({
            "pid": "CJ-123",
            "productNameEn": "Mini Car Vacuum",
            "description": "Strong suction for car interiors.",
            "images": ["https://example.com/vacuum.jpg"],
            "sellPrice": "12.50",
            "supplierName": "CJ Supplier",
        })
        self.assertEqual(mapped["source_product_id"], "CJ-123")
        self.assertEqual(mapped["needs_review"], [])
        self.assertTrue(mapped["ready_to_publish"])
        self.assertEqual(mapped["product"]["status"], "draft")
        self.assertEqual(mapped["product"]["variants"][0]["price"], "12.50")
        self.assertIn("cj-pid:CJ-123", mapped["product"]["tags"])

    def test_map_missing_evidence_is_flagged_not_invented(self):
        mapped = store_ops.map_cj_product_to_shopify({"pid": "CJ-404", "productNameEn": "Mystery Item"})
        self.assertIn("missing_description", mapped["needs_review"])
        self.assertIn("missing_images", mapped["needs_review"])
        self.assertIn("missing_price", mapped["needs_review"])
        self.assertFalse(mapped["ready_to_publish"])
        self.assertEqual(mapped["product"]["variants"][0]["price"], "0.00")

    def test_map_variants_and_markup(self):
        mapped = store_ops.map_cj_product_to_shopify({
            "pid": "CJ-9",
            "productNameEn": "Towel Set",
            "description": "Microfiber towels.",
            "images": ["https://example.com/towel.jpg"],
            "variants": [
                {"variantNameEn": "Small", "variantSku": "TW-S", "sellPrice": "5"},
                {"variantNameEn": "Large", "variantSku": "TW-L", "sellPrice": "8"},
            ],
        }, markup_percent=100)
        prices = [v["price"] for v in mapped["product"]["variants"]]
        self.assertEqual(prices, ["10.00", "16.00"])
        self.assertTrue(mapped["ready_to_publish"])


class StoreOpsWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_watch_new_orders_baseline_then_new_order(self):
        memory = {}
        original_call = store_ops._shopify_call
        original_get = store_ops.get_memory
        original_save = store_ops.save_memory
        orders = {"orders": []}
        async def fake_call(email, method, **kwargs):
            self.assertEqual(method, "get_orders")
            return {"success": True, "orders": orders["orders"]}
        store_ops._shopify_call = fake_call
        store_ops.get_memory = lambda email, key: memory.get(key)
        store_ops.save_memory = lambda email, key, value: memory.__setitem__(key, value)
        store_ops._SEEN_ORDERS_FALLBACK.clear()
        try:
            ctx = make_context()
            orders["orders"] = [{"id": 1, "order_number": 1001, "line_items": []}]
            first = await store_ops.watch_new_orders(ctx)
            self.assertTrue(first["baseline_established"])
            self.assertEqual(first["new_orders"], [])

            orders["orders"] = [
                {"id": 1, "order_number": 1001, "line_items": []},
                {"id": 2, "order_number": 1002, "email": "buyer@example.com", "line_items": [{"title": "Vacuum", "quantity": 1}]},
            ]
            second = await store_ops.watch_new_orders(ctx)
            self.assertFalse(second["baseline_established"])
            self.assertEqual(second["count"], 1)
            self.assertEqual(second["new_orders"][0]["order_number"], 1002)
        finally:
            store_ops._shopify_call = original_call
            store_ops.get_memory = original_get
            store_ops.save_memory = original_save
            store_ops._SEEN_ORDERS_FALLBACK.clear()

    async def test_import_supplier_product_creates_shopify_draft(self):
        original_details = store_ops.get_cj_product_details
        original_store = store_ops.get_connected_shopify_store
        original_api = store_ops.ShopifyAPI

        async def fake_details(product_id):
            self.assertEqual(product_id, "CJ-123")
            return {
                "pid": "CJ-123",
                "productNameEn": "Mini Car Vacuum",
                "description": "Strong suction for car interiors.",
                "images": ["https://example.com/vacuum.jpg"],
                "sellPrice": "12.50",
            }

        class FakeClient:
            async def aclose(self):
                pass

        class FakeShopifyAPI:
            def __init__(self, store_url, access_token):
                self.store_url = store_url
                self.access_token = access_token
                self.client = FakeClient()
                self.created = None

            async def create_product(self, product):
                self.created = product
                return {"success": True, "product": {"id": 987, "title": product["title"]}}

        store_ops.get_cj_product_details = fake_details
        store_ops.get_connected_shopify_store = lambda email: {"store_url": "https://example.myshopify.com", "access_token": "token"}
        store_ops.ShopifyAPI = FakeShopifyAPI
        try:
            result = await store_ops.import_supplier_product(make_context(), product_id="CJ-123")
        finally:
            store_ops.get_cj_product_details = original_details
            store_ops.get_connected_shopify_store = original_store
            store_ops.ShopifyAPI = original_api

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "draft")
        self.assertEqual(result["shopify_product_id"], 987)
        self.assertEqual(result["source_product_id"], "CJ-123")
        self.assertTrue(result["ready_to_publish"])

    async def test_watch_abandoned_carts_drafts_only_no_discount(self):
        original_call = store_ops._shopify_call
        async def fake_call(email, method, **kwargs):
            self.assertEqual(method, "get_abandoned_checkouts")
            return {"success": True, "checkouts": [{
                "id": "chk_1", "email": "shopper@example.com", "total_price": "49.99",
                "created_at": "2026-10-08T00:00:00Z",
                "line_items": [{"title": "Dog Toy", "quantity": 1}],
            }]}
        store_ops._shopify_call = fake_call
        try:
            result = await store_ops.watch_abandoned_carts(make_context())
        finally:
            store_ops._shopify_call = original_call
        self.assertEqual(result["count"], 1)
        cart = result["carts"][0]
        self.assertEqual(cart["send_status"], "not_sent")
        self.assertTrue(cart["requires_approval"])
        self.assertIn("No discount is offered", cart["policy"])
        self.assertIn("Dog Toy", str(cart["items"]))

    def test_email_refund_case_escalates_and_does_not_send(self):
        self.assertEqual(store_ops.classify_customer_message("Refund please", "I want my money back")["priority"], "high")
        result = store_ops.handle_email_notification(
            make_context(),
            from_email="buyer@example.com",
            subject="Refund please",
            body="The item arrived and I want a refund.",
            customer_name="Sam",
            order_number="#1002",
        )
        self.assertTrue(result["escalate_to_wallace"])
        self.assertEqual(result["send_status"], "not_sent")
        self.assertTrue(result["requires_approval"])
        self.assertIn("Wallace will review", result["draft_reply"])

    def test_draft_customer_reply_is_never_marked_sent(self):
        draft = store_ops.draft_customer_reply(make_context(), customer_name="Ana", topic="your order", order_number="#1003")
        self.assertEqual(draft["send_status"], "not_sent")
        self.assertTrue(draft["requires_approval"])
        self.assertIn("Hi Ana", draft["draft"])


class KillSwitchTests(unittest.TestCase):
    def test_per_agent_and_global_kill_switch(self):
        ks = KillSwitch()
        self.assertFalse(ks.is_killed("Echo"))
        ks.kill("Echo")
        self.assertTrue(ks.is_killed("Echo"))
        self.assertFalse(ks.is_killed("Rook"))
        ks.kill_all()
        self.assertTrue(ks.is_killed("Rook"))
        ks.revive_all()
        ks.revive("Echo")
        self.assertFalse(ks.is_killed("Echo"))


class AgentToolGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_role_agent_gathers_tool_evidence_before_llm(self):
        async def fake_orders(context, limit=50):
            return {"success": True, "orders": [{"id": 7, "order_number": 1007}]}
        async def fake_watch(context, limit=50, alert_existing=False):
            return {"success": True, "new_orders": [{"id": 7}], "count": 1}
        agent = va.RoleAgent(
            "Echo", "Customer communications",
            va._tools("get_shopify_orders", "watch_new_orders"),
            {"get_shopify_orders": fake_orders, "watch_new_orders": fake_watch},
        )
        async def fake_llm(context, instruction):
            self.assertIn("watch_new_orders", context.params.get("tool_evidence", {}))
            return {"status": "completed", "message": "I see the new order evidence.", "actions": [], "handoff": "", "evidence": ""}
        agent._llm_structured = fake_llm
        result = await agent._execute(make_context(), "A new order came in - check orders")
        self.assertEqual(result["tool_evidence"]["watch_new_orders"]["count"], 1)
        self.assertIn("get_shopify_orders", result["tool_evidence"])
        self.assertTrue(any(call["tool"] == "watch_new_orders" for call in result["tool_calls"]))

    async def test_import_tool_is_blocked_without_approval(self):
        calls = []
        async def fake_import(context, **kwargs):
            calls.append(kwargs)
            return {"success": True}
        agent = va.RoleAgent(
            "Rook", "Store operations",
            va._tools("import_supplier_product"),
            {"import_supplier_product": fake_import},
        )
        blocked = await agent.use_tool("import_supplier_product", make_context(), product_id="CJ-1")
        self.assertTrue(blocked["blocked"])
        self.assertEqual(blocked["status"], "awaiting_approval")
        self.assertEqual(calls, [])

        approved = await agent.use_tool(
            "import_supplier_product",
            make_context(params={"approval_granted": True}),
            product_id="CJ-1",
        )
        self.assertTrue(approved["success"])
        self.assertEqual(len(calls), 1)

    async def test_agent_run_stops_when_killed(self):
        ks = get_kill_switch()
        agent = va.RoleAgent("Echo", "Customer communications", va._tools("read_team_results"), {"read_team_results": va._read_team_results})
        ks.kill("Echo")
        try:
            result = await agent.run(make_context(), "check the inbox")
        finally:
            ks.revive("Echo")
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["blocked"])


class PolicyAndRosterTests(unittest.TestCase):
    def test_roster_has_role_specific_store_tools_and_playbooks(self):
        roster = {a["name"]: a for a in va.get_orchestrator().roster()}
        self.assertEqual(len(roster), 15)
        self.assertIn("import_supplier_product", roster["Rook"]["tools"])
        self.assertIn("handle_email_notification", roster["Echo"]["tools"])
        self.assertIn("watch_new_orders", roster["Sentinel"]["tools"])
        self.assertIn("watch_abandoned_carts", roster["Sentinel"]["tools"])
        self.assertIn("generate_organic_ad", roster["DaVinci"]["tools"])
        self.assertIn("abandoned_cart", roster["Sentinel"]["playbook_sections"])
        self.assertIn("service", roster["Echo"]["playbook_sections"])
        playbook = store_ops.get_agent_playbook("echo")
        self.assertIn("Financial decisions belong to Wallace", playbook)
        self.assertIn("do not invent one", playbook)

    def test_policy_engine_gates(self):
        self.assertEqual(authorize_tool("Rook", "import_supplier_product")["decision"], "ask")
        self.assertEqual(authorize_tool("Echo", "send_email")["decision"], "reject")
        self.assertTrue(authorize_tool("Echo", "draft_customer_reply")["allowed"])
        self.assertEqual(authorize_tool("Echo", "host_shell")["decision"], "reject")

    def test_gateway_risk_classes(self):
        self.assertEqual(_risk_for("get_shopify_products", None), "low")
        self.assertEqual(_risk_for("watch_abandoned_carts", None), "low")
        self.assertEqual(_risk_for("draft_customer_reply", None), "low")
        self.assertEqual(_risk_for("generate_organic_ad", None), "medium")
        self.assertEqual(_risk_for("import_supplier_product", None), "high")
        self.assertEqual(_risk_for("unknown_tool", None), "high")


if __name__ == "__main__":
    unittest.main()
