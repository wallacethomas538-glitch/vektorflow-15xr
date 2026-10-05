"""Background workflow run registry (kill-switch support).

Keeps a small in-memory registry of team workflow runs so a long-running
POST /api/agents/run can be polled and cancelled. Each run is an asyncio
Task; cancelling sets a per-run asyncio.Event (checked by the agent loop
between agents) and also cancels the task for immediacy when it is stuck
inside a long await.

This module has no app imports so it can be unit-tested standalone.
"""
import asyncio
import time
import uuid

MAX_RUNS = 50

_runs = {}


def new_run(goal):
    run_id = uuid.uuid4().hex[:12]
    _runs[run_id] = {
        "run_id": run_id,
        "goal": goal,
        "status": "starting",
        "started_at": time.time(),
        "completed_at": None,
        "task": None,
        "cancel_event": asyncio.Event(),
        "result": None,
        "error": None,
    }
    _prune()
    return _runs[run_id]


def get_run(run_id):
    return _runs.get(run_id)


def list_runs():
    return [public_view(r) for r in sorted(_runs.values(), key=lambda r: r["started_at"], reverse=True)]


def public_view(run):
    """JSON-safe view of a run (no task/event objects)."""
    return {
        "run_id": run["run_id"],
        "goal": run["goal"],
        "status": run["status"],
        "started_at": run["started_at"],
        "completed_at": run["completed_at"],
        "error": run["error"],
    }


def request_cancel(run_id):
    """Signal cancellation for a live run. Returns the run, or None if unknown/finished."""
    run = _runs.get(run_id)
    if not run or run["status"] not in ("starting", "running"):
        return None
    run["cancel_event"].set()
    task = run.get("task")
    if task is not None and not task.done():
        task.cancel()
    run["status"] = "cancelling"
    return run


def _prune():
    if len(_runs) <= MAX_RUNS:
        return
    victims = sorted(_runs.values(), key=lambda r: r["started_at"])[: len(_runs) - MAX_RUNS]
    for run in victims:
        if run["status"] not in ("starting", "running", "cancelling"):
            del _runs[run["run_id"]]
