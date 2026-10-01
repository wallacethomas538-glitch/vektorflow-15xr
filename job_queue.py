"""VektorFlow job queue primitives.

Borrowed/adapted from BullMQ concepts: named queues, priorities, delayed jobs,
retries/backoff, parent-child dependencies, pause/resume, and lifecycle events.
This is a provider-neutral contract; Redis/Valkey can be plugged in later
without making the queue layer the VektorFlow authority.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from heapq import heappop, heappush
from typing import Any, Dict, List, Optional
import time

@dataclass(order=True)
class QueuedJob:
    sort_key: tuple = field(init=False, repr=False)
    priority: int = 100
    run_at: float = field(default_factory=time.time)
    sequence: int = 0
    id: str = field(compare=False, default="")
    name: str = field(compare=False, default="")
    payload: Dict[str, Any] = field(compare=False, default_factory=dict)
    attempts: int = field(compare=False, default=0)
    max_attempts: int = field(compare=False, default=3)
    parent_id: Optional[str] = field(compare=False, default=None)
    status: str = field(compare=False, default="waiting")

    def __post_init__(self):
        self.sort_key = (self.run_at, self.priority, self.sequence)

class JobQueue:
    def __init__(self, name: str):
        self.name = name
        self._jobs: Dict[str, QueuedJob] = {}
        self._heap: List[QueuedJob] = []
        self._sequence = 0
        self.paused = False
        self.events: List[Dict[str, Any]] = []

    def add(self, name: str, payload: Dict[str, Any], *, job_id: Optional[str] = None,
            priority: int = 100, delay_seconds: float = 0, max_attempts: int = 3,
            parent_id: Optional[str] = None) -> QueuedJob:
        self._sequence += 1
        jid = job_id or f"{self.name}:{self._sequence}"
        if jid in self._jobs:
            return self._jobs[jid]
        job = QueuedJob(priority=priority, run_at=time.time()+delay_seconds,
                        sequence=self._sequence, id=jid, name=name,
                        payload=payload, max_attempts=max_attempts,
                        parent_id=parent_id)
        self._jobs[jid] = job
        heappush(self._heap, job)
        self._emit("waiting", job)
        return job

    def next(self) -> Optional[QueuedJob]:
        if self.paused:
            return None
        now = time.time()
        while self._heap:
            job = self._heap[0]
            if job.status != "waiting":
                heappop(self._heap)
                continue
            if job.run_at > now:
                return None
            heappop(self._heap)
            if not self.is_ready(job.id):
                heappush(self._heap, job)
                return None
            job.status = "active"
            job.attempts += 1
            self._emit("active", job)
            return job
        return None

    def complete(self, job_id: str, result: Any = None) -> QueuedJob:
        job = self._jobs[job_id]
        job.status = "completed"
        job.payload = {**job.payload, "result": result}
        self._emit("completed", job)
        return job

    def fail(self, job_id: str, reason: str, backoff_seconds: float = 1.0) -> QueuedJob:
        job = self._jobs[job_id]
        if job.attempts < job.max_attempts:
            job.status = "waiting"
            job.run_at = time.time() + backoff_seconds * (2 ** (job.attempts - 1))
            job.sort_key = (job.run_at, job.priority, job.sequence)
            heappush(self._heap, job)
            self._emit("retrying", job, reason=reason)
        else:
            job.status = "failed"
            job.payload = {**job.payload, "failure": reason}
            self._emit("failed", job, reason=reason)
        return job

    def pause(self): self.paused = True; self._emit("paused", None)
    def resume(self): self.paused = False; self._emit("resumed", None)

    def chain(self, jobs: List[Dict[str, Any]]) -> List[QueuedJob]:
        """Enqueue jobs serially using parent completion dependencies."""
        created = []
        parent_id = None
        for spec in jobs:
            job = self.add(parent_id=parent_id, **spec)
            created.append(job)
            parent_id = job.id
        return created

    def group(self, jobs: List[Dict[str, Any]]) -> List[QueuedJob]:
        """Enqueue independent jobs for parallel workers."""
        return [self.add(**spec) for spec in jobs]

    def chord(self, jobs: List[Dict[str, Any]], callback: Dict[str, Any]) -> tuple[List[QueuedJob], QueuedJob]:
        """Enqueue a parallel group plus a callback dependent on all group jobs."""
        group_jobs = self.group(jobs)
        callback_job = self.add(**callback)
        callback_job.payload = {**callback_job.payload, "wait_for": [job.id for job in group_jobs]}
        return group_jobs, callback_job

    def is_ready(self, job_id: str) -> bool:
        job = self._jobs[job_id]
        if job.parent_id:
            parent = self._jobs.get(job.parent_id)
            if parent and parent.status != "completed":
                return False
        return all(self._jobs.get(jid) and self._jobs[jid].status == "completed"
                   for jid in job.payload.get("wait_for", []))

    def snapshot(self) -> Dict[str, Any]:
        return {"name": self.name, "paused": self.paused,
                "counts": {s: sum(j.status == s for j in self._jobs.values())
                           for s in ("waiting","active","completed","failed")},
                "jobs": [self._serialize(j) for j in self._jobs.values()]}

    def _emit(self, event: str, job: Optional[QueuedJob], **extra):
        self.events.append({"event": event, "job_id": getattr(job, "id", None),
                            "at": datetime.now(timezone.utc).isoformat(), **extra})

    @staticmethod
    def _serialize(job: QueuedJob) -> Dict[str, Any]:
        return {"id": job.id, "name": job.name, "status": job.status,
                "attempts": job.attempts, "max_attempts": job.max_attempts,
                "parent_id": job.parent_id, "payload": job.payload}
