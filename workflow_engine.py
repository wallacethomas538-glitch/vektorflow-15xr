"""VektorFlow deterministic workflow/DAG runtime primitives.

Borrow/adapt pattern: workflow states, dependency readiness, retries and
checkpointable execution metadata. This layer decides WHAT is ready to run;
the Mission Control layer remains the authority over approvals and execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

@dataclass
class ArtifactRef:
    """Provider-neutral artifact reference for passing outputs between tasks."""
    name: str
    uri: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class WorkflowTemplate:
    """Reusable task template inspired by Argo step/template composition."""
    name: str
    agent: Optional[str] = None
    command: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


WORKFLOW_STATES = {"pending", "ready", "running", "waiting", "completed", "failed", "blocked", "cancelled"}

@dataclass
class WorkflowTask:
    id: str
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"
    attempts: int = 0
    max_attempts: int = 3
    retry_backoff_seconds: float = 1.0
    template: Optional[str] = None
    inputs: List[ArtifactRef] = field(default_factory=list)
    outputs: List[ArtifactRef] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

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

    def chain(self, task_ids: List[str]) -> None:
        """Wire tasks sequentially, Celery-chain style."""
        for previous, current in zip(task_ids, task_ids[1:]):
            if previous not in self.tasks or current not in self.tasks:
                raise WorkflowError("Unknown task in chain")
            if previous not in self.tasks[current].dependencies:
                self.tasks[current].dependencies.append(previous)
        self._validate()

    def group(self, task_ids: List[str]) -> List[WorkflowTask]:
        """Return independent tasks eligible for parallel execution."""
        unknown = [task_id for task_id in task_ids if task_id not in self.tasks]
        if unknown:
            raise WorkflowError(f"Unknown tasks in group: {unknown}")
        return [self.tasks[task_id] for task_id in task_ids]

    def chord(self, task_ids: List[str], callback_id: str) -> None:
        """Make a callback wait for a group of tasks, Celery-chord style."""
        if callback_id not in self.tasks:
            raise WorkflowError(f"Unknown callback task: {callback_id}")
        for task_id in task_ids:
            if task_id not in self.tasks:
                raise WorkflowError(f"Unknown task in chord: {task_id}")
            if task_id not in self.tasks[callback_id].dependencies:
                self.tasks[callback_id].dependencies.append(task_id)
        self._validate()

    def snapshot(self) -> Dict[str, object]:
        return {
            "task_count": len(self.tasks),
            "states": {state: sum(t.status == state for t in self.tasks.values()) for state in WORKFLOW_STATES},
            "tasks": [t.__dict__.copy() for t in self.tasks.values()],
        }
