"""VektorFlow deterministic workflow/DAG runtime primitives.

Borrow/adapt pattern: workflow states, dependency readiness, retries and
checkpointable execution metadata. This layer decides WHAT is ready to run;
the Mission Control layer remains the authority over approvals and execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Set


WORKFLOW_STATES = {"pending", "ready", "running", "waiting", "completed", "failed", "blocked", "cancelled"}

@dataclass
class WorkflowTask:
    id: str
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 3

class WorkflowError(ValueError):
    pass

class Workflow:
    def __init__(self, tasks: Iterable[WorkflowTask]):
        self.tasks: Dict[str, WorkflowTask] = {t.id: t for t in tasks}
        self._validate()

    def _validate(self) -> None:
        for task in self.tasks.values():
            if task.status not in WORKFLOW_STATES:
                raise WorkflowError(f"Unknown task state: {task.status}")
            missing = [d for d in task.dependencies if d not in self.tasks]
            if missing:
                raise WorkflowError(f"Task {task.id} has missing dependencies: {missing}")
        # Kahn-style cycle detection.
        indegree = {k: 0 for k in self.tasks}
        edges = {k: [] for k in self.tasks}
        for task in self.tasks.values():
            for dep in task.dependencies:
                indegree[task.id] += 1
                edges[dep].append(task.id)
        queue = [k for k, v in indegree.items() if v == 0]
        seen = 0
        while queue:
            node = queue.pop()
            seen += 1
            for nxt in edges[node]:
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    queue.append(nxt)
        if seen != len(self.tasks):
            raise WorkflowError("Workflow contains a dependency cycle")

    def ready(self) -> List[WorkflowTask]:
        ready = []
        for task in self.tasks.values():
            if task.status != "pending":
                continue
            if all(self.tasks[d].status == "completed" for d in task.dependencies):
                task.status = "ready"
                ready.append(task)
        return ready

    def mark_running(self, task_id: str) -> WorkflowTask:
        task = self.tasks[task_id]
        if task.status != "ready":
            raise WorkflowError(f"Task {task_id} is not ready")
        task.status = "running"
        task.attempts += 1
        return task

    def mark_completed(self, task_id: str) -> WorkflowTask:
        task = self.tasks[task_id]
        if task.status != "running":
            raise WorkflowError(f"Task {task_id} is not running")
        task.status = "completed"
        return task

    def mark_failed(self, task_id: str) -> WorkflowTask:
        task = self.tasks[task_id]
        if task.status != "running":
            raise WorkflowError(f"Task {task_id} is not running")
        task.status = "ready" if task.attempts < task.max_attempts else "failed"
        return task

    def blocked(self) -> List[WorkflowTask]:
        return [
            t for t in self.tasks.values()
            if t.status == "pending" and any(self.tasks[d].status in {"failed", "blocked", "cancelled"} for d in t.dependencies)
        ]

    def snapshot(self) -> Dict[str, object]:
        return {
            "task_count": len(self.tasks),
            "states": {state: sum(t.status == state for t in self.tasks.values()) for state in WORKFLOW_STATES},
            "tasks": [t.__dict__.copy() for t in self.tasks.values()],
        }
