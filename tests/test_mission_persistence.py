"""Tests for mission execution persistence — real per-task teamwork records.

The 15-agent team must genuinely execute task-by-task: each planned task row
moves pending -> running -> completed/failed, driven by its assigned agent in
planner dependency order, with the agent's real output persisted. The
mission-level result is synthesized from those real per-task records.

No mocks of the orchestrator: the execution-path test drives the REAL
orchestrator and a REAL agent through the REAL storage/transition functions,
and asserts the rows reflect the genuine outcome — including an honest
failure record when no LLM is configured (an agent that produces no usable
output must never be recorded as completed).
"""
import asyncio
import os
import sys
import tempfile
import unittest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.pop("DATABASE_URL", None)  # force the SQLite persistence path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import database
import mission_control as mc
import mission_control_api as mca
from mission_planner import build_mission_plan

TEST_EMAIL = "mission-test@vektorflow.com"


class MissionPersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        cls._tmp_path = tmp.name
        cls._old_db_path = database.DB_PATH
        database.DB_PATH = cls._tmp_path
        database.init_db()

    @classmethod
    def tearDownClass(cls):
        database.DB_PATH = cls._old_db_path
        try:
            os.unlink(cls._tmp_path)
        except OSError:
            pass

    def _new_mission(self, objective="persistence test mission"):
        return mc.create_mission(email=TEST_EMAIL, objective=objective)

    # ---- schema migration ----

    def test_result_column_migration_is_idempotent(self):
        mc.init_mission_control()
        mc.init_mission_control()  # second run must not raise
        mission = self._new_mission()
        self.assertIn("result", mission)
        self.assertEqual(mission["result"], {})

    # ---- task state machine ----

    def test_task_lifecycle_pending_running_completed(self):
        mission = self._new_mission()
        task = mc.add_task(mission["id"], "Scout", "find winning niches", [], "low")
        self.assertEqual(task["status"], "pending")

        task = mc.transition_task(task["id"], "running", actor="mission-control")
        self.assertEqual(task["status"], "running")

        payload = {
            "agent": "Scout",
            "outcome": {
                "agent": "Scout",
                "status": "completed",
                "message": "found 3 niches with rising demand",
                "evidence": "trend data summarized",
            },
        }
        task = mc.transition_task(task["id"], "completed", actor="mission-control", result=payload)
        self.assertEqual(task["status"], "completed")
        # The real agent output round-trips through storage.
        self.assertEqual(task["result"]["outcome"]["message"], "found 3 niches with rising demand")

    def test_task_failed_records_honest_error(self):
        mission = self._new_mission()
        task = mc.add_task(mission["id"], "Smaug", "price the bundle", [], "low")
        mc.transition_task(task["id"], "running", actor="mission-control")
        task = mc.transition_task(
            task["id"], "failed", actor="mission-control",
            result={"agent": "Smaug", "error": "No API key for openrouter. Add it in Settings."},
        )
        self.assertEqual(task["status"], "failed")
        self.assertIn("No API key", task["result"]["error"])

    def test_task_invalid_transition_rejected(self):
        mission = self._new_mission()
        task = mc.add_task(mission["id"], "Scout", "find niches", [], "low")
        with self.assertRaises(ValueError):
            mc.transition_task(task["id"], "completed", actor="mission-control")
        with self.assertRaises(ValueError):
            mc.transition_task(task["id"], "bogus-state", actor="mission-control")

    def test_task_audit_trail_records_transitions(self):
        mission = self._new_mission()
        task = mc.add_task(mission["id"], "Scout", "find niches", [], "low")
        mc.transition_task(task["id"], "running", actor="mission-control")
        mc.transition_task(task["id"], "completed", actor="mission-control", result={"agent": "Scout"})
        events = [a["event_type"] for a in mc.get_audit(mission["id"])]
        self.assertIn("task.transitioned", events)

    # ---- dependency ordering ----

    def test_dependency_order_respects_planner_dag(self):
        tasks = [
            {"id": "t3", "dependencies": ["t1", "t2"]},
            {"id": "t1", "dependencies": []},
            {"id": "t2", "dependencies": ["t1"]},
        ]
        ordered = mca._dependency_order(tasks)
        ids = [t["id"] for t in ordered]
        self.assertLess(ids.index("t1"), ids.index("t2"))
        self.assertLess(ids.index("t1"), ids.index("t3"))
        self.assertLess(ids.index("t2"), ids.index("t3"))

    def test_dependency_order_survives_cycle_without_deadlock(self):
        tasks = [
            {"id": "a", "dependencies": ["b"]},
            {"id": "b", "dependencies": ["a"]},
        ]
        ordered = mca._dependency_order(tasks)
        self.assertEqual({t["id"] for t in ordered}, {"a", "b"})

    def test_planner_task_ids_translate_to_real_task_ids(self):
        mission = self._new_mission()
        plan = build_mission_plan(mission["objective"], {})
        tasks = mca._create_plan_tasks(mission["id"], plan)
        self.assertEqual(len(tasks), 15)
        by_id = {t["id"] for t in tasks}
        for task in tasks:
            for dep in task.get("dependencies") or []:
                self.assertIn(dep, by_id)
        # Phase-0 tasks (Scout/ViralDet/Shadow) have no dependencies.
        phase0 = [t for t in tasks if t["agent"] in {"Scout", "ViralDet", "Shadow"}]
        self.assertTrue(all(not t.get("dependencies") for t in phase0))

    # ---- agent-output honesty guard ----

    def test_agent_work_guard_rejects_empty_output(self):
        ok, reason = mca._agent_work_succeeded({"agent": "X", "status": "completed", "message": ""})
        self.assertFalse(ok)
        self.assertIn("no message", reason)

    def test_agent_work_guard_rejects_placeholder_response(self):
        ok, reason = mca._agent_work_succeeded({
            "agent": "X",
            "status": "completed",
            "message": "I am ready to help, but I do not have enough information to answer that yet.",
        })
        self.assertFalse(ok)
        self.assertIn("placeholder", reason)

    def test_agent_work_guard_rejects_failed_and_blocked(self):
        ok, _ = mca._agent_work_succeeded({"agent": "X", "status": "failed", "error": "boom"})
        self.assertFalse(ok)
        ok, reason = mca._agent_work_succeeded({"agent": "X", "status": "blocked"})
        self.assertFalse(ok)
        self.assertIn("blocked", reason)

    def test_agent_work_guard_accepts_real_evidence(self):
        ok, _ = mca._agent_work_succeeded({
            "agent": "Scout", "status": "completed",
            "message": "found 3 niches", "evidence": "trend snapshot",
        })
        self.assertTrue(ok)
        ok, _ = mca._agent_work_succeeded({
            "agent": "Scout", "status": "completed",
            "type": "products", "data": [{"title": "widget"}],
        })
        self.assertTrue(ok)

    def test_agent_work_guard_rejects_context_read_only(self):
        # Re-reading shared team context is not doing the work.
        ok, reason = mca._agent_work_succeeded({
            "agent": "Architect", "status": "completed", "message": "",
            "actions": [], "handoff": "", "evidence": "",
            "tool_calls": [{"tool": "read_team_results", "status": "completed"}],
            "tool_evidence": {"read_team_results": {"scout": {"message": "x"}}},
        })
        self.assertFalse(ok)
        self.assertIn("no message", reason)

    def test_agent_work_guard_accepts_completed_real_tool(self):
        ok, _ = mca._agent_work_succeeded({
            "agent": "Rook", "status": "completed", "message": "",
            "tool_calls": [
                {"tool": "read_team_results", "status": "completed"},
                {"tool": "get_shopify_products", "status": "completed"},
            ],
        })
        self.assertTrue(ok)

    # ---- mission-level result synthesized from real task records ----

    def test_mission_result_persisted_from_real_task_records(self):
        mission = self._new_mission("persist path end-to-end")
        for state in ("planning", "ready", "approved", "executing"):
            mc.transition_mission(mission["id"], state, "test", TEST_EMAIL)
        plan = build_mission_plan(mission["objective"], {})
        tasks = mca._create_plan_tasks(mission["id"], plan)
        # This is exactly the persist path _run_mission_team uses after each
        # real agent run: transition the row, store the real output.
        for task in tasks:
            mc.transition_task(task["id"], "running", actor="mission-control")
            mc.transition_task(
                task["id"], "completed", actor="mission-control",
                result={"agent": task["agent"],
                        "outcome": {"agent": task["agent"], "status": "completed",
                                    "message": f"{task['agent']} did its part"}})
        mc.set_mission_result(mission["id"], {
            "status": "completed", "goal": mission["objective"],
            "task_count": len(tasks), "completed_count": len(tasks), "failed_count": 0,
        })
        mc.transition_mission(mission["id"], "completed", "mission-control", TEST_EMAIL)

        got = mc.get_mission(mission["id"], TEST_EMAIL)
        self.assertEqual(got["state"], "completed")
        self.assertEqual(got["result"]["status"], "completed")
        self.assertEqual(got["result"]["task_count"], 15)
        rows = mc.list_tasks(mission["id"])
        self.assertEqual(len(rows), 15)
        self.assertTrue(all(r["status"] == "completed" for r in rows))
        self.assertTrue(all((r["result"] or {}).get("outcome", {}).get("message") for r in rows))

    def test_unknown_agent_task_records_honest_failure(self):
        """The real per-task runner, real orchestrator, unknown agent name."""
        from vektorflow_agents import AgentContext, get_orchestrator

        mission = self._new_mission("unknown agent probe")
        task = mc.add_task(mission["id"], "Nobody", "do impossible things", [], "low")
        context = AgentContext(email=TEST_EMAIL, user={}, stores=[], llm_keys={},
                               icp={}, memory={}, params={"mission_id": mission["id"]})
        asyncio.run(mca._execute_mission_task(
            get_orchestrator(), context, mission["id"], mission["objective"], task, {}))
        row = mc.get_task(task["id"])
        self.assertEqual(row["status"], "failed")
        self.assertIn("not on the 15-agent roster", row["result"]["error"])

    def test_run_mission_team_real_orchestrator_honest_outcome(self):
        """End-to-end through the REAL _run_mission_team with the REAL orchestrator.

        No LLM keys exist in this environment, so the real Cerebrum agent
        cannot produce usable output. The mission must land failed with the
        honest reason on both the task row and the mission record — it must
        NEVER be recorded as completed.
        """
        mission = self._new_mission("honest failure probe")
        for state in ("planning", "ready", "approved", "executing"):
            mc.transition_mission(mission["id"], state, "test", TEST_EMAIL)
        mc.add_task(mission["id"], "Cerebrum", "summarize team state", [], "low")

        result = asyncio.run(mca._run_mission_team(mission["id"], TEST_EMAIL))

        rows = mc.list_tasks(mission["id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "failed")
        self.assertIn("error", rows[0]["result"] or {})

        got = mc.get_mission(mission["id"], TEST_EMAIL)
        self.assertEqual(got["state"], "failed")
        self.assertEqual(got["result"]["status"], "failed")
        self.assertEqual(got["result"]["failed_count"], 1)
        self.assertEqual(got["result"]["task_count"], 1)
        self.assertEqual(len(got["result"]["failed_tasks"]), 1)
        self.assertEqual(got["result"]["failed_tasks"][0]["agent"], "Cerebrum")
        # The returned result matches what was persisted.
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["failed_count"], 1)


if __name__ == "__main__":
    unittest.main()
