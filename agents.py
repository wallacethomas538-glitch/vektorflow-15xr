"""
VektorFlow 15XR — 15-agent autonomous e-commerce team.
Each agent has a defined business duty and shares the same AgentContext so
agents communicate through shared results and persistent memory.
"""
import asyncio, json, logging, re, os
from typing import Dict, Any, List, Optional, Callable
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
    def __init__(self,name:str,description:str,tools:Optional[List[Dict]]=None,tool_handlers:Optional[Dict[str,Callable]]=None):
        self.name=name; self.description=description; self.tools=tools or []
        self.tool_handlers=tool_handlers or {}
        self.status=AgentStatus.IDLE; self.result=None

    async def use_tool(self,tool_name:str,context,**kwargs):
        handler=self.tool_handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Tool '{tool_name}' is not available to {self.name}")
        result=handler(context,**kwargs)
        if hasattr(result,"__await__"):
            result=await result
        return result

    async def run(self,context,instruction):
        import uuid
        from src.event_bus import get_event_bus

        run_id=str(uuid.uuid4())
        bus=get_event_bus()

        # Consume targeted EventBus handoffs before executing this agent's task.
        pending_messages=bus.receive_agent_messages(self.name, limit=20)
        if pending_messages:
            handoffs=[]
            for message in pending_messages:
                data=message.get("data",{}) if isinstance(message,dict) else {}
                handoffs.append({
                    "source_agent":data.get("source_agent") or message.get("source_agent"),
                    "message_type":data.get("message_type") or message.get("message_type"),
                    "payload":data.get("payload") if "payload" in data else message.get("payload"),
                    "event_id":message.get("event_id"),
                })
            handoff_context=(
                "\n\nIncoming agent handoffs from EventBus:\n"
                + json.dumps(handoffs,default=str)
                + "\nUse these handoffs as additional task context. Do not claim work was completed unless you actually perform it."
            )
            instruction=f"{instruction}{handoff_context}"

        self.status=AgentStatus.RUNNING
        await bus.publish(
            "agent.run.started",
            {
                "run_id":run_id,
                "task_id":context.params.get("task_id"),
                "email":context.email,
                "agent":self.name,
                "source_agent":self.name,
                "instruction":instruction,
            },
            source=self.name,
        )
        try:
            result=await self._execute(context,instruction)
            self.result=result
            self.status=AgentStatus.COMPLETED
            await bus.publish(
                "agent.run.completed",
                {
                    "run_id":run_id,
                    "task_id":context.params.get("task_id"),
                    "email":context.email,
                    "agent":self.name,
                    "source_agent":self.name,
                    "result":result,
                },
                source=self.name,
            )
            handoff=result.get("handoff") if isinstance(result,dict) else None
            if handoff:
                target=None
                if isinstance(handoff,dict):
                    target=handoff.get("target_agent") or handoff.get("agent")
                    payload=handoff
                else:
                    payload={"message":str(handoff)}
                await bus.publish(
                    "agent.message.created",
                    {
                        "run_id":run_id,
                        "task_id":context.params.get("task_id"),
                        "email":context.email,
                        "source_agent":self.name,
                        "target_agent":target,
                        "message_type":"handoff",
                        "payload":payload,
                    },
                    source=self.name,
                )
            return result
        except Exception as exc:
            self.status=AgentStatus.FAILED
            logger.exception("Agent %s failed",self.name)
            await bus.publish(
                "agent.run.failed",
                {
                    "run_id":run_id,
                    "task_id":context.params.get("task_id"),
                    "email":context.email,
                    "agent":self.name,
                    "source_agent":self.name,
                    "error":str(exc),
                },
                source=self.name,
            )
            return {"agent":self.name,"error":str(exc),"status":"failed","run_id":run_id}
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
Respond naturally as the {self.name} agent. Do not return JSON, markdown data structures, status objects, tool metadata, or empty placeholders. Speak directly to the user like a real business specialist. Give concrete reasoning, findings, and next actions when the available evidence supports them. Be honest when required data is not available. Never claim an external action was completed unless the connected integration actually performed it."""
        result=await call_llm(prompt,DEFAULT_MODEL,context.llm_keys)
        return result.get("response","I am ready to help, but I do not have enough information to answer that yet.").strip()

    async def _llm_structured(self,context,instruction):
        shared=json.dumps(context.results,default=str)[-12000:]
        prompt=f"""You are the {self.name} agent in VektorFlow 15XR.
Duty: {self.description}
User goal/instruction: {instruction}
Shared work from other agents:
{shared}
Business context: {json.dumps(context.params,default=str)}
Return concise JSON with keys: status, message, actions, handoff, evidence. The message must be a natural response from the agent, not JSON or tool metadata. Never return an empty message when the assigned duty can be performed from the supplied context.
Never claim an external action was completed unless the connected integration actually performed it."""
        result=await call_llm(prompt,DEFAULT_MODEL,context.llm_keys)
        text=result.get("response","")
        try:
            match=re.search(r"\{.*\}",text,re.DOTALL)
            parsed=json.loads(match.group(0) if match else text)
            if isinstance(parsed,dict): return parsed
        except Exception: pass
        return {"status":"completed","message":text.strip(),"actions":[],"handoff":"","evidence":""}

class ScoutAgent(BaseAgent):
    def __init__(self):
        super().__init__("Scout","Discovers products, niches, demand and trends.",
            _tools("search_cj_products","get_tiktok_trends","get_google_trends"),
            {"search_cj_products":search_cj_products,"get_tiktok_trends":_tiktok_trends,"get_google_trends":_google_trends})
    async def _execute(self,context,instruction):
        normalized = instruction.lower().strip()
        # Direct conversation should go through the LLM. Tool-backed discovery
        # remains available for explicit product/trend/search requests.
        if any(term in normalized for term in ("trend", "trends", "tiktok")):
            return {"agent":self.name,"type":"trends","data":(await get_tiktok_trends())[:10],"status":"completed"}
        if any(term in normalized for term in ("search", "product", "products", "catalog", "supplier", "niche", "discover")):
            keyword=instruction.replace("search","").replace("scout","").strip() or "best selling products"
            products = await search_cj_products(keyword)
            if not products:
                return {"agent":self.name,"type":"products","keyword":keyword,"data":[],"status":"failed","error":"CJ product search returned no results or is not configured."}
            return {"agent":self.name,"type":"products","keyword":keyword,"data":products[:10],"status":"completed"}
        return await self._llm_role(context, instruction)

class RoleAgent(BaseAgent):
    async def _execute(self,context,instruction): return await self._llm_structured(context,instruction)


def _read_team_results(context, agent_name=None):
    """Read the structured results produced by earlier team members."""
    results=context.results
    if agent_name:
        return {agent_name.lower(): results.get(agent_name.lower())}
    return results.copy()


class SmaugAgent(RoleAgent):
    def __init__(self,name="Smaug",description="Owns profit strategy, unit economics, budgets and treasury decisions."):
        super().__init__(name,description,_tools("read_team_results","check_inventory"),{"read_team_results":_read_team_results,"check_inventory":_inventory_check})

    async def _execute(self,context,instruction):
        team_results=await self.use_tool("read_team_results",context)
        context.params["smaug_input"]=team_results
        result=await self._llm_role(context,instruction)
        return {
            "agent": self.name,
            "status": "completed",
            "message": result,
            "actions": [],
            "handoff": "",
            "evidence": team_results,
            "tool_calls": [{"tool":"read_team_results","status":"completed","agents_available":list(team_results.keys())}]
        }


class AdImageAgent:
    """Dedicated ad-image capability. Its Pollinations credential is never exposed to other agents."""
    name = "AdSpecialist"
    description = "Generates advertisement imagery through Pollinations."

    def __init__(self):
        self.api_key = os.getenv("POLLINATIONS_ADS_KEY", "")
        self.api_url = os.getenv("POLLINATIONS_API_URL", "https://gen.pollinations.ai").rstrip("/")
        self.referrer = os.getenv("POLLINATIONS_REFERRER", "vektorflow-ai")

    async def generate_image(self, prompt: str, model: str = "flux", size: str = "1024x1024"):
        if not self.api_key:
            raise RuntimeError("POLLINATIONS_ADS_KEY is not configured")
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("Prompt required")
        model = model.strip() or "flux"
        size = size.strip() or "1024x1024"
        width, height = (size.split("x", 1) if "x" in size else ("1024", "1024"))

        import httpx
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.api_url}/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Referer": self.referrer,
                },
                json={
                    "model": model,
                    "prompt": prompt,
                    "size": f"{width}x{height}",
                    "n": 1,
                    "response_format": "url",
                },
            )
        if response.status_code >= 400:
            logger.error("AdSpecialist Pollinations image API error: HTTP %s", response.status_code)
            raise RuntimeError(
                f"Pollinations image generation failed (upstream HTTP {response.status_code})"
            )
        result = response.json()
        return {
            "status": "success",
            "provider": "pollinations",
            "agent": self.name,
            "model": model,
            "data": result.get("data", []),
        }


_ad_specialist = AdImageAgent()


def get_ad_specialist():
    return _ad_specialist


def _agent_health(context): return {"status":"healthy","agent":context.params.get("agent_name","unknown")}
def _agent_info(context): return get_orchestrator().roster()
async def _inventory_check(context):
    from inventory import InventoryMonitor
    return await InventoryMonitor(context.email).check_all_stores()
async def _inventory_alerts(context):
    from inventory import InventoryMonitor
    return await InventoryMonitor(context.email).get_alert_summary()
async def _organic_content(context, product_name="product", product_description="", platforms=None, tone="casual"):
    from organic_content import OrganicContentGenerator
    return await OrganicContentGenerator(context.email).generate_content(product_name, product_description, platforms or ["instagram","facebook","tiktok"], tone, 3)
async def _campaign(context, product_type="product", goal="increase sales"):
    from campaign import generate_campaign
    return await generate_campaign(context.email, product_type, goal)
async def _outreach(context): return await handle_outreach("generate outreach", context.llm_keys, context.icp, context.email)
async def _seo(context, product_title="product", description="", category="general", keywords=None):
    from seo_optimizer import generate_seo_metadata
    return await generate_seo_metadata(product_title, description, category, keywords or [product_title], context.llm_keys)

async def _seo_research(context, product_title="product", description="", keywords=None):
    from seo_research import build_research_report
    return build_research_report(product_title, description, keywords or [])
async def _google_trends(context, keyword="dropshipping products"):
    from trend_engine import get_google_trends
    return await get_google_trends(keyword)
async def _tiktok_trends(context): return await get_tiktok_trends()
async def _memory(context): return get_all_memory(context.email)
async def _stores(context): return get_user_stores(context.email) or []
def _tools(*names):
    catalog={"search_cj_products":{"name":"search_cj_products","description":"Search supplier catalog"},"get_tiktok_trends":{"name":"get_tiktok_trends","description":"Find TikTok trend signals"},"get_google_trends":{"name":"get_google_trends","description":"Find Google trend signals"},"read_team_results":{"name":"read_team_results","description":"Read results from other agents"},"check_inventory":{"name":"check_inventory","description":"Check connected-store inventory and alerts"},"get_inventory_alerts":{"name":"get_inventory_alerts","description":"Summarize inventory alerts"},"get_stores":{"name":"get_stores","description":"Read connected store configuration"},"generate_seo":{"name":"generate_seo","description":"Generate SEO metadata"},"seo_research":{"name":"seo_research","description":"Run provider-neutral SEO keyword clustering and on-page audit"},"generate_content":{"name":"generate_content","description":"Generate organic content"},"generate_campaign":{"name":"generate_campaign","description":"Generate a marketing campaign"},"generate_outreach":{"name":"generate_outreach","description":"Generate customer outreach"},"system_health":{"name":"system_health","description":"Check VektorFlow service health"},"agent_roster":{"name":"agent_roster","description":"Read the active 15-agent roster"},"read_memory":{"name":"read_memory","description":"Read shared VektorFlow memory"}}
    return [catalog[n] for n in names]
def _handler_map(names):
    return {"search_cj_products":search_cj_products,"get_tiktok_trends":_tiktok_trends,"get_google_trends":_google_trends,"read_team_results":_read_team_results,"check_inventory":_inventory_check,"get_inventory_alerts":_inventory_alerts,"get_stores":_stores,"generate_seo":_seo,"seo_research":_seo_research,"generate_content":_organic_content,"generate_campaign":_campaign,"generate_outreach":_outreach,"system_health":_agent_health,"agent_roster":_agent_info,"read_memory":_memory}

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
            if name=="Scout":
                agent=ScoutAgent()
            elif name=="Smaug":
                agent=SmaugAgent(name,description)
            else:
                tool_sets={"Architect":["agent_roster","read_team_results"],"DaVinci":["generate_content","generate_seo","seo_research"],"Rook":["check_inventory","get_stores"],"Aegis":["system_health","get_stores"],"Arbiter":["agent_roster","read_team_results"],"Sentinel":["system_health","check_inventory","get_inventory_alerts"],"Echo":["generate_outreach","read_memory"],"Cerebrum":["read_memory","read_team_results"],"ViralDet":["get_tiktok_trends","get_google_trends"],"Shadow":["get_google_trends","get_tiktok_trends","seo_research"],"Bundler":["read_team_results","generate_campaign"],"Pivot":["read_team_results","generate_campaign"],"Oracle":["read_team_results","read_memory"]}.get(name,["read_team_results"])
                handlers=_handler_map(tool_sets)
                agent=RoleAgent(name,description,_tools(*tool_sets),handlers)
            self.register_agent(agent)
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
