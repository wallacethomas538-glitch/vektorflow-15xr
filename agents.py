"""
VektorFlow 15xr - Autonomous Agent Orchestration
"""

import asyncio
import json
import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

# ============ IMPORTS ============
from database import (
    get_user, get_user_stores, get_llm_keys, get_icp_data,
    save_memory, get_memory, get_all_memory,
    add_task_history, update_task_result, get_tasks
)
from llm_handler import call_llm
from store_manager import search_cj_products, get_cj_product_details
from trend_engine import get_tiktok_trends
import re

logger = logging.getLogger("vektorflow")

# ============ TYPES ============
class AgentStatus(Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class AgentContext:
    """Context passed between agents during orchestration."""
    email: str
    user: Dict[str, Any]
    stores: List[Dict]
    llm_keys: Dict[str, str]
    icp: Dict[str, Any]
    memory: Dict[str, Any]
    params: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict] = field(default_factory=list)

# ============ BASE AGENT ============
class BaseAgent:
    """Base class for all specialized agents."""
    
    def __init__(self, name: str, description: str, tools: List[Dict] = None):
        self.name = name
        self.description = description
        self.tools = tools or []
        self.status = AgentStatus.IDLE
        self.result = None
    
    async def run(self, context: AgentContext, instruction: str) -> Dict[str, Any]:
        """Execute the agent's primary function."""
        self.status = AgentStatus.RUNNING
        try:
            result = await self._execute(context, instruction)
            self.result = result
            self.status = AgentStatus.COMPLETED
            return result
        except Exception as e:
            self.status = AgentStatus.FAILED
            logger.error(f"Agent {self.name} failed: {e}")
            return {"error": str(e)}
    
    async def _execute(self, context: AgentContext, instruction: str) -> Dict[str, Any]:
        """Override in subclasses."""
        raise NotImplementedError
    
    def get_tools_prompt(self) -> str:
        """Return a description of available tools for LLM prompting."""
        if not self.tools:
            return "No tools available."
        return "\n".join([f"- {t['name']}: {t['description']}" for t in self.tools])

# ============ SPECIALIZED AGENTS ============

class ScoutAgent(BaseAgent):
    """Product research and trend discovery."""
    
    def __init__(self):
        super().__init__(
            name="Scout",
            description="Discovers winning products and market trends.",
            tools=[
                {"name": "search_cj_products", "description": "Search CJ Dropshipping catalog"},
                {"name": "get_tiktok_trends", "description": "Fetch trending products from TikTok"},
            ]
        )
    
    async def _execute(self, context: AgentContext, instruction: str) -> Dict[str, Any]:
        # Determine if user wants trends or product search
        if "trend" in instruction.lower():
            trends = await get_tiktok_trends()
            return {"type": "trends", "data": trends[:10]}
        else:
            # Extract keyword
            keyword = instruction.replace("search", "").replace("scout", "").strip()
            if not keyword:
                keyword = "best selling products"
            products = await search_cj_products(keyword)
            return {"type": "products", "data": products[:10], "keyword": keyword}

class SourceAgent(BaseAgent):
    """Product sourcing and supplier discovery."""
    
    def __init__(self):
        super().__init__(
            name="Source",
            description="Finds reliable suppliers and compares prices.",
            tools=[
                {"name": "get_cj_product_details", "description": "Get product details from CJ"},
            ]
        )
    
    async def _execute(self, context: AgentContext, instruction: str) -> Dict[str, Any]:
        # For now, use CJ search with a twist: find multiple variants
        keyword = instruction.replace("source", "").strip() or "phone case"
        products = await search_cj_products(keyword)
        # Simulate supplier comparison
        suppliers = [
            {"name": "CJ Dropshipping", "price": products[0].get("price", "$10") if products else "$10"},
            {"name": "AliExpress", "price": "$12"},
            {"name": "Spocket", "price": "$11.50"},
        ]
        return {
            "type": "sourcing",
            "product": keyword,
            "suppliers": suppliers,
            "recommended": suppliers[0]
        }

class PriceAgent(BaseAgent):
    """Dynamic pricing optimization."""
    
    def __init__(self):
        super().__init__(
            name="Price",
            description="Optimizes product pricing for maximum profit.",
            tools=[]
        )
    
    async def _execute(self, context: AgentContext, instruction: str) -> Dict[str, Any]:
        # Use LLM to recommend pricing based on ICP and market
        icp = context.icp or {}
        prompt = f"""
        You are a pricing expert. Given the following business context:
        - Product type: {icp.get('product_type', 'general')}
        - Customer: {icp.get('customer', 'store owners')}
        - Instruction: {instruction}
        
        Recommend a dynamic pricing strategy. Provide:
        1. Base price
        2. Suggested markup (%)
        3. Bundle recommendations
        """
        result = await call_llm(prompt, "llama-3.3-70b-versatile", context.llm_keys)
        return {
            "type": "pricing",
            "recommendation": result.get("response", "Unable to generate pricing.")
        }

class FulfillAgent(BaseAgent):
    """Order fulfillment and inventory management."""
    
    def __init__(self):
        super().__init__(
            name="Fulfill",
            description="Manages inventory and automates order fulfillment.",
            tools=[]
        )
    
    async def _execute(self, context: AgentContext, instruction: str) -> Dict[str, Any]:
        stores = context.stores or []
        if not stores:
            return {"type": "fulfillment", "message": "No stores connected. Please connect a store first."}
        
        # Simulate inventory check
        inventory = [
            {"product": "LED Desk Lamp", "stock": 120, "reorder_level": 50},
            {"product": "Wireless Earbuds", "stock": 45, "reorder_level": 30},
        ]
        # Check for low stock
        low_stock = [item for item in inventory if item["stock"] < item["reorder_level"]]
        if low_stock:
            return {
                "type": "fulfillment",
                "message": "Low stock items detected.",
                "low_stock": low_stock
            }
        else:
            return {
                "type": "fulfillment",
                "message": "All inventory levels are healthy."
            }

class AnalyzeAgent(BaseAgent):
    """Business analytics and reporting."""
    
    def __init__(self):
        super().__init__(
            name="Analyze",
            description="Analyzes sales, revenue, and business performance.",
            tools=[]
        )
    
    async def _execute(self, context: AgentContext, instruction: str) -> Dict[str, Any]:
        # Use LLM to generate a business report
        prompt = f"""
        Generate a business performance summary based on:
        - Store: {context.user.get('store_name', 'Unknown')}
        - Products: {context.icp.get('product_type', 'general')}
        - Recent tasks: {len(context.results)}
        
        Provide actionable insights for improvement.
        """
        result = await call_llm(prompt, "llama-3.3-70b-versatile", context.llm_keys)
        return {
            "type": "analysis",
            "report": result.get("response", "Analysis not available.")
        }

# ============ ORCHESTRATOR ============

class Orchestrator:
    """Central controller that plans and executes multi-agent workflows."""
    
    def __init__(self):
        self.agents: Dict[str, BaseAgent] = {}
        self.register_agent(ScoutAgent())
        self.register_agent(SourceAgent())
        self.register_agent(PriceAgent())
        self.register_agent(FulfillAgent())
        self.register_agent(AnalyzeAgent())
    
    def register_agent(self, agent: BaseAgent):
        self.agents[agent.name.lower()] = agent
    
    def get_agent(self, name: str) -> Optional[BaseAgent]:
        return self.agents.get(name.lower())
    
    async def plan_and_execute(self, goal: str, context: AgentContext) -> Dict[str, Any]:
        """
        High-level method: interpret goal, break into steps, assign agents, return results.
        """
        # 1. Use LLM to decompose goal into tasks
        plan = await self._create_plan(goal, context)
        if "error" in plan:
            return plan
        
        # 2. Execute each task sequentially (or parallel later)
        results = {}
        for task in plan.get("tasks", []):
            agent_name = task.get("agent")
            instruction = task.get("instruction", "")
            if agent_name and agent_name in self.agents:
                agent = self.agents[agent_name]
                result = await agent.run(context, instruction)
                results[agent_name] = result
                # Save result to context for subsequent agents
                context.results[agent_name] = result
                # Optionally save to memory
                save_memory(context.email, f"agent_{agent_name}_result", json.dumps(result))
            else:
                logger.warning(f"Agent {agent_name} not found")
        
        # 3. Compile final response
        return {
            "goal": goal,
            "plan": plan,
            "results": results,
            "status": "completed"
        }
    
    async def _create_plan(self, goal: str, context: AgentContext) -> Dict[str, Any]:
        """
        Use LLM to break a high-level goal into a sequence of agent tasks.
        """
        agent_names = list(self.agents.keys())
        agent_descriptions = "\n".join([f"- {name}: {self.agents[name].description}" for name in agent_names])
        
        prompt = f"""
        You are a task planner. Given a user goal and a set of available agents, create a step-by-step plan.
        
        Available agents:
        {agent_descriptions}
        
        User goal: "{goal}"
        Context: {json.dumps(context.params, default=str)}
        
        Return a JSON object with a "tasks" array. Each task has:
        - "agent": the agent name (one of {agent_names})
        - "instruction": a specific instruction for that agent
        
        Example:
        {{
            "tasks": [
                {{"agent": "scout", "instruction": "Find trending LED lamps"}},
                {{"agent": "price", "instruction": "Optimize pricing for those products"}}
            ]
        }}
        
        Only return the JSON object, no other text.
        """
        
        try:
            response = await call_llm(prompt, "llama-3.3-70b-versatile", context.llm_keys)
            plan_text = response.get("response", "{}")
            # Extract JSON from response (in case extra text)
            json_match = re.search(r'\{.*\}', plan_text, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group())
            else:
                plan = json.loads(plan_text)
            return plan
        except Exception as e:
            logger.error(f"Plan creation failed: {e}")
            # Fallback: single task for the most relevant agent
            return self._fallback_plan(goal)
    
    def _fallback_plan(self, goal: str) -> Dict[str, Any]:
        """Simple heuristic fallback if LLM planning fails."""
        goal_lower = goal.lower()
        if "trend" in goal_lower or "product" in goal_lower:
            return {"tasks": [{"agent": "scout", "instruction": goal}]}
        elif "price" in goal_lower or "pricing" in goal_lower:
            return {"tasks": [{"agent": "price", "instruction": goal}]}
        elif "inventory" in goal_lower or "stock" in goal_lower:
            return {"tasks": [{"agent": "fulfill", "instruction": goal}]}
        elif "analyze" in goal_lower or "report" in goal_lower:
            return {"tasks": [{"agent": "analyze", "instruction": goal}]}
        else:
            return {"tasks": [{"agent": "scout", "instruction": goal}]}

# ============ GLOBAL ORCHESTRATOR INSTANCE ============
_orchestrator = Orchestrator()

# ============ MAIN ENTRY POINT ============
async def run_agent_task(email: str, agent_name: str, command: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Legacy compatibility wrapper for agents.py.
    Now uses the orchestrator to handle any command.
    """
    params = params or {}
    
    # Build context
    user = get_user(email)
    stores = get_user_stores(email)
    llm_keys = get_llm_keys(email)
    icp = get_icp_data(email)
    memory = get_all_memory(email) or {}
    
    context = AgentContext(
        email=email,
        user=user or {},
        stores=stores or [],
        llm_keys=llm_keys or {},
        icp=icp or {},
        memory=memory,
        params=params,
        results={}
    )
    
    # If agent_name is "orchestrator" or "auto", use full planning
    if agent_name.lower() in ["orchestrator", "auto", "autopilot"]:
        result = await _orchestrator.plan_and_execute(command, context)
        return result
    
    # Otherwise, directly run the specific agent
    agent = _orchestrator.get_agent(agent_name)
    if agent:
        result = await agent.run(context, command)
        return result
    else:
        # Fallback: use orchestrator to plan anyway
        return await _orchestrator.plan_and_execute(command, context)

# ============ AUTOPILOT MODE (Advanced) ============
class Autopilot:
    """Continuous business monitoring and proactive agent triggers."""
    
    def __init__(self):
        self.running = False
        self.interval_seconds = 3600  # hourly
    
    async def start(self, email: str):
        self.running = True
        logger.info(f"Autopilot started for {email}")
        while self.running:
            try:
                # Check inventory, trends, etc.
                context = AgentContext(
                    email=email,
                    user=get_user(email) or {},
                    stores=get_user_stores(email) or [],
                    llm_keys=get_llm_keys(email) or {},
                    icp=get_icp_data(email) or {},
                    memory=get_all_memory(email) or {},
                    params={}
                )
                # Run a health check
                fulfill_agent = _orchestrator.get_agent("fulfill")
                result = await fulfill_agent.run(context, "Check inventory")
                if result.get("low_stock"):
                    # Send alert (email, slack, etc.)
                    logger.info(f"Low stock alert for {email}")
                    # Save notification to memory
                    save_memory(email, "autopilot_alert", json.dumps(result))
                
                # Wait for next cycle
                await asyncio.sleep(self.interval_seconds)
            except Exception as e:
                logger.error(f"Autopilot error: {e}")
                await asyncio.sleep(60)
    
    def stop(self):
        self.running = False
        logger.info("Autopilot stopped")

# Singleton autopilot instance
_autopilot = Autopilot()

# ============ TEST ============
if __name__ == "__main__":
    import asyncio
    async def test():
        result = await run_agent_task(
            email="commander@vektorflow.com",
            agent_name="orchestrator",
            command="Find trending phone accessories and recommend pricing."
        )
        print(json.dumps(result, indent=2))
    asyncio.run(test())