"""
VektorFlow 15xr - LLM Router
"""

import os
import httpx
from typing import Dict, Optional

async def call_groq(prompt: str, api_key: str, model: str) -> Optional[str]:
    if not api_key:
        return None
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                print(f"Groq API error: {response.status_code}")
                return None
    except Exception as e:
        print(f"Groq exception: {str(e)}")
        return None

async def route_llm(prompt: str, model: str, user_keys: Dict) -> Dict:
    groq_key = user_keys.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
    
    if not groq_key:
        return {"success": False, "error": "No Groq API key found. Add it in Your API Keys section."}
    
    response = await call_groq(prompt, groq_key, model)
    if response:
        return {"success": True, "provider": "groq", "response": response, "model": model}
    else:
        return {"success": False, "error": "Groq request failed. Check your API key."}
