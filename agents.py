"""
VektorFlow 15XR — 15-agent autonomous e-commerce team.
Each agent has a defined business duty and shares the same AgentContext so
agents communicate through shared results and persistent memory.
"""
import asyncio, json, logging, re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from database import get_user, get_user_stores, get_llm_keys, get_icp_data, save_memory, get_all_memory
from llm_handler import call_llm, DEFAULT_MODEL
from store_manager import search_cj_products
from trend_engine import get_tiktok_trends

logger = logging.getLogger("vektorflow")

class AgentStatus(Enum):
    IDLE="idle"; RUNNING="running"; COMPLETED="completed"; FAILED="failed"

@dataclass
class AgentContext:
    email: str
    user: Dict[str, Any]
    stores: List[Dict]
    llm_keys: Dict[str, str]
    icp: Dict[str, Any]
    memory: Dict[str, Any]
    params: Dict[str, Any]=field(default_factory=dict)
    results: Dict[str, Any]=field(default_factory=dict)
    conversation_history: List[Dict]=field(default_factory=list)

class BaseAgent:
    def __init__(self,name:str,description:str,tools:Optional[List[Dict]]=None):
        self.name=name; self.description=description; self.tools=tools or []
        self.status=AgentStatus.IDLE; self.result=None
    async def run(self,context,instruction):
        self.status=AgentStatus.RUNNING
        try:
            result=await self._execute(context,instruction)
            self.result=result; self.status=AgentStatus.COMPLETED; return result
        except Exception as exc:
            self.status=AgentStatus.FAILED; logger.exception("Agent %s failed",self.name)
            return {"agent":self.name,"error":str(exc),"status":"failed"}
    async def _execute(self,context,instruction): raise NotImplementedError
    def summary(self):
        return {"name":self.name,"description":self.description,"status":self.status.value,"tools":[t["name"] for t in self.tools]}
    async def _llm_role(self,context,instruction):
        shared=json.dumps(context.results,default=str)[-12000:]
        prompt=f"""You are the {self.name} agent in VektorFlow 15XR.
Duty: {self.description}
You operate an e-commerce business as part of a 15-agent team.
User goal/instruction: {instruction}
Shared work from other agents:
{shared}
Business context: {json.dumps(context.params,default=str)}
Conversation with this agent:
{json.dumps(context.conversation_history[-12:],default=str)}
Return concise JSON with keys: status, message, actions, handoff, evidence. Evidence should contain concrete findings or reasoning when the task asks for analysis. Never return empty work when the assigned duty can be performed from the supplied context.
Never claim an external action was completed unless the connected integration actually performed it."""
        result=await call_llm(prompt,DEFAULT_MODEL,context.llm_keys)
        text=result.get("response","")
        try:
            match=re.search(r"\{.*\}",text,re.DOTALL)
            return json.loads(match.group(0) if match else text)
        except Exception:
            return {"status":"completed","message":text,"actions":[],"handoff":""}

class ScoutAgent(BaseAgent):
    def __init__(self):
        super().__init__("Scout","Discovers products, niches, demand and trends.",
            [{"name":"search_cj_products","description":"Search supplier catalog"},{"name":"get_tiktok_trends","description":"Find product trends"}])
    async def _execute(self,context,instruction):
        if "trend" in instruction.lower():
            return {"agent":self.name,"type":"trends","data":(await get_tiktok_trends())[:10],"status":"completed"}
        keyword=instruction.replace("search","").replace("scout","").strip() or "best selling products"
        return {"agent":self.name,"type":"products","keyword":keyword,"data":(await search_cj_products(keyword))[:10],"status":"completed"}

class RoleAgent(BaseAgent):
    async def _execute(self,context,instruction): return await self._llm_role(context,instruction)

AGENT_ROLES=[
("Scout","Discovers products, niches, demand and trends."),
("Smaug","Owns profit strategy, unit economics, budgets and treasury decisions."),
("Architect","Designs workflows, systems, integrations and agent execution plans."),
("DaVinci","Creates product pages, brand creative, offers and conversion-focused content."),
("Rook","Executes store operations, catalog changes and routine commerce tasks."),
("Aegis","Protects accounts, transactions, credentials and operational security."),
("Arbiter","Reviews decisions, policies, compliance risks and approval gates."),
("Sentinel","Monitors systems, stores, jobs, failures, anomalies and service health."),
("Echo","Owns customer communications, support, feedback and retention signals."),
("Cerebrum","Maintains shared knowledge, memory, context and cross-agent synthesis."),
("ViralDet","Detects viral trends, social signals and emerging demand."),
("Shadow","Performs competitive intelligence, competitor monitoring and market gaps."),
("Bundler","Designs bundles, cross-sells, upsells and merchandising strategies."),
("Pivot","Runs experiments and recommends controlled changes when performance shifts."),
("Oracle","Synthesizes team evidence into forecasts, priorities and executive recommendations."),
]

class Orchestrator:
    def __init__(self):
        self.agents={}
        for name,description in AGENT_ROLES:
            self.register_agent(ScoutAgent() if name=="Scout" else RoleAgent(name,description))
    def register_agent(self,agent): self.agents[agent.name.lower()]=agent
    def get_agent(self,name): return self.agents.get(name.lower())
    def roster(self): return [a.summary() for a in self.agents.values()]
    async def team_execute(self,goal,context):
        order=[name.lower() for name,_ in AGENT_ROLES]
        results={}
        for name in order:
            agent=self.agents[name]
            role_description=agent.description
            instruction=(f"{goal}\n\nYour assigned duty is: {role_description}\n"
                         f"Perform your part of this task now. Use the results already produced by earlier agents as evidence. "
                         f"Return concrete findings, reasoning, actions, and handoff information relevant to your duty.")
            if name == "oracle":
                instruction=(f"{goal}\n\nYou are the final Oracle synthesizer. Review ALL evidence produced by the other agents in context.results. "
                             f"Identify the strongest-supported opportunities, explain the evidence from each relevant agent, "
                             f"surface missing evidence/uncertainty, and provide explicit next actions. Do not invent data.")
            result=await agent.run(context,instruction)
            results[name]=result; context.results[name]=result
            save_memory(context.email,f"agent_{name}_result",json.dumps(result,default=str))
        return {"status":"completed","goal":goal,"agent_count":15,"results":results,"roster":self.roster()}
    async def plan_and_execute(self,goal,context):
        descriptions="\n".join(f"- {name}: {desc}" for name,desc in AGENT_ROLES)
        prompt=f"""You are the VektorFlow 15XR orchestrator.
Available agents:
{descriptions}
Goal: {goal}
Shared context: {json.dumps(context.params,default=str)}
Create JSON {{"tasks":[{{"agent":"name","instruction":"..."}}]}} using only the canonical 15 names."""
        try:
            response=await call_llm(prompt,DEFAULT_MODEL,context.llm_keys)
            text=response.get("response","{}"); match=re.search(r"\{.*\}",text,re.DOTALL)
            plan=json.loads(match.group(0) if match else text)
        except Exception:
            return await self.team_execute(goal,context)
        results={}
        for task in plan.get("tasks",[]):
            name=str(task.get("agent","")).lower(); agent=self.agents.get(name)
            if not agent: continue
            result=await agent.run(context,task.get("instruction",goal))
            results[name]=result; context.results[name]=result
            save_memory(context.email,f"agent_{name}_result",json.dumps(result,default=str))
        return {"status":"completed","goal":goal,"plan":plan,"results":results,"agent_count":len(results)}

_orchestrator=Orchestrator()
def get_orchestrator(): return _orchestrator

async def run_agent_task(email,agent_name,command,params=None):
    context=AgentContext(email=email,user=get_user(email) or {},stores=get_user_stores(email) or [],
        llm_keys=get_llm_keys(email) or {},icp=get_icp_data(email) or {},memory=get_all_memory(email) or {},params=params or {})
    if agent_name.lower() in {"orchestrator","auto","autopilot","vektor"}:
        return await _orchestrator.plan_and_execute(command,context)
    agent=_orchestrator.get_agent(agent_name)
    return await agent.run(context,command) if agent else await _orchestrator.plan_and_execute(command,context)

class Autopilot:
    def __init__(self): self.running=False; self.interval_seconds=3600
    async def start(self,email):
        self.running=True
        while self.running:
            try:
                context=AgentContext(email=email,user=get_user(email) or {},stores=get_user_stores(email) or [],
                    llm_keys=get_llm_keys(email) or {},icp=get_icp_data(email) or {},memory=get_all_memory(email) or {})
                await _orchestrator.team_execute("Run the next safe e-commerce health and growth cycle.",context)
                await asyncio.sleep(self.interval_seconds)
            except Exception as exc:
                logger.error("Autopilot error: %s",exc); await asyncio.sleep(60)
    def stop(self): self.running=False
_autopilot=Autopilot()
