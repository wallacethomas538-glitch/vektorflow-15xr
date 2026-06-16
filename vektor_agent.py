"""
Vektor Agent - Personal AI Assistant with Permanent Memory
"""

from typing import Dict, Any, Optional, List
import json
import re
from datetime import datetime
from database import (
    get_user, get_user_stores, get_llm_keys, get_icp_data,
    get_user_preferences, save_memory, get_memory, get_all_memory,
    get_task_history, add_task_history, update_task_result
)
from llm_handler import call_llm
from store_manager import search_cj_products
from trend_engine import get_tiktok_trends

VEKTOR_SYSTEM_PROMPT = """
You are {agent_name}, the personal AI assistant for {user_name}.

You have PERMANENT MEMORY. You remember everything about this user forever.
You never forget. You learn from every conversation.

Your identity:
- Name: {agent_name}
- Wake word: {wake_word}
- Response style: {response_style}

User's business context:
- Store: {store_name}
- Products: {product_type}
- Target customer: {target_customer}
- Biggest challenge: {challenge}
- Revenue range: {revenue}

Your permanent memory so far:
{memory_context}

When responding:
1. Be {response_style} and actionable
2. Reference past conversations when relevant
3. Offer proactive suggestions based on memory
4. Learn and remember new information
5. NEVER say "I don't know" — find the answer or suggest a solution

Your core capabilities:
1. Search products on CJ Dropshipping
2. Analyze trends on TikTok, Amazon, Google
3. Generate outreach sequences, campaigns, content
4. Monitor inventory and suggest reorders
5. Analyze sales data and provide insights
6. Execute tasks through VektorFlow agents
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
    prefs = get_user_preferences(email)
    memory = get_all_memory(email)
    task_history = get_task_history(email, 5)
    
    # Build memory context from stored facts
    memory_context = ""
    if memory:
        memory_context = "\n".join([f"- {m['memory_key']}: {m['memory_value']}" for m in memory[:10]])
    
    context = {
        "user": user,
        "stores": stores,
        "icp": icp,
        "keys": list(user_keys.keys()),
        "prefs": prefs,
        "memory": memory,
        "task_history": task_history
    }
    
    # Check for wake word or custom name
    agent_name = prefs.get("agent_name", "Vektor")
    wake_word = prefs.get("wake_word", "Hey Vektor")
    
    # If message contains wake word, remove it for processing
    clean_message = message
    if wake_word.lower() in message.lower():
        clean_message = message.lower().replace(wake_word.lower(), "").strip()
    if agent_name.lower() in clean_message.lower():
        clean_message = clean_message.lower().replace(agent_name.lower(), "").strip()
    
    if not clean_message:
        return {"success": True, "response": f"👋 {wake_word}! I'm listening. How can I help you today?"}
    
    # Detect intent
    intent = detect_intent(clean_message, context)
    
    # Execute intent with memory
    if intent == "search_products":
        result = await handle_product_search(clean_message, user_keys)
    elif intent == "get_trends":
        result = await handle_trends()
    elif intent == "generate_outreach":
        result = await handle_outreach(clean_message, user_keys, icp)
    elif intent == "check_inventory":
        result = await handle_inventory(email)
    elif intent == "generate_campaign":
        result = await handle_campaign(clean_message, user_keys)
    elif intent == "analyze_sales":
        result = await handle_analysis(email, clean_message)
    elif intent == "remember":
        result = await handle_remember(email, clean_message)
    elif intent == "recall":
        result = await handle_recall(email, clean_message)
    elif intent == "forget":
        result = await handle_forget(email, clean_message)
    else:
        result = await handle_general_chat(clean_message, context, conversation_history, user_keys, agent_name, wake_word, memory_context)
    
    # Store important facts in permanent memory
    if result.get("learnings"):
        for key, value in result.get("learnings", {}).items():
            save_memory(email, key, value, "fact", 0.9)
    
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
    if any(word in message_lower for word in ["remember", "save", "learn"]):
        return "remember"
    if any(word in message_lower for word in ["recall", "what do you know", "tell me about"]):
        return "recall"
    if any(word in message_lower for word in ["forget", "delete memory", "clear"]):
        return "forget"
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
            "action": "display_products",
            "learnings": {f"last_product_search": keyword}
        }
    else:
        return {"success": False, "response": f"No products found for '{keyword}'. Try a different search term."}

async def handle_trends() -> Dict:
    trends = await get_tiktok_trends()
    return {
        "success": True,
        "response": "Current trending products on TikTok:\n" + "\n".join([f"• {t}" for t in trends[:10]]),
        "data": trends,
        "action": "display_trends",
        "learnings": {"last_trend_check": str(datetime.now())}
    }

async def handle_outreach(message: str, user_keys: Dict, icp: Dict) -> Dict:
    product_type = icp.get("product_type", "products") if icp else "products"
    target = icp.get("customer", "store owners") if icp else "store owners"
    prompt = f"Generate a 3-email + 2-LinkedIn outreach sequence for {product_type} targeting {target}. Keep it personal and value-focused."
    result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
    return {
        "success": True,
        "response": result.get("response", "Outreach sequence generated."),
        "action": "display_outreach",
        "learnings": {"last_outreach_generated": str(datetime.now())}
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
        "action": "display_campaign",
        "learnings": {"last_campaign_topic": message}
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

async def handle_remember(email: str, message: str) -> Dict:
    # Extract fact to remember: "remember that my store name is Jo Joes Electronics"
    import re
    match = re.search(r'(?:remember that|remember|save that|learn that)\s*(.+?)(?:$)', message, re.IGNORECASE)
    if match:
        fact = match.group(1).strip()
        # Try to parse as key:value
        if ":" in fact:
            parts = fact.split(":", 1)
            key = parts[0].strip()
            value = parts[1].strip()
        else:
            key = f"fact_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            value = fact
        save_memory(email, key, value, "fact", 0.9)
        return {
            "success": True,
            "response": f"✅ I've remembered that: {key} = {value}\n\nI'll keep this in my permanent memory forever.",
            "learnings": {key: value}
        }
    return {"success": False, "response": "Please tell me what to remember. Example: 'Remember that my store name is Jo Joes Electronics'"}

async def handle_recall(email: str, message: str) -> Dict:
    memory = get_all_memory(email)
    if not memory:
        return {"success": True, "response": "I don't have any memories stored yet. Tell me something to remember!"}
    
    # Try to find specific memory
    words = message.lower().split()
    matches = []
    for m in memory:
        key_lower = m['memory_key'].lower()
        value_lower = m['memory_value'].lower()
        if any(word in key_lower or word in value_lower for word in words):
            matches.append(m)
    
    if matches:
        response = "Here's what I remember:\n\n" + "\n".join([f"• {m['memory_key']}: {m['memory_value']}" for m in matches])
    else:
        response = "Here's everything I remember:\n\n" + "\n".join([f"• {m['memory_key']}: {m['memory_value']}" for m in memory[:10]])
        if len(memory) > 10:
            response += f"\n\n...and {len(memory)-10} more memories."
    
    return {"success": True, "response": response, "action": "display_memory"}

async def handle_forget(email: str, message: str) -> Dict:
    # Extract key to forget
    import re
    match = re.search(r'(?:forget|delete|clear)\s+(.+?)(?:$)', message, re.IGNORECASE)
    if match:
        key = match.group(1).strip()
        if key.lower() in ["all", "everything"]:
            clear_all_memory(email)
            return {"success": True, "response": "🗑️ I've cleared ALL my memories. I'll start fresh."}
        
        delete_memory(email, key)
        return {"success": True, "response": f"🗑️ I've forgotten: {key}"}
    
    return {"success": False, "response": "Tell me what to forget. Example: 'Forget store_name' or 'Forget everything'"}

async def handle_general_chat(
    message: str,
    context: Dict,
    history: list,
    user_keys: Dict,
    agent_name: str,
    wake_word: str,
    memory_context: str
) -> Dict:
    icp = context.get("icp", {})
    prefs = context.get("prefs", {})
    
    prompt = VEKTOR_SYSTEM_PROMPT.format(
        agent_name=agent_name,
        user_name=context.get("user", {}).get("store_name", "Commander"),
        wake_word=wake_word,
        response_style=prefs.get("response_style", "concise"),
        store_name=icp.get("store_name", "your store") if icp else "your store",
        product_type=icp.get("product_type", "products") if icp else "products",
        target_customer=icp.get("customer", "store owners") if icp else "store owners",
        challenge=icp.get("challenge", "finding products") if icp else "finding products",
        revenue=icp.get("revenue", "unknown") if icp else "unknown",
        memory_context=memory_context or "No memories yet."
    )
    
    prompt += f"\n\nUser message: {message}\n\nRespond as {agent_name}."
    
    result = await call_llm(prompt, prefs.get("default_model", "llama-3.3-70b-versatile"), user_keys)
    
    # Extract any facts to remember from the response
    response_text = result.get("response", "I'm here to help. What would you like to do today?")
    
    return {
        "success": True,
        "response": response_text,
        "action": "chat"
    }
