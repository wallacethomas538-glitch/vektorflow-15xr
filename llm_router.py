"""
VektorFlow 15xr - LLM Router
Handles Groq, Gemini, Hugging Face, and fallback logic
"""

import os
import httpx
from typing import Dict, Optional

# ========== GROQ ==========
async def call_groq(prompt: str, api_key: str) -> Optional[str]:
    """Call Groq API with the given key"""
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
            else:
                print(f"Groq API error: {response.status_code}")
                return None
    except Exception as e:
        print(f"Groq exception: {str(e)}")
        return None

# ========== GEMINI ==========
async def call_gemini(prompt: str, api_key: str) -> Optional[str]:
    """Call Gemini API with the given key"""
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
                print(f"Gemini API error: {response.status_code}")
                return None
    except Exception as e:
        print(f"Gemini exception: {str(e)}")
        return None

# ========== HUGGING FACE ==========
async def call_huggingface(prompt: str, api_key: str) -> Optional[str]:
    """Call Hugging Face Inference API with the given key"""
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
                print(f"Hugging Face API error: {response.status_code}")
                return None
    except Exception as e:
        print(f"Hugging Face exception: {str(e)}")
        return None

# ========== MAIN ROUTER ==========
async def route_llm(prompt: str, model: str, user_keys: Dict) -> Dict:
    """
    Route LLM request to the selected provider
    Returns: {"success": bool, "provider": str, "response": str, "error": str}
    """
    
    # Get the appropriate API key for the selected model
    api_key = None
    if model == "groq":
        # First try user's key, then fallback to environment variable
        api_key = user_keys.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
        response = await call_groq(prompt, api_key)
        if response:
            return {"success": True, "provider": "groq", "response": response}
        else:
            return {"success": False, "error": "Groq request failed. Check your API key."}
    
    elif model == "gemini":
        api_key = user_keys.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
        response = await call_gemini(prompt, api_key)
        if response:
            return {"success": True, "provider": "gemini", "response": response}
        else:
            return {"success": False, "error": "Gemini request failed. Check your API key."}
    
    elif model == "huggingface":
        api_key = user_keys.get("hf_api_key") or os.environ.get("HF_API_KEY")
        response = await call_huggingface(prompt, api_key)
        if response:
            return {"success": True, "provider": "huggingface", "response": response}
        else:
            return {"success": False, "error": "Hugging Face request failed. Check your API key."}
    
    else:
        return {"success": False, "error": f"Unknown model: {model}"}
