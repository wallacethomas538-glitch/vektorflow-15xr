"""Analytics tracking for VektorFlow AI."""

import logging
from typing import Dict, Any, List
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class AnalyticsClient:
    def __init__(self):
        self._audit_log: List[Dict] = []
        self._metrics = {
            "api_calls": 0,
            "images_generated": 0,
            "bulk_images_generated": 0,
            "scripts_generated": 0,
            "hashtags_generated": 0,
            "captions_generated": 0,
            "videos_generated": 0,
            "qr_codes_generated": 0,
            "ad_copies_saved": 0,
            "errors": 0,
        }

    def increment_metric(self, metric: str, value: int = 1):
        if metric in self._metrics:
            self._metrics[metric] += value

    def get_metrics(self) -> Dict[str, Any]:
        return {**self._metrics, "audit_log_count": len(self._audit_log)}

    def log_action(self, user: str, action: str, details: Dict) -> Dict:
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "user": user or "anonymous",
            "action": action,
            "details": details,
        }
        self._audit_log.append(entry)
        return entry

    def get_audit_log(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        return self._audit_log[-limit-offset:-offset] if offset > 0 else self._audit_log[-limit:]

    def get_daily_stats(self, date: str = None) -> Dict:
        if not date:
            date = datetime.utcnow().strftime("%Y-%m-%d")
        return {"date": date, "api_calls": 0, "images": 0, "scripts": 0, "errors": 0}