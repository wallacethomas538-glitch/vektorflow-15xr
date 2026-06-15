"""
Universal LLM Handler - Supports any provider with bring-your-own-key
"""

import os
import httpx
from typing import Dict, Optional, Any

# Provider API endpoints (OpenAI-compatible where possible)
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

# Model to provider mapping
MODEL_PROVIDER = {
    "llama-3.3-70b-versatile": "groq",
    "llama-3.1-8b-instant": "groq",
    "openai/gpt-oss-120b": "groq",
    "mistral-large-latest": "mistral",
    "mistral-small-latest": "mistral",
    "deepseek-chat": "deepseek",
    "deepseek-coder": "deepseek",
    "command-r-plus": "cohere",
    "command-r": "cohere",
    "gemini-2.0-flash-exp": "gemini",
    "gemini-1.5-pro": "gemini",
    "claude-3-5-sonnet-latest": "anthropic",
    "claude-3-opus-latest": "anthropic",
    "gpt-4o": "openai",
    "gpt-4o-mini": "openai"
}

async def call_llm(prompt: str, model: str, user_llm_keys: Dict[str, str]) -> Dict:
    """
    Universal LLM call - supports any provider the user has a key for.
    """
    # Determine provider from model
    provider = MODEL_PROVIDER.get(model)
    if not provider:
        # Try to infer from model name
        if "gpt" in model.lower():
            provider = "openai"
        elif "claude" in model.lower():
            provider = "anthropic"
        elif "gemini" in model.lower():
            provider = "gemini"
        elif "mistral" in model.lower():
            provider = "mistral"
        elif "deepseek" in model.lower():
            provider = "deepseek"
        elif "command" in model.lower():
            provider = "cohere"
        else:
            provider = "groq"  # default
    
    # Get user's API key for this provider
    api_key = user_llm_keys.get(provider)
    if not api_key:
        return {
            "success": False,
            "error": f"No API key found for {provider}. Please add your {provider.upper()} API key in settings.",
            "provider": provider
        }
    
    config = PROVIDER_CONFIG.get(provider)
    if not config:
        return {"success": False, "error": f"Unknown provider: {provider}"}
    
    # Route to appropriate handler
    if config["openai_compatible"]:
        return await call_openai_compatible(prompt, api_key, model, config["url"])
    elif provider == "anthropic":
        return await call_anthropic(prompt, api_key, model)
    elif provider == "cohere":
        return await call_cohere(prompt, api_key, model)
    else:
        return {"success": False, "error": f"Provider {provider} not fully configured yet"}

async def call_openai_compatible(prompt: str, api_key: str, model: str, url: str) -> Dict:
    """Call any OpenAI-compatible API endpoint"""
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
                error_text = response.text[:200] if response.text else "Unknown error"
                return {"success": False, "error": f"API error {response.status_code}: {error_text}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}

async def call_anthropic(prompt: str, api_key: str, model: str) -> Dict:
    """Call Anthropic Claude API (different format)"""
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
                return {"success": False, "error": f"Anthropic API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}

async def call_cohere(prompt: str, api_key: str, model: str) -> Dict:
    """Call Cohere API"""
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
                return {"success": False, "error": f"Cohere API error: {response.status_code}"}
    except Exception as e:
        return {"success": False, "error": f"Request failed: {str(e)}"}
