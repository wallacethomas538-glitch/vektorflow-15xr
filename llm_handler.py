"""
Universal LLM Handler - Supports any provider with bring-your-own-key
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
        "url": "https://api.deepseek.com/chat/completions",
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
    }
}

MODEL_PROVIDER = {
    "llama-3.3-70b-versatile": "groq",
    "llama-3.1-8b-instant": "groq",
    "openai/gpt-oss-120b": "groq",
    "mistral-large-latest": "mistral",
    "mistral-small-latest": "mistral",
    "deepseek-chat": "deepseek",
    "command-r-plus": "cohere",
    "command-r": "cohere",
    "gemini-2.0-flash-exp": "gemini",
    "gemini-1.5-pro": "gemini",
    "claude-3-5-sonnet-latest": "anthropic",
    "claude-3-opus-latest": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai"
}

async def call_llm(prompt: str, model: str, user_keys: Dict[str, str]) -> Dict:
    provider = MODEL_PROVIDER.get(model)
    if not provider:
        return {"success": False, "error": f"Unknown model: {model}"}
    
    api_key = user_keys.get(provider)
    if not api_key:
        return {"success": False, "error": f"No API key for {provider}. Add it in Settings."}
    
    config = PROVIDER_CONFIG.get(provider)
    if not config:
        return {"success": False, "error": f"Unknown provider: {provider}"}
    
    if config["openai_compatible"]:
        return await call_openai_compatible(prompt, api_key, model, config["url"])
    elif provider == "anthropic":
        return await call_anthropic(prompt, api_key, model)
    elif provider == "cohere":
        return await call_cohere(prompt, api_key, model)
    else:
        return {"success": False, "error": f"Provider {provider} not configured"}

async def call_openai_compatible(prompt: str, api_key: str, model: str, url: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
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
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content}
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}

async def call_anthropic(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 500,
                    "temperature": 0.7
                }
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("content", [{}])[0].get("text", "")
                return {"success": True, "response": content}
            else:
                return {"success": False, "error": f"Anthropic error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}

async def call_cohere(prompt: str, api_key: str, model: str) -> Dict:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.cohere.ai/v1/chat",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "message": prompt,
                    "temperature": 0.7,
                    "max_tokens": 500
                }
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("text", "")
                return {"success": True, "response": content}
            else:
                return {"success": False, "error": f"Cohere error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}
