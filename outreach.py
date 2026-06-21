"""
VektorFlow 15xr - Outreach Generator
AI-powered email and LinkedIn sequence generator.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from llm_handler import call_llm
from database import (
    get_icp_data,
    save_memory,
    add_task_history,
    update_task_result,
    get_user_preferences
)

logger = logging.getLogger("vektorflow")

async def generate_outreach_sequence(
    product_type: str,
    target_audience: str,
    pain_points: List[str],
    goals: List[str],
    user_keys: Dict[str, str],
    platform: str = "email",  # "email" or "linkedin"
    sequence_length: int = 3,
    preferences: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Generate a complete outreach sequence.
    
    Args:
        product_type: Type of product being sold
        target_audience: Who we're targeting
        pain_points: Customer pain points
        goals: Customer goals
        user_keys: User's API keys
        platform: "email" or "linkedin"
        sequence_length: Number of messages in sequence
        preferences: User preferences
    
    Returns:
        Dict with generated outreach sequence
    """
    # Get user preferences
    if not preferences:
        preferences = {}
    response_style = preferences.get("response_style", "concise")
    
    prompt = f"""
    You are an expert copywriter specializing in dropshipping outreach.
    
    Product Type: {product_type}
    Target Audience: {target_audience}
    Pain Points: {', '.join(pain_points)}
    Goals: {', '.join(goals)}
    Platform: {platform}
    Number of Messages: {sequence_length}
    Response Style: {response_style}
    
    Generate a complete outreach sequence that:
    1. Grabs attention in the first line
    2. Addresses pain points
    3. Presents the solution
    4. Includes a clear call to action
    
    Return ONLY valid JSON with this structure:
    {{
        "sequence": [
            {{
                "subject": "..." (for emails) or "title": "..." (for LinkedIn),
                "body": "...",
                "cta": "..."
            }},
            ...
        ],
        "best_time": "Tuesday 10am",
        "follow_up_days": [1, 3, 7]
    }}
    """
    
    try:
        result = await call_llm(prompt, "llama-3.3-70b-versatile", user_keys)
        response_text = result.get("response", "{}")
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
        else:
            data = json.loads(response_text)
        
        return data
    except Exception as e:
        logger.error(f"Outreach generation failed: {e}")
        return {
            "sequence": [
                {
                    "subject": f"Boost your {product_type} sales",
                    "body": f"Hi there,\n\nI noticed you're in the {target_audience} space. We help businesses like yours overcome {pain_points[0] if pain_points else 'common challenges'}.\n\nLet's chat about how we can help you achieve {goals[0] if goals else 'your goals'}.\n\nBest,\nVektorFlow Team",
                    "cta": "Reply to this email to set up a time."
                }
            ],
            "best_time": "Tuesday 10am",
            "follow_up_days": [1, 3, 7],
            "error": "Fallback response used"
        }

async def save_outreach_sequence(
    email: str,
    sequence: Dict[str, Any],
    product_type: str,
    target_audience: str
) -> str:
    """
    Save an outreach sequence to memory and task history.
    
    Args:
        email: User email
        sequence: Generated sequence
        product_type: Product type
        target_audience: Target audience
    
    Returns:
        Task ID
    """
    # Save to memory
    memory_key = f"outreach_{product_type[:20].lower().replace(' ', '_')}"
    save_memory(email, memory_key, json.dumps(sequence))
    
    # Add to task history
    task_id = add_task_history(
        email=email,
        agent_name="outreach_generator",
        task=f"Generated outreach for {product_type} targeting {target_audience}",
        status="completed"
    )
    update_task_result(task_id, json.dumps(sequence), status="completed")
    
    return task_id

async def get_saved_outreach(email: str, product_type: str) -> Optional[Dict]:
    """
    Retrieve a saved outreach sequence.
    
    Args:
        email: User email
        product_type: Product type
    
    Returns:
        Saved sequence or None
    """
    memory_key = f"outreach_{product_type[:20].lower().replace(' ', '_')}"
    from database import get_memory
    data = get_memory(email, memory_key)
    if data:
        return json.loads(data)
    return None

async def handle_outreach(
    message: str,
    user_keys: Dict[str, str],
    icp: Dict[str, Any],
    email: str = "commander@vektorflow.com"
) -> Dict[str, Any]:
    """
    Main entry point for outreach generation.
    Called by vektor_agent.py when intent is detected.
    
    Args:
        message: User instruction
        user_keys: User's API keys
        icp: ICP data
        email: User email
    
    Returns:
        Dict with outreach results
    """
    try:
        # Extract product type from ICP or message
        product_type = icp.get("product_type", "dropshipping products")
        target_audience = icp.get("customer", "store owners")
        pain_points = icp.get("pain_points", ["finding winning products"])
        goals = icp.get("goals", ["increase sales"])
        
        # Get preferences
        preferences = get_user_preferences(email) or {}
        
        # Generate outreach
        result = await generate_outreach_sequence(
            product_type=product_type,
            target_audience=target_audience,
            pain_points=pain_points,
            goals=goals,
            user_keys=user_keys,
            platform="email",
            sequence_length=3,
            preferences=preferences
        )
        
        # Save sequence
        task_id = await save_outreach_sequence(
            email=email,
            sequence=result,
            product_type=product_type,
            target_audience=target_audience
        )
        
        return {
            "success": True,
            "response": f"Outreach sequence generated for {product_type} targeting {target_audience}.",
            "sequence": result.get("sequence", []),
            "best_time": result.get("best_time", "Tuesday 10am"),
            "follow_up_days": result.get("follow_up_days", [1, 3, 7]),
            "task_id": task_id,
            "action": "display_outreach"
        }
        
    except Exception as e:
        logger.error(f"Outreach handler error: {e}")
        return {
            "success": False,
            "response": f"Failed to generate outreach: {str(e)}"
        }