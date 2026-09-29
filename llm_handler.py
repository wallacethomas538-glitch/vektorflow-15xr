"""
Universal LLM Handler - Supports all providers
"""

import os
import asyncio
import httpx
from typing import Dict, Optional, Any

DEFAULT_MODEL = os.getenv("VEKTORFLOW_MODEL", "ollama/llama3.2")

# Comma-separated Ollama endpoints. The first endpoint is used first, then
# subsequent endpoints are tried automatically when a request fails.
DEFAULT_OLLAMA_ENDPOINT = "https://ollama.com/api/generate"
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
POLLINATIONS_API_KEY = os.getenv("POLLINATIONS_API_KEY", "")
POLLINATIONS_API_URL = os.getenv("POLLINATIONS_API_URL", "https://gen.pollinations.ai").rstrip("/")
POLLINATIONS_REFERRER = os.getenv("POLLINATIONS_REFERRER", "vektorflow-ai")
OLLAMA_ENDPOINTS = [
    endpoint.strip().rstrip("/")
    for endpoint in os.getenv("OLLAMA_ENDPOINTS", DEFAULT_OLLAMA_ENDPOINT).split(",")
    if endpoint.strip()
]
_ollama_index = 0
_ollama_index_lock = asyncio.Lock()

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
        "url": "https://ollama.com/api/generate",
        "openai_compatible": False
    },
    "pollinations": {
        "url": "https://gen.pollinations.ai/v1/chat/completions",
        "openai_compatible": True
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
    "ollama/llama3.2": "ollama",
    "pollinations/openai": "pollinations",
    "pollinations/gpt-5.6-luna": "pollinations"
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

    if provider == "pollinations":
        api_key = user_keys.get("pollinations") or POLLINATIONS_API_KEY
        if not api_key:
            return {"success": False, "error": "No API key for pollinations. Configure POLLINATIONS_API_KEY or add a Pollinations key in Settings."}
        return await call_pollinations(prompt, api_key, model)
    
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

async def call_pollinations(prompt: str, api_key: str, model: str) -> Dict:
    """Call Pollinations through its OpenAI-compatible API."""
    model_name = model.replace("pollinations/", "")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{POLLINATIONS_API_URL}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "Referer": POLLINATIONS_REFERRER,
                },
                json={
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 1000,
                },
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return {"success": True, "response": content, "provider": "pollinations", "model": model_name}
            return {"success": False, "error": f"Pollinations API error: {response.status_code}", "provider": "pollinations"}
    except Exception as e:
        return {"success": False, "error": f"Pollinations request failed: {str(e)}", "provider": "pollinations"}


async def call_ollama(prompt: str, model: str) -> Dict:
    """Call Ollama with round-robin endpoint selection and automatic failover."""
    global _ollama_index

    if not OLLAMA_ENDPOINTS:
        return {"success": False, "error": "No Ollama endpoints configured."}

    model_name = model.replace("ollama/", "")
    async with _ollama_index_lock:
        start_index = _ollama_index % len(OLLAMA_ENDPOINTS)
        _ollama_index = (start_index + 1) % len(OLLAMA_ENDPOINTS)

    errors = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for offset in range(len(OLLAMA_ENDPOINTS)):
            endpoint_index = (start_index + offset) % len(OLLAMA_ENDPOINTS)
            endpoint = OLLAMA_ENDPOINTS[endpoint_index]
            try:
                headers = {"Content-Type": "application/json"}
                if OLLAMA_API_KEY:
                    headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json={"model": model_name, "prompt": prompt, "stream": False}
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "response": data.get("response", ""),
                        "provider": "ollama",
                        "endpoint": endpoint,
                    }

                errors.append(f"{endpoint}: HTTP {response.status_code}")
            except Exception as exc:
                errors.append(f"{endpoint}: {exc}")

    return {
        "success": False,
        "error": "All Ollama endpoints failed: " + " | ".join(errors),
        "provider": "ollama",
    }

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