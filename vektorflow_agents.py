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
from store_manager import search_cj_products, get_cj_product_details
from trend_engine import get_tiktok_trends
from external_tools import brave_search, tavily_search, apify_actor, webscraping_ai
from ai_observability import start_span
from agent_personas import AGENT_PERSONAS
from kill_switch import get_kill_switch
import store_ops
from store_ops import get_agent_playbook

logger = logging.getLogger("vektorflow")

# Tool risk classes used by the agent layer. Read-only and draft-only tools may
# run as evidence gathering; mutating or customer/money-adjacent tools stay
# behind Wallace's approval gate.
TOOL_RISK = {
    "read_team_results": "low",
    "check_inventory": "low",
    "get_inventory_alerts": "low",
    "get_stores": "low",
    "system_health": "low",
    "agent_roster": "low",
    "read_memory": "low",
    "search_cj_products": "low",
    "get_cj_product_details": "low",
    "get_tiktok_trends": "low",
    "get_google_trends": "low",
    "brave_search": "low",
    "tavily_search": "low",
    "seo_research": "low",
    "webscraping_ai": "low",
    "get_shopify_products": "low",
    "get_shopify_orders": "low",
    "watch_new_orders": "low",
    "watch_abandoned_carts": "low",
    "classify_customer_message": "low",
    "draft_customer_reply": "low",
    "handle_email_notification": "low",
    "create_order_service_case": "low",
    "generate_organic_ad": "medium",
    "generate_content": "medium",
    "generate_campaign": "medium",
    "generate_seo": "medium",
    "generate_outreach": "medium",
    "apify_actor": "medium",
    "import_supplier_product": "high",
}

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
        self.name=name; self.description=description; self.persona=AGENT_PERSONAS.get(name, "You are the " + name + " specialist in VektorFlow 15XR. Stay within your defined duty and be factual."); self.tools=tools or []
        self.tool_handlers=tool_handlers or {}
        self.status=AgentStatus.IDLE; self.result=None

    async def use_tool(self,tool_name:str,context,**kwargs):
        if get_kill_switch().is_killed(self.name):
            return {"success": False, "blocked": True, "status": "blocked", "tool": tool_name,
                    "error": f"Kill switch is on for {self.name}; tool execution is stopped."}
        handler=self.tool_handlers.get(tool_name)
        if handler is None:
            raise ValueError(f"Tool '{tool_name}' is not available to {self.name}")
        risk=TOOL_RISK.get(tool_name, "high")
        params=getattr(context, "params", {}) or {}
        if risk in {"high", "critical"} and not params.get("approval_granted"):
            return {"success": False, "blocked": True, "status": "awaiting_approval", "tool": tool_name,
                    "risk": risk, "error": f"Tool '{tool_name}' is {risk}-risk and requires Wallace's approval before it runs."}
        with start_span(
            "vektorflow.tool",
            {
                "vf.agent": self.name,
                "vf.tool": tool_name,
                "vf.mission_id": context.params.get("mission_id"),
                "vf.task_id": context.params.get("task_id"),
            },
        ):
            result=handler(context,**kwargs)
            if hasattr(result,"__await__"):
                result=await result
        return result

    async def run(self,context,instruction):
        import uuid
        from src.event_bus import get_event_bus

        run_id=str(uuid.uuid4())
        bus=get_event_bus()

        if get_kill_switch().is_killed(self.name):
            self.status=AgentStatus.FAILED
            return {"agent": self.name, "status": "blocked", "blocked": True, "run_id": run_id,
                    "error": f"Kill switch is on for {self.name}; agent stopped before tools or LLM work."}

        # Consume targeted EventBus handoffs before executing this agent's task.
        pending_messages=[] if context.params.get("conversation_mode") == "direct" else bus.receive_agent_messages(self.name, limit=20)
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
            with start_span(
                "vektorflow.agent.run",
                {
                    "vf.agent": self.name,
                    "vf.run_id": run_id,
                    "vf.mission_id": context.params.get("mission_id"),
                    "vf.task_id": context.params.get("task_id"),
                },
            ):
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
        return {"name":self.name,"description":self.description,"persona":self.persona,"status":self.status.value,"tools":[t["name"] for t in self.tools],"playbook_sections":store_ops.AGENT_PLAYBOOK_SECTIONS.get(self.name.lower(),[])}
    async def _gather_tool_evidence(self,context,instruction):
        """Run assigned low-risk tools before reasoning when the task needs them.

        This is the difference between a role prompt and a working agent: the
        LLM receives tool evidence (products, orders, carts, inventory, team
        results) instead of improvising from the instruction alone. Mutating
        tools are never auto-run here; they stay behind the approval gate.
        """
        text=(instruction or "").lower()
        params=getattr(context, "params", {}) or {}
        wanted=[]
        def wants(tool, *terms):
            if tool in self.tool_handlers and any(term in text for term in terms):
                wanted.append(tool)
        if "read_team_results" in self.tool_handlers and context.results:
            wanted.append("read_team_results")
        wants("check_inventory", "inventory", "stock", "low stock", "out of stock")
        wants("get_inventory_alerts", "inventory alert", "stock alert", "low stock")
        wants("get_shopify_products", "product", "catalog", "store", "shopify", "listing", "bundle")
        wants("get_shopify_orders", "order", "customer", "fulfillment", "shipping", "service")
        wants("watch_new_orders", "new order", "new orders", "order came in", "orders")
        wants("watch_abandoned_carts", "abandoned", "cart", "checkout")
        wants("search_cj_products", "supplier", "cj", "dropship", "source product")
        wants("get_cj_product_details", "supplier product", "cj product", "product id")
        if "handle_email_notification" in self.tool_handlers and isinstance(params.get("email_event"), dict):
            wanted.append("handle_email_notification")
        if "classify_customer_message" in self.tool_handlers and isinstance(params.get("customer_message"), dict):
            wanted.append("classify_customer_message")
        if "create_order_service_case" in self.tool_handlers and isinstance(params.get("order"), dict):
            wanted.append("create_order_service_case")
        evidence={}
        seen=set()
        for tool in wanted:
            if tool in seen:
                continue
            seen.add(tool)
            try:
                evidence[tool]=await self.use_tool(tool, context)
            except Exception as exc:
                evidence[tool]={"success": False, "error": str(exc)}
        if evidence:
            params["tool_evidence"]=evidence
            context.params=params
        return evidence
    async def _llm_role(self,context,instruction):
        shared=json.dumps(context.results,default=str)[-12000:]
        prompt=f"""You are the {self.name} agent in VektorFlow 15XR.
Persona: {self.persona}
Duty: {self.description}
{get_agent_playbook(self.name)}
You operate an e-commerce business as part of a 15-agent team.
User goal/instruction: {instruction}
Shared work from other agents:
{shared}
Tool evidence gathered for this run:
{json.dumps(context.params.get("tool_evidence", {}),default=str)[-8000:]}
Business context: {json.dumps(context.params,default=str)}
Conversation with this agent:
{json.dumps(context.conversation_history[-12:],default=str)}
Respond naturally as the {self.name} agent. Do not return JSON, markdown data structures, status objects, tool metadata, or empty placeholders. Speak directly to the user like a real business specialist. Give concrete reasoning, findings, and next actions when the available evidence supports them. Be honest when required data is not available. Never claim an external action was completed unless the connected integration actually performed it."""
        result=await call_llm(prompt,DEFAULT_MODEL,context.llm_keys,context.params.get("temperature"))
        return result.get("response","I am ready to help, but I do not have enough information to answer that yet.").strip()

    async def _llm_structured(self,context,instruction):
        shared=json.dumps(context.results,default=str)[-12000:]
        prompt=f"""You are the {self.name} agent in VektorFlow 15XR.
Persona: {self.persona}
Duty: {self.description}
{get_agent_playbook(self.name)}
User goal/instruction: {instruction}
Shared work from other agents:
{shared}
Tool evidence gathered for this run:
{json.dumps(context.params.get("tool_evidence", {}),default=str)[-8000:]}
Business context: {json.dumps(context.params,default=str)}
Return concise JSON with keys: status, message, actions, handoff, evidence. The message must be a natural response from the agent, not JSON or tool metadata. Never return an empty message when the assigned duty can be performed from the supplied context.
Never claim an external action was completed unless the connected integration actually performed it."""
        result=await call_llm(prompt,DEFAULT_MODEL,context.llm_keys,context.params.get("temperature"))
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
            _tools("search_cj_products","get_cj_product_details","get_shopify_products","get_tiktok_trends","get_google_trends","brave_search","tavily_search","apify_actor"),
            {"search_cj_products":search_cj_products,"get_cj_product_details":_cj_product_details,"get_shopify_products":_store_products,"get_tiktok_trends":_tiktok_trends,"get_google_trends":_google_trends,"brave_search":_brave_search,"tavily_search":_tavily_search,"apify_actor":_apify_actor})
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
    async def _execute(self,context,instruction):
        evidence=await self._gather_tool_evidence(context,instruction)
        result=await self._llm_structured(context,instruction)
        if isinstance(result,dict):
            result.setdefault("agent",self.name)
            if evidence:
                result["tool_evidence"]=evidence
                result["tool_calls"]=[{"tool":tool,"status":"failed" if isinstance(value,dict) and value.get("success") is False else "completed"} for tool,value in evidence.items()]
        return result


def _read_team_results(context, agent_name=None):
    """Read the structured results produced by earlier team members."""
    results=context.results
    if agent_name:
        return {agent_name.lower(): results.get(agent_name.lower())}
    return results.copy()


class SmaugAgent(RoleAgent):
    def __init__(self,name="Smaug",description="Owns profit strategy, unit economics, budgets and treasury decisions."):
        super().__init__(name,description,_tools("read_team_results","check_inventory","get_shopify_products","get_shopify_orders","watch_new_orders"),{"read_team_results":_read_team_results,"check_inventory":_inventory_check,"get_shopify_products":_store_products,"get_shopify_orders":_store_orders,"watch_new_orders":_watch_new_orders})

    async def _execute(self,context,instruction):
        team_results=await self.use_tool("read_team_results",context)
        context.params["smaug_input"]=team_results
        evidence=await self._gather_tool_evidence(context,instruction)
        result=await self._llm_role(context,instruction)
        tool_calls=[{"tool":"read_team_results","status":"completed","agents_available":list(team_results.keys())}]
        tool_calls += [{"tool":tool,"status":"failed" if isinstance(value,dict) and value.get("success") is False else "completed"} for tool,value in evidence.items()]
        return {
            "agent": self.name,
            "status": "completed",
            "message": result,
            "actions": [],
            "handoff": "",
            "evidence": team_results,
            "tool_evidence": evidence,
            "tool_calls": tool_calls
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


async def _cj_product_details(context, product_id=""):
    return await get_cj_product_details(product_id)
async def _store_products(context, limit=50):
    return await store_ops.get_shopify_products(context, limit=limit)
async def _store_orders(context, limit=50):
    return await store_ops.get_shopify_orders(context, limit=limit)
async def _watch_new_orders(context, limit=50, alert_existing=False):
    return await store_ops.watch_new_orders(context, limit=limit, alert_existing=alert_existing)
async def _watch_abandoned_carts(context, limit=50):
    return await store_ops.watch_abandoned_carts(context, limit=limit)
async def _import_supplier_product(context, **kwargs):
    return await store_ops.import_supplier_product(context, **kwargs)
def _handle_email_notification(context, **kwargs):
    params=getattr(context, "params", {}) or {}
    event=params.get("email_event") if isinstance(params.get("email_event"), dict) else {}
    return store_ops.handle_email_notification(context, **{**event, **kwargs})
def _draft_customer_reply(context, **kwargs):
    return store_ops.draft_customer_reply(context, **kwargs)
def _classify_customer_message(context, subject="", body=""):
    params=getattr(context, "params", {}) or {}
    event=params.get("customer_message") if isinstance(params.get("customer_message"), dict) else {}
    return store_ops.classify_customer_message(subject or event.get("subject", ""), body or event.get("body", ""))
def _create_order_service_case(context, order=None):
    params=getattr(context, "params", {}) or {}
    return store_ops.create_order_service_case(context, order or params.get("order") or {})
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
async def _brave_search(context, query=""):
    return await brave_search(query)
async def _tavily_search(context, query=""):
    return await tavily_search(query)
async def _apify_actor(context, actor_id="", run_input=None):
    return await apify_actor(actor_id, run_input or {})
async def _webscraping_ai(context, url="", question=None):
    return await webscraping_ai(url, question)
def _tools(*names):
    catalog={"search_cj_products":{"name":"search_cj_products","description":"Search supplier catalog"},"get_cj_product_details":{"name":"get_cj_product_details","description":"Fetch one exact CJ supplier product by product id"},"get_tiktok_trends":{"name":"get_tiktok_trends","description":"Find TikTok trend signals"},"get_google_trends":{"name":"get_google_trends","description":"Find Google trend signals"},"read_team_results":{"name":"read_team_results","description":"Read results from other agents"},"check_inventory":{"name":"check_inventory","description":"Check connected-store inventory and alerts"},"get_inventory_alerts":{"name":"get_inventory_alerts","description":"Summarize inventory alerts"},"get_stores":{"name":"get_stores","description":"Read connected store configuration"},"get_shopify_products":{"name":"get_shopify_products","description":"Read products from the connected Shopify store"},"get_shopify_orders":{"name":"get_shopify_orders","description":"Read orders from the connected Shopify store"},"watch_new_orders":{"name":"watch_new_orders","description":"Return Shopify orders not seen before (first run sets a silent baseline)"},"watch_abandoned_carts":{"name":"watch_abandoned_carts","description":"List abandoned carts with draft-only recovery messages"},"import_supplier_product":{"name":"import_supplier_product","description":"Import one exact CJ supplier product into Shopify as a draft (approval-gated)"},"handle_email_notification":{"name":"handle_email_notification","description":"Turn an email event into a service case plus draft reply for Wallace's approval"},"draft_customer_reply":{"name":"draft_customer_reply","description":"Draft a customer reply; never sends"},"classify_customer_message":{"name":"classify_customer_message","description":"Classify a customer message and escalation priority"},"create_order_service_case":{"name":"create_order_service_case","description":"Create an order service case checklist"},"generate_seo":{"name":"generate_seo","description":"Generate SEO metadata"},"seo_research":{"name":"seo_research","description":"Run provider-neutral SEO keyword clustering and on-page audit"},"generate_content":{"name":"generate_content","description":"Generate organic content"},"generate_organic_ad":{"name":"generate_organic_ad","description":"Write organic social ad copy Wallace can copy and post himself"},"generate_campaign":{"name":"generate_campaign","description":"Generate a marketing campaign"},"generate_outreach":{"name":"generate_outreach","description":"Generate customer outreach"},"system_health":{"name":"system_health","description":"Check VektorFlow service health"},"agent_roster":{"name":"agent_roster","description":"Read the active 15-agent roster"},"read_memory":{"name":"read_memory","description":"Read shared VektorFlow memory"},"brave_search":{"name":"brave_search","description":"Search the web for current research and competitive intelligence"},"tavily_search":{"name":"tavily_search","description":"Run agent-oriented web research with grounded sources"},"apify_actor":{"name":"apify_actor","description":"Run an Apify web-data extraction Actor"},"webscraping_ai":{"name":"webscraping_ai","description":"Fetch or question a webpage through a rendering/extraction API"}}
    return [catalog[n] for n in names]
def _handler_map(names):
    return {"search_cj_products":search_cj_products,"get_cj_product_details":_cj_product_details,"get_tiktok_trends":_tiktok_trends,"get_google_trends":_google_trends,"read_team_results":_read_team_results,"check_inventory":_inventory_check,"get_inventory_alerts":_inventory_alerts,"get_stores":_stores,"get_shopify_products":_store_products,"get_shopify_orders":_store_orders,"watch_new_orders":_watch_new_orders,"watch_abandoned_carts":_watch_abandoned_carts,"import_supplier_product":_import_supplier_product,"handle_email_notification":_handle_email_notification,"draft_customer_reply":_draft_customer_reply,"classify_customer_message":_classify_customer_message,"create_order_service_case":_create_order_service_case,"generate_seo":_seo,"seo_research":_seo_research,"generate_content":_organic_content,"generate_organic_ad":_organic_content,"generate_campaign":_campaign,"generate_outreach":_outreach,"system_health":_agent_health,"agent_roster":_agent_info,"read_memory":_memory,"brave_search":_brave_search,"tavily_search":_tavily_search,"apify_actor":_apify_actor,"webscraping_ai":_webscraping_ai}

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
                tool_sets={"Architect":["agent_roster","read_team_results","system_health"],"DaVinci":["generate_content","generate_organic_ad","generate_seo","seo_research","webscraping_ai","get_shopify_products","read_team_results"],"Rook":["check_inventory","get_stores","get_shopify_products","get_shopify_orders","import_supplier_product","watch_new_orders","watch_abandoned_carts","create_order_service_case"],"Aegis":["system_health","get_stores","get_shopify_orders","classify_customer_message","read_team_results"],"Arbiter":["agent_roster","read_team_results","classify_customer_message","handle_email_notification","get_shopify_orders","watch_abandoned_carts"],"Sentinel":["system_health","check_inventory","get_inventory_alerts","get_shopify_products","get_shopify_orders","watch_new_orders","watch_abandoned_carts"],"Echo":["generate_outreach","read_memory","handle_email_notification","draft_customer_reply","classify_customer_message","get_shopify_orders","watch_new_orders","create_order_service_case"],"Cerebrum":["read_memory","read_team_results","get_shopify_products","get_shopify_orders"],"ViralDet":["get_tiktok_trends","get_google_trends","brave_search","tavily_search","get_shopify_products"],"Shadow":["get_google_trends","get_tiktok_trends","seo_research","brave_search","tavily_search","webscraping_ai","get_shopify_products"],"Bundler":["read_team_results","generate_campaign","get_shopify_products","check_inventory"],"Pivot":["read_team_results","generate_campaign","watch_abandoned_carts","get_shopify_orders"],"Oracle":["read_team_results","read_memory","get_shopify_products","get_shopify_orders"]}.get(name,["read_team_results"])
                handlers=_handler_map(tool_sets)
                agent=RoleAgent(name,description,_tools(*tool_sets),handlers)
            self.register_agent(agent)
    def register_agent(self,agent): self.agents[agent.name.lower()]=agent
    def get_agent(self,name): return self.agents.get(name.lower())
    def roster(self): return [a.summary() for a in self.agents.values()]
    async def team_execute(self,goal,context,cancel_event=None):
        order=[name.lower() for name,_ in AGENT_ROLES]
        results={}
        completed=[]
        cancelled=False
        for name in order:
            if cancel_event is not None and cancel_event.is_set():
                cancelled=True; break
            agent=self.agents[name]
            role_description=agent.description
            instruction=(f"{goal}\n\nYour assigned duty is: {role_description}\n"
                         f"Perform your part of this task now. Use the results already produced by earlier agents as evidence. "
                         f"Return concrete findings, reasoning, actions, and handoff information relevant to your duty.")
            if name == "oracle":
                instruction=(f"{goal}\n\nYou are the final Oracle synthesizer. Review ALL evidence produced by the other agents in context.results. "
                             f"Identify the strongest-supported opportunities, explain the evidence from each relevant agent, "
                             f"surface missing evidence/uncertainty, and provide explicit next actions. Do not invent data.")
            try:
                result=await agent.run(context,instruction)
            except asyncio.CancelledError:
                cancelled=True; break
            results[name]=result; context.results[name]=result
            completed.append(name)
            save_memory(context.email,f"agent_{name}_result",json.dumps(result,default=str))
        status="cancelled" if cancelled else "completed"
        return {"status":status,"goal":goal,"agent_count":len(results),"results":results,"roster":self.roster(),
                "completed_agents":completed,"cancelled":cancelled}
    async def plan_and_execute(self,goal,context):
        descriptions="\n".join(f"- {name}: {desc}" for name,desc in AGENT_ROLES)
        prompt=f"""You are the VektorFlow 15XR orchestrator.
Available agents:
{descriptions}
Goal: {goal}
Shared context: {json.dumps(context.params,default=str)}
Create JSON {{"tasks":[{{"agent":"name","instruction":"..."}}]}} using only the canonical 15 names."""
        try:
            response=await call_llm(prompt,DEFAULT_MODEL,context.llm_keys,context.params.get("temperature"))
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
