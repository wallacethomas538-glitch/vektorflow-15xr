"""
Universal LLM Handler - Supports all providers
"""

import os
import httpx
from typing import Dict, Optional, Any

PROVIDER_CONFIG = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "openai_compatible": True
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "openai_compatible": True
    },
    "deepseek": {
        "url": "https://api.deepseek.com/v1/chat/completions",
        "openai_compatible": True
    },
    "cohere": {
        "url": "https://api.cohere.ai/v1/chat",
        "openai_compatible": False
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "openai_compatible": True
    },
    "anthropic": {
        "url": "https://api.anthropic.com/v1/messages",
        "openai_compatible": False
    },
    "openai": {
        "url": "https://api.openai.com/v1/chat/completions",
        "openai_compatible": True
    },
    "huggingface": {
        "url": "https://api-inference.huggingface.co/models/",
        "openai_compatible": False
    },
    "ollama": {
        "url": "https://ollama-levx-vovn.onrender.com/api/generate",
        "openai_compatible": False
    }
}

MODEL_PROVIDER = {
    "llama-3.3-70b-versatile": "groq",
    "llama-3.1-8b-instant": "groq",
    "openai/gpt-oss-120b": "groq",
    "mistral-large-latest": "mistral",
    "mistral-small-latest": "mistral",
    "deepseek-v4-pro": "deepseek",
    "deepseek-v4-flash": "deepseek",
    "deepseek-chat": "deepseek",
    "command-r-plus": "cohere",
    "command-r": "cohere",
    "gemini-2.0-flash-exp": "gemini",
    "gemini-1.5-pro": "gemini",
    "claude-3-5-sonnet-latest": "anthropic",
    "claude-3-opus-latest": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai",
    "meta-llama/Llama-3.2-1B-Instruct": "huggingface",
    "meta-llama/Meta-Llama-3-70B-Instruct": "huggingface",
    "ollama/llama3.2": "ollama"
}

async def call_llm(prompt: str, model: str, user_keys: Dict) -> Dict:
    provider = MODEL_PROVIDER.get(model)
    if not provider:
        return {"success": False, "error": f"Unknown model: {model}"}
    
    config = PROVIDER_CONFIG.get(provider)
    if not config:
        return {"success": False, "error": f"Unknown provider: {provider}"}
    
    if provider == "ollama":
        return await call_ollama(prompt, model)
    
    api_key = user_keys.get(provider)
    if not api_key:
        return {"success": False, "error": f"No API key for {provider}. Add it in Settings."}
    
    if provider == "groq":
        return await call_groq(prompt, api_key, model)
    elif provider == "deepseek":
        return await call_deepseek(prompt, api_key, model)
    elif provider == "gemini":
        return await call_gemini(prompt, api_key, model)
    elif provider == "huggingface":
        return await call_huggingface(prompt, api_key, model)
    elif provider == "openai":
        return await call_openai(prompt, api_key, model)
    elif provider == "anthropic":
        return await call_anthropic(prompt, api_key, model)
    elif provider == "mistral":
        return await call_mistral(prompt, api_key, model)
    elif provider == "cohere":
        return await call_cohere(prompt, api_key, model)
    else:
        return {"success": False, "error": f"Provider {provider} not configured"}

async def call_ollama(prompt: str, model: str) -> Dict:
    try:
        model_name = model.replace("ollama/", "")
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                "https://ollama-levx-vovn.onrender.com/api/generate",
                json={"model": model_name, "prompt": prompt, "stream": False}
            )
            if response.status_code == 200:
                data = response.json()
                return {"success": True, "response": data.get("response", "")}
            return {"success": False, "error": f"Ollama API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Ollama request failed: {str(e)}"}

async def call_groq(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Groq API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Groq request failed: {str(e)}"}

async def call_deepseek(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"DeepSeek API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"DeepSeek request failed: {str(e)}"}

async def call_gemini(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Gemini API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Gemini request failed: {str(e)}"}

async def call_huggingface(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"https://api-inference.huggingface.co/models/{model}",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"inputs": prompt}
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    content = data[0].get("generated_text", "")
                    return {"success": True, "response": content}
                return {"success": True, "response": str(data)}
            return {"success": False, "error": f"Hugging Face API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Hugging Face request failed: {str(e)}"}

async def call_openai(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"OpenAI API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"OpenAI request failed: {str(e)}"}

async def call_anthropic(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 500, "temperature": 0.7}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("content", [{}])[0].get("text", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Anthropic API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Anthropic request failed: {str(e)}"}

async def call_mistral(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Mistral API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Mistral request failed: {str(e)}"}

async def call_cohere(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.cohere.ai/v1/chat",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "message": prompt, "temperature": 0.7, "max_tokens": 500}
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("text", "")
                return {"success": True, "response": content}
            return {"success": False, "error": f"Cohere API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Cohere request failed: {str(e)}"}