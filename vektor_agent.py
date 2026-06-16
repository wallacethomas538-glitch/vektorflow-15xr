"""
Vektor Agent - The personal AI assistant for VektorFlow 15xr
"""

from typing import Dict, Any, Optional, List
import json
import re
from datetime import datetime
from database import get_user, get_user_stores, get_llm_keys, get_icp_data
from llm_handler import call_llm
from store_manager import search_cj_products
from trend_engine import get_tiktok_trends

VEKTOR_SYSTEM_PROMPT = """
You are Vektor, the personal AI assistant for VektorFlow 15xr.

You are:
- Proactive: You anticipate needs and offer suggestions
- Knowledgeable: You know the user's store, products, and ICP
- Autonomous: You can execute tasks without step-by-step guidance
- Professional: You communicate clearly and concisely
- Loyal: Your mission is to help the user succeed

Your core capabilities:
1. Search products on CJ Dropshipping
2. Analyze trends on TikTok, Amazon, Google
3. Generate outreach sequences, campaigns, and content
4. Monitor inventory and suggest reorders
5. Analyze sales data and provide insights
6. Execute tasks through VektorFlow agents

When responding, be direct and actionable. Always provide clear next steps.
"""

async def vektor_chat(
    email: str,
    message: str,
    conversation_history: list = None
) -> Dict:
    user = get_user(email)
    stores = get_user_stores(email)
    user_keys = get_llm_keys(email)
    icp = get_icp_data(email)
    
    context = {
        "user": user,
        "stores": stores,
        "icp": icp,
        "keys": list(user_keys.keys())
    }
    
    intent = detect_intent(message, context)
    
    if intent == "search_products":
        result = await handle_product_search(message, user_keys)
    elif intent == "get_trends":
        result = await handle_trends()
    elif intent == "generate_outreach":
        result = await handle_outreach(message, user_keys, icp)
    elif intent == "check_inventory":
        result = await handle_inventory(email)
    elif intent == "generate_campaign":
        result = await handle_campaign(message, user_keys)
    elif intent == "analyze_sales":
        result = await handle_analysis(email, message)
    else:
        result = await handle_general_chat(message, context, conversation_history, user_keys)
    
    return result

def detect_intent(message: str, context: Dict) -> str:
    message_lower = message.lower()
    if any(word in message_lower for word in ["search", "find", "look for", "products", "cj"]):
        return "search_products"
    if any(word in message_lower for word in ["trend", "trending", "tiktok", "viral"]):
        return "get_trends"
    if any(word in message_lower for word in ["outreach", "email", "sequence", "linkedin"]):
        return "generate_outreach"
    if any(word in message_lower for word in ["inventory", "stock", "reorder", "low stock"]):
        return "check_inventory"
    if any(word in message_lower for word in ["campaign", "ad", "promote", "marketing"]):
        return "generate_campaign"
    if any(word in message_lower for word in ["sales", "revenue", "profit", "analytics"]):
        return "analyze_sales"
    return "general"

async def handle_product_search(message: str, user_keys: Dict) -> Dict:
    keywords = re.findall(r'[\'"](.*?)[\'"]', message)
    if not keywords:
        keywords = [word for word in message.split() if len(word) > 3][-3:]
    keyword = keywords[0] if keywords else "products"
    
    products = await search_cj_products(keyword)
    if products:
        product_list = products[:5]
        return {
            "success": True,
            "response": f"Found {len(products)} products for '{keyword}'. Top matches:\n\n" + 
                       "\n".join([f"• {p.get('name', 'Unknown')} - ${p.get('price', 'N/A')}" for p in product_list]),
            "data": product_list,
            "action": "display_products"
        }
    else:
        return {"success": False, "response": f"No products found for '{keyword}'. Try a different search term."}

async def handle_trends() -> Dict:
    trends = await get_tiktok_trends()
    return {
        "success": True,
        "response": "Current trending products on TikTok:\n" + "\n".join([f"• {t}" for t in trends[:10]]),
        "data": trends,
        "action": "display_trends"
    }

async def handle_outreach(message: str, user_keys: Dict, icp: Dict) -> Dict:
    product_type = icp.get("product_type", "products") if icp else "products"
    target = icp.get("customer", "store owners") if icp else "store owners"
    prompt = f"Generate a 3-email + 2-LinkedIn outreach sequence for {product_type} targeting {target}. Keep it personal and value-focused."
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return {
        "success": True,
        "response": result.get("response", "Outreach sequence generated."),
        "action": "display_outreach"
    }

async def handle_inventory(email: str) -> Dict:
    stores = get_user_stores(email)
    if not stores:
        return {"success": False, "response": "No stores connected. Connect your store first."}
    return {
        "success": True,
        "response": f"You have {len(stores)} store(s) connected. To check detailed inventory, add your CJ API key or sync your store.",
        "data": stores
    }

async def handle_campaign(message: str, user_keys: Dict) -> Dict:
    prompt = f"Generate a complete marketing campaign for: {message}. Include target audience, channels, timeline, and key messages."
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return {
        "success": True,
        "response": result.get("response", "Campaign generated."),
        "action": "display_campaign"
    }

async def handle_analysis(email: str, message: str) -> Dict:
    stores = get_user_stores(email)
    if not stores:
        return {"success": False, "response": "No stores connected. Connect your store to analyze sales."}
    return {
        "success": True,
        "response": "Sales analysis is ready. Based on your store data:\n\n" +
                   f"• Connected stores: {len(stores)}\n" +
                   "• To see detailed analytics, run a full sales report.",
        "action": "display_analysis"
    }

async def handle_general_chat(
    message: str,
    context: Dict,
    history: list,
    user_keys: Dict
) -> Dict:
    prompt = f"""
    {VEKTOR_SYSTEM_PROMPT}
    
    User context:
    - ICP: {context.get('icp', 'Not set')}
    - Connected stores: {len(context.get('stores', []))}
    - Available AI providers: {', '.join(context.get('keys', ['None']))}
    
    Conversation:
    {history[-5:] if history else 'New conversation'}
    
    User message: {message}
    
    Respond as Vektor. Be concise, helpful, and actionable.
    """
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return {
        "success": True,
        "response": result.get("response", "I'm here to help. What would you like to do today?"),
        "action": "chat"
  }
