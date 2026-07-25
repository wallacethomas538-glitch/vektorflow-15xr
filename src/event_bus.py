"""Event Bus for agent-to-agent communication."""

import asyncio
import logging
from typing import Dict, List, Callable, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}
        self._event_history: List[Dict] = []

    def subscribe(self, event_type: str, callback: Callable) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    async def publish(self, event_type: str, data: Dict[str, Any], source: str = "system") -> None:
        event = {
            "type": event_type,
            "data": data,
            "source": source,
            "timestamp": datetime.utcnow().isoformat()
        }
        self._event_history.append(event)
        if event_type in self._subscribers:
            for callback in self._subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Event callback error: {e}")

    def get_history(self, limit: int = 50) -> List[Dict]:
        return self._event_history[-limit:]


_event_bus = EventBus()


def get_event_bus() -> EventBus:
    return _event_bus