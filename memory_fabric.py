"""Compatibility facade for VektorFlow's authoritative Postgres runtime memory.

All durable memory writes and retrieval now flow through runtime_memory.py.
This module keeps the existing MemoryFabric API for agents that already import it.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from runtime_memory import (
    DEFAULT_EMAIL,
    get_all_memory,
    get_memory,
    hybrid_search,
    save_memory,
)


class MemoryFabric:
    def __init__(self, email: str = DEFAULT_EMAIL):
        self.email = email

    def store_episode(self, agent_id: str, action: str, context: Dict, outcome: str):
        save_memory(
            self.email,
            f"episode:{agent_id}:{action}",
            outcome,
            source_agent=agent_id,
            metadata={"action": action, "context": context, "memory_type": "episodic"},
        )

    def get_episodes(self, agent_id: str, limit: int = 50):
        results = hybrid_search(email=self.email, query=agent_id, limit=limit)
        return [
            r for r in results
            if (r.get("source_agent") == agent_id)
            or r.get("metadata", {}).get("memory_type") == "episodic"
        ]

    def update_shared_context(self, key: str, value: Any, source: str):
        save_memory(
            self.email,
            f"shared:{key}",
            value if isinstance(value, str) else str(value),
            source_agent=source,
            metadata={"memory_type": "shared_context", "key": key},
        )

    def get_shared_context(self, key: Optional[str] = None):
        if key:
            return get_memory(self.email, f"shared:{key}")
        return {
            row["memory_key"].removeprefix("shared:"): row["memory_value"]
            for row in get_all_memory(self.email)
            if row["memory_key"].startswith("shared:")
        }

    def get_all_shared_context(self):
        return self.get_shared_context()

    def close(self):
        return None
