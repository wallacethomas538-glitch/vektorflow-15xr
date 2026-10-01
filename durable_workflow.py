"""VektorFlow durable workflow state primitives.

Borrowed/adapted from Temporal concepts: workflow identity, event history,
signals, cancellation, checkpoints, and resumable execution. Persistence is
intentionally injected so VektorFlow can use its existing DB now and
Supabase/Postgres later.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime, timezone

@dataclass
class WorkflowEvent:
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class DurableWorkflow:
    workflow_id: str
    state: str = "running"
    step: int = 0
    history: List[WorkflowEvent] = field(default_factory=list)
    signals: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, event_type: str, **data):
        self.history.append(WorkflowEvent(event_type, data))
        self.step += 1

    def signal(self, name: str, payload: Optional[Dict[str, Any]] = None):
        self.signals.append({"name": name, "payload": payload or {}})
        self.record("signal_received", name=name, payload=payload or {})

    def pause(self, reason: str = ""):
        self.state = "paused"
        self.record("paused", reason=reason)

    def resume(self):
        self.state = "running"
        self.record("resumed")

    def cancel(self, reason: str = ""):
        self.state = "cancelled"
        self.record("cancelled", reason=reason)

    def complete(self, result: Any = None):
        self.state = "completed"
        self.record("completed", result=result)

    def fail(self, error: str):
        self.state = "failed"
        self.record("failed", error=error)

    def wait_for_signal(self, name: str) -> bool:
        """Temporal-style durable human/external signal gate."""
        return any(signal.get("name") == name for signal in self.signals)

    def checkpoint(self) -> Dict[str, Any]:
        return {"workflow_id": self.workflow_id, "state": self.state,
                "step": self.step,
                "history": [{"type": e.type, "data": e.data, "at": e.at} for e in self.history],
                "signals": list(self.signals)}

    @classmethod
    def restore(cls, snapshot: Dict[str, Any]) -> "DurableWorkflow":
        wf = cls(snapshot["workflow_id"], snapshot["state"], snapshot["step"])
        wf.history = [WorkflowEvent(e["type"], e.get("data", {}), e.get("at", "")) for e in snapshot.get("history", [])]
        wf.signals = list(snapshot.get("signals", []))
        return wf

class WorkflowExecutor:
    """Provider-neutral executor: application code decides activities; state is durable."""
    def __init__(self, workflow: DurableWorkflow, persist: Callable[[Dict[str, Any]], None]):
        self.workflow = workflow
        self.persist = persist

    def checkpoint(self):
        snapshot = self.workflow.checkpoint()
        self.persist(snapshot)
        return snapshot

    def run_step(self, name: str, fn: Callable[[], Any], *, idempotency_key: Optional[str] = None) -> Any:
        if self.workflow.state != "running":
            raise RuntimeError(f"Workflow is {self.workflow.state}")
        self.workflow.record("step_started", name=name, idempotency_key=idempotency_key)
        self.checkpoint()
        try:
            result = fn()
            self.workflow.record("step_completed", name=name, result=result)
            self.checkpoint()
            return result
        except Exception as exc:
            self.workflow.record("step_failed", name=name, error=str(exc))
            self.checkpoint()
            raise
