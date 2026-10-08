"""Agent kill switch / fail-safe.

A killed agent must stop before it calls tools or an LLM. The global switch
("*") takes the whole team down. VF_AGENT_KILL_SWITCH=1 (or "true"/"on")
forces the global switch on at import time so a service can be started in a
safe, agents-down state.
"""

from __future__ import annotations

import os
from typing import Optional

GLOBAL_AGENT_ID = "*"


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


class KillSwitch:
    def __init__(self):
        self._killed = set()
        if _env_truthy("VF_AGENT_KILL_SWITCH"):
            self._killed.add(GLOBAL_AGENT_ID)

    def kill(self, agent_id: str):
        self._killed.add(agent_id)

    def kill_all(self):
        self._killed.add(GLOBAL_AGENT_ID)

    def revive(self, agent_id: str):
        self._killed.discard(agent_id)

    def revive_all(self):
        self._killed.discard(GLOBAL_AGENT_ID)

    def is_killed(self, agent_id: Optional[str] = None) -> bool:
        if GLOBAL_AGENT_ID in self._killed:
            return True
        return bool(agent_id and agent_id in self._killed)

    def killed_agents(self):
        return sorted(self._killed)


_kill_switch = KillSwitch()


def get_kill_switch() -> KillSwitch:
    return _kill_switch


def kill_switch_status() -> dict:
    return {
        "global_killed": _kill_switch.is_killed(),
        "killed_agents": _kill_switch.killed_agents(),
        "env_forced": _env_truthy("VF_AGENT_KILL_SWITCH"),
    }
