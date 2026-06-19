"""
database.py - Complete data access layer for VektorFlow 15xr
"""
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

# ============ IN-MEMORY DATABASE ============
_users = {}
_stores = {}
_conversations = {}
_tasks = {}
_icp_data = {}
_preferences = {}
_memories = {}

# ============ USER FUNCTIONS ============
def get_user(email: str) -> Optional[Dict]:
    return _users.get(email)

def create_user(email: str, password: str, data: Dict = None) -> Dict:
    _users[email] = {
        "email": email,
        "password": password,
        "created_at": datetime.utcnow().isoformat(),
        "data": data or {}
    }
    return _users[email]

def get_user_stores(email: str) -> List[Dict]:
    return _stores.get(email, [])

def get_user_preferences(email: str) -> Dict:
    if email in _preferences:
        return _preferences[email]
    return {
        "theme": "dark",
        "notifications": True,
        "language": "en",
        "dashboard_layout": "default",
        "auto_optimize": True,
        "trend_alerts": True,
        "email_digest": "daily"
    }

def update_user_preferences(email: str, preferences: Dict) -> Dict:
    _preferences[email] = preferences
    return _preferences[email]

# ============ STORE FUNCTIONS ============
def connect_store(email: str, platform: str, store_url: str) -> Dict:
    if email not in _stores:
        _stores[email] = []
    
    store = {
        "platform": platform,
        "store_url": store_url,
        "connected_at": datetime.utcnow().isoformat()
    }
    _stores[email].append(store)
    return store

# ============ LLM FUNCTIONS ============
def get_llm_keys(email: str) -> Dict:
    return {
        "openai": os.environ.get("OPENAI_API_KEY", ""),
        "groq": os.environ.get("GROQ_API_KEY", ""),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY", "")
    }

# ============ ICP FUNCTIONS ============
def get_icp_data(email: str) -> Dict:
    if email in _icp_data:
        return _icp_data[email]
    return {
        "customer": "E-commerce store owners",
        "product_type": "dropshipping products",
        "target_audience": "Online shoppers aged 18-45",
        "pain_points": ["Finding winning products", "SEO optimization", "Supplier management"],
        "goals": ["Increase sales", "Automate operations", "Scale business"],
        "niche": "General merchandise"
    }

def save_icp_data(email: str, icp_data: Dict) -> Dict:
    _icp_data[email] = icp_data
    return icp_data

# ============ CONVERSATION FUNCTIONS ============
def save_conversation(email: str, user_message: str, ai_response: str, conversation_id: Optional[str] = None) -> str:
    if email not in _conversations:
        _conversations[email] = []
    
    if not conversation_id:
        conversation_id = f"conv_{datetime.utcnow().timestamp()}"
    
    _conversations[email].append({
        "conversation_id": conversation_id,
        "user_message": user_message,
        "ai_response": ai_response,
        "timestamp": datetime.utcnow().isoformat()
    })
    return conversation_id

def get_conversations(email: str, limit: int = 10) -> List[Dict]:
    convs = _conversations.get(email, [])
    return convs[-limit:]

# ============ MEMORY FUNCTIONS (BOTH SINGULAR AND PLURAL SUPPORTED) ============
def save_memory(email: str, key: str, value: Any) -> bool:
    """Save a memory item for a user (key-value store)"""
    try:
        if email not in _memories:
            _memories[email] = {}
        _memories[email][key] = {
            "value": value,
            "updated_at": datetime.utcnow().isoformat()
        }
        return True
    except Exception:
        return False

def get_memory(email: str, key: str) -> Optional[Any]:
    """Get a memory item for a user"""
    try:
        if email in _memories and key in _memories[email]:
            return _memories[email][key].get("value")
        return None
    except Exception:
        return None

# THIS FIXES YOUR SPECIFIC ERROR: 'get_all_memory' (singular)
def get_all_memory(email: str) -> Dict:
    """Get all memories for a user (SINGULAR version for compatibility)"""
    try:
        return _memories.get(email, {})
    except Exception:
        return {}

# THIS IS THE PLURAL VERSION (kept for compatibility)
def get_all_memories(email: str) -> Dict:
    """Get all memories for a user (PLURAL version for compatibility)"""
    try:
        return _memories.get(email, {})
    except Exception:
        return {}

def delete_memory(email: str, key: str) -> bool:
    """Delete a memory item for a user"""
    try:
        if email in _memories and key in _memories[email]:
            del _memories[email][key]
            return True
        return False
    except Exception:
        return False

# ============ TASK FUNCTIONS ============
def get_tasks(email: Optional[str] = None) -> List[Dict]:
    if email and email in _tasks:
        return _tasks[email]
    return [
        {"id": "1", "title": "Optimize product descriptions", "status": "in_progress", "priority": "high"},
        {"id": "2", "title": "Generate meta tags for 15 products", "status": "pending", "priority": "medium"},
        {"id": "3", "title": "Update schema markup", "status": "completed", "priority": "low"}
    ]

def create_task(email: str, title: str, description: str = "", priority: str = "medium") -> Dict:
    if email not in _tasks:
        _tasks[email] = []
    
    task = {
        "id": f"task_{len(_tasks[email]) + 1}",
        "title": title,
        "description": description,
        "status": "pending",
        "priority": priority,
        "created_at": datetime.utcnow().isoformat()
    }
    _tasks[email].append(task)
    return task

def update_task(email: str, task_id: str, updates: Dict) -> Optional[Dict]:
    tasks = _tasks.get(email, [])
    for task in tasks:
        if task.get("id") == task_id:
            task.update(updates)
            return task
    return None

# ============ INITIALIZE ============
create_user("commander@vektorflow.com", "vektorflow2026", {"role": "admin"})

print("✅ Database initialized with ALL required functions (including get_all_memory).")
print("   Username: commander@vektorflow.com")
print("   Password: vektorflow2026")