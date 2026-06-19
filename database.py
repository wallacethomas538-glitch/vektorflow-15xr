"""
database.py - Data access layer for VektorFlow 15xr
"""
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

# ============ SIMPLE IN-MEMORY DATABASE (FOR DEVELOPMENT) ============
# Replace this with PostgreSQL/Redis in production

_users = {}
_stores = {}
_conversations = {}
_tasks = {}
_icp_data = {}

def get_user(email: str) -> Optional[Dict]:
    """Get a user by email"""
    return _users.get(email)

def create_user(email: str, password: str, data: Dict = None) -> Dict:
    """Create a new user"""
    _users[email] = {
        "email": email,
        "password": password,
        "created_at": datetime.utcnow().isoformat(),
        "data": data or {}
    }
    return _users[email]

def get_user_stores(email: str) -> List[Dict]:
    """Get stores connected to a user"""
    return _stores.get(email, [])

def connect_store(email: str, platform: str, store_url: str) -> Dict:
    """Connect a store to a user"""
    if email not in _stores:
        _stores[email] = []
    
    store = {
        "platform": platform,
        "store_url": store_url,
        "connected_at": datetime.utcnow().isoformat()
    }
    _stores[email].append(store)
    return store

def get_llm_keys(email: str) -> Dict:
    """Get LLM API keys for a user"""
    # In production, fetch from database or environment
    return {
        "openai": os.environ.get("OPENAI_API_KEY", ""),
        "groq": os.environ.get("GROQ_API_KEY", ""),
        "anthropic": os.environ.get("ANTHROPIC_API_KEY", "")
    }

def get_icp_data(email: str) -> Dict:
    """Get ICP (Ideal Customer Profile) data for a user"""
    # Check if we have stored ICP data
    if email in _icp_data:
        return _icp_data[email]
    
    # Return default ICP
    return {
        "customer": "E-commerce store owners",
        "product_type": "dropshipping products",
        "target_audience": "Online shoppers aged 18-45",
        "pain_points": ["Finding winning products", "SEO optimization", "Supplier management"],
        "goals": ["Increase sales", "Automate operations", "Scale business"],
        "niche": "General merchandise"
    }

def save_icp_data(email: str, icp_data: Dict) -> Dict:
    """Save ICP data for a user"""
    _icp_data[email] = icp_data
    return icp_data

def save_conversation(email: str, user_message: str, ai_response: str, conversation_id: Optional[str] = None) -> str:
    """Save a conversation between user and AI"""
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
    """Get conversation history for a user"""
    convs = _conversations.get(email, [])
    return convs[-limit:]

def get_tasks(email: Optional[str] = None) -> List[Dict]:
    """Get tasks for a user"""
    if email and email in _tasks:
        return _tasks[email]
    
    # Return default tasks
    return [
        {"id": "1", "title": "Optimize product descriptions", "status": "in_progress", "priority": "high"},
        {"id": "2", "title": "Generate meta tags for 15 products", "status": "pending", "priority": "medium"},
        {"id": "3", "title": "Update schema markup", "status": "completed", "priority": "low"},
        {"id": "4", "title": "Analyze competitor keywords", "status": "pending", "priority": "high"}
    ]

def create_task(email: str, title: str, description: str = "", priority: str = "medium") -> Dict:
    """Create a new task"""
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
    """Update a task"""
    tasks = _tasks.get(email, [])
    for task in tasks:
        if task.get("id") == task_id:
            task.update(updates)
            return task
    return None

# ============ INITIALIZE WITH DEFAULT USER ============
create_user("commander@vektorflow.com", "vektorflow2026", {"role": "admin"})

print("✅ Database initialized with default user.")
print("   Username: commander@vektorflow.com")
print("   Password: vektorflow2026")