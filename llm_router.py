"""
VektorFlow 15xr - LLM Router
Supports Groq, Gemini, Hugging Face
"""

import os
import httpx
from typing import Dict, Optional

# ========== GROQ ==========
async def call_groq(prompt: str, api_key: str, model: str) -> Optional[str]:
    """Call Groq API with the given key and model"""
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
                print(f"Groq API error: {response.status_code} - {response.text[:200]}")
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
    
    # Get API keys from user's saved keys or environment variables
    groq_key = user_keys.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
    gemini_key = user_keys.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    hf_key = user_keys.get("hf_api_key") or os.environ.get("HF_API_KEY")
    
    # Groq models (includes Llama 3.3, GPT OSS, Qwen, etc.)
    if "llama" in model or "gpt-oss" in model or "qwen" in model or "mixtral" in model:
        if not groq_key:
            return {"success": False, "error": "No Groq API key found. Add it in Your API Keys section."}
        response = await call_groq(prompt, groq_key, model)
        if response:
            return {"success": True, "provider": "groq", "response": response, "model": model}
        else:
            return {"success": False, "error": "Groq request failed. Check your API key and model name."}
    
    # Gemini
    elif model == "gemini":
        if not gemini_key:
            return {"success": False, "error": "No Gemini API key found. Add it in Your API Keys section."}
        response = await call_gemini(prompt, gemini_key)
        if response:
            return {"success": True, "provider": "gemini", "response": response}
        else:
            return {"success": False, "error": "Gemini request failed. Check your API key."}
    
    # Hugging Face
    elif model == "huggingface":
        if not hf_key:
            return {"success": False, "error": "No Hugging Face API key found. Add it in Your API Keys section."}
        response = await call_huggingface(prompt, hf_key)
        if response:
            return {"success": True, "provider": "huggingface", "response": response}
        else:
            return {"success": False, "error": "Hugging Face request failed. Check your API key."}
    
    else:
        return {"success": False, "error": f"Unknown model: {model}. Try llama-3.3-70b-versatile or openai/gpt-oss-120b"}
