"""VektorFlow campaign generation engine."""
import json
import logging
from typing import Any, Dict, List, Optional

from database import add_task_history, update_task_result, save_memory, get_llm_keys
from llm_handler import call_llm, DEFAULT_MODEL

logger = logging.getLogger("vektorflow")

async def generate_campaign(
    email: str,
    product_type: str,
    goal: str,
    target_audience: Optional[str] = None,
    channels: Optional[List[str]] = None,
    budget: int = 1000,
    timeline_days: int = 30,
) -> Dict[str, Any]:
    channels = channels or ["email", "social"]
    task_id = add_task_history(email, "campaign", f"Campaign for {product_type}")
    prompt = f"""Create a practical marketing campaign plan for a product.
Product: {product_type}
Goal: {goal}
Audience: {target_audience or 'general customers'}
Channels: {', '.join(channels)}
Budget: {budget}
Timeline: {timeline_days} days
Return ONLY valid JSON with keys: name, objective, audience, channels, budget, timeline_days, strategy, actions, metrics."""
    try:
        user_keys = get_llm_keys(email) or {}
        result = await call_llm(prompt, DEFAULT_MODEL, user_keys)
        raw = result.get("response", "{}")
        try:
            start, end = raw.find("{"), raw.rfind("}")
            campaign = json.loads(raw[start:end + 1]) if start >= 0 and end > start else {}
        except Exception:
            campaign = {}
        if not campaign:
            campaign = {
                "name": f"{product_type} Growth Campaign",
                "objective": goal,
                "audience": target_audience or "general customers",
                "channels": channels,
                "budget": budget,
                "timeline_days": timeline_days,
                "strategy": "Test channel-specific creative, measure conversions, and reallocate budget toward measured results.",
                "actions": [],
                "metrics": ["conversion rate", "cost per acquisition", "revenue"],
            }
        campaign_id = f"campaign_{task_id}"
        campaign["campaign_id"] = campaign_id
        save_memory(email, campaign_id, json.dumps(campaign))
        update_task_result(task_id, json.dumps(campaign), status="completed")
        return {"success": True, "campaign": campaign, "campaign_id": campaign_id, "task_id": task_id}
    except Exception as e:
        logger.error("Campaign generation failed: %s", e)
        update_task_result(task_id, json.dumps({"error": str(e)}), status="failed")
        return {"success": False, "campaign": {}, "campaign_id": None, "task_id": task_id, "error": str(e)}

print("✅ Campaign module loaded successfully")
