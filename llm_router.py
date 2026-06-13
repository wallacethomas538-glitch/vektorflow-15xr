import httpx
import os
from typing import Dict, Optional

async def call_groq(prompt: str, api_key: str) -> Optional[str]:
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "mixtral-8x7b-32768",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except:
        pass
    return None

async def call_gemini(prompt: str, api_key: str) -> Optional[str]:
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    except:
        pass
    return None

async def call_huggingface(prompt: str, api_key: str) -> Optional[str]:
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"inputs": prompt}
            )
            if response.status_code == 200:
                data = response.json()
                return data[0].get("generated_text", "")
    except:
        pass
    return None

async def route_llm(prompt: str, model: str, user_keys: Dict) -> Dict:
    providers = {
        "groq": (call_groq, user_keys.get("groq_key")),
        "gemini": (call_gemini, user_keys.get("gemini_key")),
        "huggingface": (call_huggingface, user_keys.get("hf_key"))
    }
    
    if model not in providers:
        model = "groq"
    
    func, api_key = providers[model]
    response = await func(prompt, api_key)
    
    if response:
        return {"success": True, "provider": model, "response": response}
    
    # Fallback to any available provider
    for fallback_model, (fallback_func, fallback_key) in providers.items():
        if fallback_key and fallback_model != model:
            response = await fallback_func(prompt, fallback_key)
            if response:
                return {"success": True, "provider": fallback_model, "response": response, "fallback": True}
    
    return {"success": False, "error": "No LLM providers available. Add an API key."}
