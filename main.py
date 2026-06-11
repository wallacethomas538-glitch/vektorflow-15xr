"""
VektorFlow 15xr - Main Entry Point
15 agents. Memory fabric. Cognition sharing. E-commerce intelligence.
"""

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
from datetime import datetime

# Import all modules
from memory_fabric import MemoryFabric
from agent_with_memory import VektorAgent
from kill_switch import KillSwitch
from free_tier_router import FreeTierRouter
from monitor_agent import MonitorAgent
from interference_merge import InterferenceMerge
from semantic_pattern_operator import SemanticPatternOperator
from cognition_fabric import CognitionFabric
from trend_to_catalog_mapper import TrendToCatalogMapper
from ai_citation_optimizer import AICitationOptimizer
from click_to_message_builder import ClickToMessageBuilder
from social_commerce_connector import SocialCommerceConnector
from weekly_report_generator import WeeklyReportGenerator

app = FastAPI(title="VektorFlow 15xr", description="15 agents with memory fabric + e-commerce intelligence")

# Active agents storage
agents: Dict[str, VektorAgent] = {}
kill_switch = KillSwitch()
memory = MemoryFabric()

# ========== CORE AGENT ENDPOINTS ==========

class TaskRequest(BaseModel):
    agent_id: str
    task: str
    data: Dict[str, Any]

class CatalogUpdate(BaseModel):
    store_id: str
    products: List[Dict[str, Any]]

@app.get("/")
def root():
    return {
        "status": "online",
        "system": "VektorFlow 15xr",
        "version": "2.0",
        "agents_ready": 15,
        "features": [
            "Three-tier memory fabric",
            "Cognition sharing",
            "Interference merge",
            "Free-tier LLM routing",
            "Trend-to-catalog mapping",
            "AI citation optimization",
            "Click-to-message campaigns",
            "Weekly intelligence reports"
        ]
    }

@app.get("/health")
def health():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.post("/agent/register")
def register_agent(agent_id: str):
    if agent_id not in agents:
        agents[agent_id] = VektorAgent(agent_id)
    return {"status": "registered", "agent_id": agent_id, "total_agents": len(agents)}

@app.post("/agent/run")
def run_agent(request: TaskRequest):
    if kill_switch.is_killed(request.agent_id):
        raise HTTPException(403, f"Agent {request.agent_id} is killed")
    
    if request.agent_id not in agents:
        agents[request.agent_id] = VektorAgent(request.agent_id)
    
    result = agents[request.agent_id].run(request.task, request.data)
    return result

@app.get("/agents")
def list_agents():
    return {"agents": list(agents.keys()), "count": len(agents)}

# ========== ADMIN ENDPOINTS ==========

@app.post("/admin/kill/{agent_id}")
def kill_agent(agent_id: str, x_admin_key: str = Header(...)):
    if x_admin_key != os.environ.get("ADMIN_API_KEY", "change_me"):
        raise HTTPException(401, "Invalid admin key")
    kill_switch.kill(agent_id)
    return {"status": "killed", "agent_id": agent_id}

@app.post("/admin/revive/{agent_id}")
def revive_agent(agent_id: str, x_admin_key: str = Header(...)):
    if x_admin_key != os.environ.get("ADMIN_API_KEY", "change_me"):
        raise HTTPException(401, "Invalid admin key")
    kill_switch.revive(agent_id)
    return {"status": "revived", "agent_id": agent_id}

# ========== MEMORY ENDPOINTS ==========

@app.get("/memory/{agent_id}")
def get_agent_memory(agent_id: str, limit: int = 50):
    episodes = memory.get_episodes(agent_id, limit)
    return {"agent_id": agent_id, "episodes": episodes, "count": len(episodes)}

@app.get("/context")
def get_shared_context():
    return memory.get_all_shared_context()

# ========== E-COMMERCE ENDPOINTS ==========

# Store catalogs in memory (in production, use DB)
catalogs = {}

@app.post("/ecommerce/catalog")
def upload_catalog(data: CatalogUpdate):
    catalogs[data.store_id] = data.products
    memory.update_shared_context(f"catalog_{data.store_id}", data.products, "api")
    return {"status": "catalog stored", "store_id": data.store_id, "product_count": len(data.products)}

@app.get("/ecommerce/trends/{store_id}")
def get_trending_matches(store_id: str):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found. Upload catalog first.")
    mapper = TrendToCatalogMapper(catalogs[store_id])
    result = mapper.run_weekly()
    mapper.close()
    return result

@app.get("/ecommerce/citation/{store_id}/{product_name}")
def get_citation_score(store_id: str, product_name: str):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found")
    
    product = next((p for p in catalogs[store_id] if p.get("name", "").lower() == product_name.lower()), None)
    if not product:
        raise HTTPException(404, f"Product '{product_name}' not found")
    
    optimizer = AICitationOptimizer()
    return optimizer.calculate_citation_score(product)

@app.get("/ecommerce/campaign/{store_id}/{product_name}")
def generate_campaign(store_id: str, product_name: str, trend: Optional[str] = None):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found")
    
    product = next((p for p in catalogs[store_id] if p.get("name", "").lower() == product_name.lower()), None)
    if not product:
        raise HTTPException(404, f"Product '{product_name}' not found")
    
    builder = ClickToMessageBuilder()
    sequence = builder.generate_sequence(product, trend)
    ad_copy = builder.generate_ad_copy(product, trend)
    
    return {
        "product": product.get("name"),
        "sequence": sequence,
        "ad_copy": ad_copy
    }

@app.get("/ecommerce/weekly-report/{store_id}")
def get_weekly_report(store_id: str):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found")
    
    generator = WeeklyReportGenerator(catalogs[store_id])
    report = generator.generate_full_report()
    generator.close()
    return {"report": report, "store_id": store_id}

@app.get("/ecommerce/social-export/{store_id}")
def export_social_csv(store_id: str, platform: str = "tiktok"):
    if store_id not in catalogs:
        raise HTTPException(404, "No catalog found")
    
    connector = SocialCommerceConnector()
    if platform == "tiktok":
        csv_data = connector.generate_tiktok_shop_csv(catalogs[store_id])
        return {"csv": csv_data, "format": "csv", "platform": "TikTok Shop"}
    elif platform == "instagram":
        return connector.generate_instagram_product_tags(catalogs[store_id])
    else:
        raise HTTPException(400, "Platform must be 'tiktok' or 'instagram'")

# ========== LLM ROUTING ENDPOINT ==========

class LLMRequest(BaseModel):
    prompt: str
    fallback: bool = True

@app.post("/llm/call")
async def call_llm(request: LLMRequest):
    router = FreeTierRouter()
    result = await router.call(request.prompt, request.fallback)
    return result

# ========== INTERFERENCE MERGE ENDPOINT ==========

class MergeRequest(BaseModel):
    responses: List[Dict[str, Any]]

@app.post("/merge")
def merge_responses(request: MergeRequest):
    result = InterferenceMerge.merge(request.responses)
    return result

# ========== PATTERN DETECTION ENDPOINT ==========

class PatternRequest(BaseModel):
    events: List[Dict[str, Any]]
    pattern: List[str]

@app.post("/pattern/detect")
def detect_pattern(request: PatternRequest):
    operator = SemanticPatternOperator()
    for event in request.events:
        operator.add_event(event)
    detected = operator.detect_pattern(request.pattern)
    return {"pattern": request.pattern, "detected": detected}
