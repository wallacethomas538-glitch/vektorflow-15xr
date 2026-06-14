"""
VektorFlow 15xr - LLM Router
"""

import os
import httpx
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
                    "model": "llama-3.3-70b-versatile",
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
            else:
                return None
    except Exception:
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
                if isinstance(data, list) and len(data) > 0:
                    return data[0].get("generated_text", "")
                return str(data)
            else:
                return None
    except Exception:
        return None

async def route_llm(prompt: str, model: str, user_keys: Dict) -> Dict:
    groq_key = user_keys.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
    gemini_key = user_keys.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    hf_key = user_keys.get("hf_api_key") or os.environ.get("HF_API_KEY")
    
    if model == "groq":
        if not groq_key:
            return {"success": False, "error": "No Groq API key found"}
        response = await call_groq(prompt, groq_key)
        if response:
            return {"success": True, "provider": "groq", "response": response}
        else:
            return {"success": False, "error": "Groq request failed"}
    
    elif model == "gemini":
        if not gemini_key:
            return {"success": False, "error": "No Gemini API key found"}
        response = await call_gemini(prompt, gemini_key)
        if response:
            return {"success": True, "provider": "gemini", "response": response}
        else:
            return {"success": False, "error": "Gemini request failed"}
    
    elif model == "huggingface":
        if not hf_key:
            return {"success": False, "error": "No Hugging Face API key found"}
        response = await call_huggingface(prompt, hf_key)
        if response:
            return {"success": True, "provider": "huggingface", "response": response}
        else:
            return {"success": False, "error": "Hugging Face request failed"}
    
    else:
        return {"success": False, "error": f"Unknown model: {model}"}
