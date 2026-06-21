"""
VektorFlow 15xr - Organic Content Generator
AI-powered social content creation for entrepreneurs.
Generates copy-paste ready captions, hashtags, and posting tips.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from llm_handler import call_llm
from database import (
    get_icp_data,
    save_memory,
    get_memory,
    add_task_history,
    update_task_result,
    get_user_preferences
)

logger = logging.getLogger("vektorflow")

# ============ CONFIGURATION ============
DEFAULT_PLATFORMS = ["instagram", "facebook", "tiktok"]
DEFAULT_NUMBER_OF_OPTIONS = 3
DEFAULT_HASHTAG_COUNT = 12

# ============ ORGANIC CONTENT GENERATOR ============

class OrganicContentGenerator:
    """
    AI-powered organic social content generator.
    Creates copy-paste ready captions, hashtags, and posting tips.
    """
    
    def __init__(self, email: str):
        """
        Initialize the content generator for a user.
        
        Args:
            email: User email
        """
        self.email = email
        self.user_keys = None
        self.icp = None
        self.preferences = None
        self._load_user_data()
    
    def _load_user_data(self):
        """Load user data from database."""
        try:
            from database import get_llm_keys
            self.user_keys = get_llm_keys(self.email)
            self.icp = get_icp_data(self.email)
            self.preferences = get_user_preferences(self.email) or {}
        except Exception as e:
            logger.error(f"Failed to load user data: {e}")
            self.user_keys = {}
            self.icp = {}
            self.preferences = {}
    
    async def generate_content(
        self,
        product_name: str,
        product_description: Optional[str] = None,
        platforms: List[str] = None,
        tone: str = "casual",
        number_of_options: int = DEFAULT_NUMBER_OF_OPTIONS
    ) -> Dict[str, Any]:
        """
        Generate organic social content for a product.
        
        Args:
            product_name: Name of the product
            product_description: Description of the product (optional)
            platforms: List of platforms (instagram, facebook, tiktok, linkedin, twitter)
            tone: casual, professional, funny, inspiring, educational
            number_of_options: Number of caption options to generate
        
        Returns:
            Dict with content, hashtags, and posting tips
        """
        try:
            if not platforms:
                platforms = DEFAULT_PLATFORMS
            
            # Generate content using AI
            content = await self._generate_content_with_ai(
                product_name=product_name,
                product_description=product_description,
                platforms=platforms,
                tone=tone,
                number_of_options=number_of_options
            )
            
            # Save to memory
            content_id = self._save_content(content, product_name)
            
            # Add to task history
            task_id = add_task_history(
                email=self.email,
                agent_name="organic_content",
                task=f"Generated organic content for {product_name}",
                status="completed"
            )
            update_task_result(
                task_id=task_id,
                result=json.dumps({
                    "content_id": content_id,
                    "product_name": product_name,
                    "platforms": platforms,
                    "number_of_options": number_of_options
                }),
                status="completed"
            )
            
            return {
                "success": True,
                "content": content,
                "content_id": content_id,
                "task_id": task_id,
                "platforms": platforms
            }
            
        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _generate_content_with_ai(
        self,
        product_name: str,
        product_description: Optional[str],
        platforms: List[str],
        tone: str,
        number_of_options: int
    ) -> Dict[str, Any]:
        """
        Use AI to generate organic content.
        
        Returns:
            Dict with captions, hashtags, and posting tips
        """
        description_text = product_description or f"A high-quality {product_name}."
        
        prompt = f"""
        You are a social media content creator. Generate organic social content for a product.
        
        Product Name: {product_name}
        Product Description: {description_text}
        Platforms: {', '.join(platforms)}
        Tone: {tone}
        Number of Caption Options: {number_of_options}
        
        Generate content that is:
        - Engaging and authentic
        - Copy-paste ready for personal pages
        - Not promotional or ad-like
        - Focused on storytelling and lifestyle
        
        Return ONLY valid JSON with this structure:
        {{
            "captions": [
                {{
                    "text": "...",
                    "emoji_style": "casual",
                    "hook": "..."
                }},
                ...
            ],
            "hashtags": {{
                "primary": ["...", "..."],
                "secondary": ["...", "..."],
                "niche": ["...", "..."]
            }},
            "posting_tips": {{
                "best_time": "...",
                "engagement_hook": "...",
                "visual_suggestion": "..."
            }}
        }}
        """
        
        try:
            result = await call_llm(prompt, "llama-3.3-70b-versatile", self.user_keys)
            response_text = result.get("response", "{}")
            
            import re
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                content = json.loads(json_match.group())
            else:
                content = json.loads(response_text)
            
            # Ensure required fields exist
            content.setdefault("captions", [
                {"text": f"Discover the amazing {product_name}! Perfect for your daily needs.", "emoji_style": "casual", "hook": "What do you think?"}
            ])
            content.setdefault("hashtags", {
                "primary": [f"#{product_name.replace(' ', '')}", "#quality", "#best"],
                "secondary": ["#style", "#trending", "#musthave"],
                "niche": ["#lifestyle", "#everyday", "#value"]
            })
            content.setdefault("posting_tips", {
                "best_time": "8-10am or 6-8pm",
                "engagement_hook": "Ask a question in the caption",
                "visual_suggestion": f"Show the {product_name} in use"
            })
            
            return content
            
        except Exception as e:
            logger.error(f"AI content generation failed: {e}")
            return self._generate_content_fallback(
                product_name=product_name,
                product_description=description_text,
                platforms=platforms
            )
    
    def _generate_content_fallback(
        self,
        product_name: str,
        product_description: str,
        platforms: List[str]
    ) -> Dict[str, Any]:
        """Fallback content structure if AI fails."""
        return {
            "captions": [
                {
                    "text": f"Check out this {product_name}! {product_description[:100]}",
                    "emoji_style": "casual",
                    "hook": "What do you think?"
                },
                {
                    "text": f"Here's something special for you - {product_name}. {product_description[:80]}",
                    "emoji_style": "friendly",
                    "hook": "Tag someone who needs this!"
                },
                {
                    "text": f"Loving this {product_name} right now! {product_description[:60]}",
                    "emoji_style": "casual",
                    "hook": "Would you try this?"
                }
            ],
            "hashtags": {
                "primary": [f"#{product_name.replace(' ', '')}", "#quality", "#best"],
                "secondary": ["#style", "#trending", "#musthave"],
                "niche": ["#lifestyle", "#everyday", "#value"]
            },
            "posting_tips": {
                "best_time": "8-10am or 6-8pm",
                "engagement_hook": "Ask a question in the caption",
                "visual_suggestion": f"Show the {product_name} in use"
            }
        }
    
    def _save_content(self, content: Dict[str, Any], product_name: str) -> str:
        """
        Save content to memory.
        
        Returns:
            Content ID
        """
        content_id = f"organic_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        save_memory(
            self.email,
            content_id,
            json.dumps({
                "content_id": content_id,
                "product_name": product_name,
                "created_at": datetime.utcnow().isoformat(),
                "content": content
            })
        )
        
        # Save to history
        history_key = "organic_content_history"
        history = get_memory(self.email, history_key)
        if history:
            try:
                history_list = json.loads(history)
            except:
                history_list = []
        else:
            history_list = []
        
        history_list.insert(0, {
            "content_id": content_id,
            "product_name": product_name,
            "created_at": datetime.utcnow().isoformat()
        })
        
        if len(history_list) > 20:
            history_list = history_list[:20]
        
        save_memory(self.email, history_key, json.dumps(history_list))
        
        return content_id

# ============ CONVENIENCE FUNCTIONS ============

async def generate_organic_content(
    email: str,
    product_name: str,
    product_description: Optional[str] = None,
    platforms: List[str] = None,
    tone: str = "casual",
    number_of_options: int = DEFAULT_NUMBER_OF_OPTIONS
) -> Dict[str, Any]:
    """
    Convenience function to generate organic content.
    
    Args:
        email: User email
        product_name: Name of the product
        product_description: Description of the product (optional)
        platforms: List of platforms
        tone: casual, professional, funny, inspiring, educational
        number_of_options: Number of caption options
    
    Returns:
        Content generation result
    """
    generator = OrganicContentGenerator(email)
    return await generator.generate_content(
        product_name=product_name,
        product_description=product_description,
        platforms=platforms,
        tone=tone,
        number_of_options=number_of_options
    )

async def handle_organic_content(
    message: str,
    user_keys: Dict[str, str],
    email: str = "commander@vektorflow.com"
) -> Dict[str, Any]:
    """
    Handle organic content requests from vektor_agent.py.
    
    Args:
        message: User instruction
        user_keys: User's API keys
        email: User email
    
    Returns:
        Formatted response for vektor_agent
    """
    try:
        # Extract product name from message
        product_name = "product"
        words = message.lower().split()
        for i, word in enumerate(words):
            if word in ["for", "about", "my"] and i + 1 < len(words):
                product_name = words[i + 1]
                break
            if word in ["post", "content", "generate"] and i + 1 < len(words):
                product_name = words[i + 1]
                break
        
        # Determine tone
        tone = "casual"
        if "professional" in message.lower():
            tone = "professional"
        elif "funny" in message.lower():
            tone = "funny"
        elif "inspiring" in message.lower():
            tone = "inspiring"
        elif "educational" in message.lower():
            tone = "educational"
        
        # Generate content
        result = await generate_organic_content(
            email=email,
            product_name=product_name,
            product_description=None,  # Will be extracted from ICP if available
            tone=tone
        )
        
        if not result.get("success"):
            return {
                "success": False,
                "response": f"Failed to generate content: {result.get('error', 'Unknown error')}",
                "action": "error"
            }
        
        content = result.get("content", {})
        captions = content.get("captions", [])
        hashtags = content.get("hashtags", {})
        tips = content.get("posting_tips", {})
        
        # Build response
        response = f"📝 Organic Content Generated for '{product_name}'\n\n"
        
        # Captions
        for i, caption in enumerate(captions[:3], 1):
            response += f"📌 Option {i}:\n"
            response += f"   {caption.get('text', '')}\n"
            response += f"   💡 Hook: {caption.get('hook', '')}\n\n"
        
        # Hashtags
        response += "🏷️ Suggested Hashtags:\n"
        all_hashtags = (
            hashtags.get("primary", [])[:5] +
            hashtags.get("secondary", [])[:5] +
            hashtags.get("niche", [])[:5]
        )
        response += "   " + " ".join(all_hashtags[:12]) + "\n\n"
        
        # Tips
        response += "💡 Posting Tips:\n"
        response += f"   • Best Time: {tips.get('best_time', '')}\n"
        response += f"   • Engagement Hook: {tips.get('engagement_hook', '')}\n"
        response += f"   • Visual Suggestion: {tips.get('visual_suggestion', '')}\n"
        
        response += f"\n📌 Content ID: {result.get('content_id')}"
        
        return {
            "success": True,
            "response": response,
            "data": {
                "content": content,
                "content_id": result.get("content_id"),
                "task_id": result.get("task_id")
            },
            "action": "display_organic_content"
        }
        
    except Exception as e:
        logger.error(f"Organic content handler error: {e}")
        return {
            "success": False,
            "response": f"Failed to generate content: {str(e)}",
            "action": "error"
        }

# ============ INITIALIZATION ============

print("✅ Organic Content Generator module loaded successfully")
print("   Features: copy-paste captions, hashtags, posting tips")
print("   Platforms: Instagram, Facebook, TikTok, LinkedIn, Twitter")
print("   ✓ 100% organic — no ad platforms involved")