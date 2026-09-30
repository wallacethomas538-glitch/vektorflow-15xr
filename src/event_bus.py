"""Event Bus for VektorFlow agent-to-agent communication.

The bus remains the authoritative in-process communication layer. Optional
adapters (such as n8n) observe selected events; they do not replace the bus.
"""

import asyncio
import logging
import uuid
from typing import Dict, List, Callable, Any
from datetime import datetime, timezone

from supabase_runtime import persist_event
from src.n8n_adapter import forward_event_async

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_history: List[Dict] = []
        self._agent_inboxes: Dict[str, List[Dict]] = {}

    def subscribe(self, event_type: str, callback: Callable) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if callback not in self._subscribers[event_type]:
            self._subscribers[event_type].append(callback)

    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        source: str = "system",
    ) -> Dict[str, Any]:
        event_data = dict(data or {})
        event_id = str(event_data.get("event_id") or "evt_" + uuid.uuid4().hex)
        event_data["event_id"] = event_id
        event = {
            "event_id": event_id,
            "type": event_type,
            "data": event_data,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._event_history.append(event)

        try:
            await asyncio.to_thread(persist_event, event)
        except Exception as exc:
            logger.debug("Durable event persistence unavailable: %s", exc)

        # Local subscribers are the primary VektorFlow communication path.
        if event_type in self._subscribers:
            for callback in list(self._subscribers[event_type]):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as exc:
                    logger.error("Event callback error for %s: %s", event_id, exc)

        # A targeted handoff becomes an inbox item for the receiving agent.
        if event_type == "agent.message.created":
            target = event_data.get("target_agent")
            if target:
                key = str(target).strip().lower()
                self._agent_inboxes.setdefault(key, []).append(event)

        # n8n is an optional workflow/tool adapter, never the source of truth.
        try:
            delivered = await forward_event_async(event)
            if not delivered:
                logger.error("n8n adapter did not deliver event %s", event_id)
        except Exception as exc:
            logger.error("n8n adapter error for %s: %s", event_id, exc)

        return event

    def get_history(self, limit: int = 50) -> List[Dict]:
        return self._event_history[-limit:]

    def receive_agent_messages(self, agent_name: str, limit: int = 20) -> List[Dict]:
        """Return and remove pending targeted messages for an agent."""
        key = str(agent_name).strip().lower()
        inbox = self._agent_inboxes.get(key, [])
        messages = inbox[-limit:]
        self._agent_inboxes[key] = []
        return messages


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _event_bus
