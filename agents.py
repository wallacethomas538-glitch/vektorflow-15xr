"""
Autonomous Agents - Run tasks, inventory checks, trend detection
"""

from typing import Dict, List, Optional, Any
import asyncio
from database import add_task_history, update_task_result, get_user_stores, get_llm_keys
from llm_handler import call_llm
from store_manager import get_cj_inventory

AGENT_PERSONAS = {
    "Market Research Agent": "You are a market research expert. Analyze market trends and provide actionable insights.",
    "Trend Analysis Agent": "You are a trend detection specialist. Identify emerging product trends.",
    "Content Writer Agent": "You are a creative copywriter. Write engaging marketing copy.",
    "Campaign Optimizer": "You are a marketing strategist. Optimize campaigns for maximum ROI.",
    "Data Analyst Agent": "You are a data analyst. Provide clear analysis of product and sales data."
}

async def run_agent_task(email: str, agent_name: str, task: str, model: str = "llama-3.3-70b-versatile") -> Dict:
    task_id = add_task_history(email, agent_name, task, "running")
    
    user_keys = get_llm_keys(email)
    persona = AGENT_PERSONAS.get(agent_name, "You are a helpful AI assistant.")
    full_prompt = f"{persona}\n\nTask: {task}\n\nProvide detailed, actionable results."
    
    result = await call_llm(full_prompt, model, user_keys)
    
    if result.get("success"):
        update_task_result(task_id, result.get("response", ""), "completed")
        return {"success": True, "response": result.get("response"), "task_id": task_id}
    else:
        update_task_result(task_id, result.get("error", ""), "failed")
        return {"success": False, "error": result.get("error"), "task_id": task_id}

async def inventory_monitor_agent(email: str):
    stores = get_user_stores(email)
    alerts = []
    for store in stores:
        if store["platform"] == "cjdropshipping":
            inventory = await get_cj_inventory(store["api_key"], store["api_secret"])
            for item in inventory:
                if item.get("stock", 0) < 5:
                    alerts.append(f"Low stock: {item.get('name')} - {item.get('stock')} left")
    if alerts:
        task_id = add_task_history(email, "Inventory Monitor Agent", "Low stock check", "completed")
        update_task_result(task_id, "\n".join(alerts), "completed")
    return alerts
