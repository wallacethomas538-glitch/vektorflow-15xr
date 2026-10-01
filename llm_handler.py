"""
Universal LLM Handler - Supports all providers
"""

import os
import asyncio
import httpx
from typing import Dict, Optional, Any
from ai_observability import start_span

LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "").rstrip("/")
LLM_GATEWAY_API_KEY = os.getenv("LLM_GATEWAY_API_KEY", "")
LLM_GATEWAY_PROVIDER = os.getenv("LLM_GATEWAY_PROVIDER", "openrouter")
LLM_GATEWAY_MODEL = os.getenv("LLM_GATEWAY_MODEL", "openrouter/free")
DEFAULT_MODEL = os.getenv("VEKTORFLOW_MODEL", "ollama/qwen2.5:0.5b-instruct")

# Direct provider credentials. Keep these server-side; never put them in Vite/client env.
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_HTTP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "")
OPENROUTER_X_TITLE = os.getenv("OPENROUTER_X_TITLE", "VektorFlow")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
OPENCODE_ZEN_API_KEY = os.getenv("OPENCODE_ZEN_API_KEY", "")

# Comma-separated Ollama endpoints. The first endpoint is used first, then
# subsequent endpoints are tried automatically when a request fails.
DEFAULT_OLLAMA_ENDPOINT = "https://ollama.com/api/generate"
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
OLLAMA_ENDPOINTS = [
    endpoint.strip().rstrip("/")
    for endpoint in os.getenv("OLLAMA_ENDPOINTS", DEFAULT_OLLAMA_ENDPOINT).split(",")
    if endpoint.strip()
]
_ollama_index = 0
_ollama_index_lock = asyncio.Lock()

PROVIDER_CONFIG = {
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "openai_compatible": True
    },
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
    "nvidia": {
        "url": "https://integrate.api.nvidia.com/v1/chat/completions",
        "openai_compatible": True
    },
    "cloudflare": {
        "url": "https://api.cloudflare.com/client/v4",
        "openai_compatible": False
    },
    "opencode": {
        "url": "https://opencode.ai/zen/v1/chat/completions",
        "openai_compatible": True
    },
    "ollama": {
        "url": "https://ollama.com/api/generate",
        "openai_compatible": False
    },
}

MODEL_PROVIDER = {
    "openrouter/free": "openrouter",
    "openrouter/auto": "openrouter",
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
}

# Provider-prefixed models are resolved without requiring every model to be
# hard-coded above. Examples: openrouter/meta-llama/..., nvidia/..., etc.
PROVIDER_PREFIXES = {
    "openrouter": "openrouter",
    "groq": "groq",
    "mistral": "mistral",
    "deepseek": "deepseek",
    "cohere": "cohere",
    "gemini": "gemini",
    "anthropic": "anthropic",
    "openai": "openai",
    "huggingface": "huggingface",
    "ollama": "ollama",
    "nvidia": "nvidia",
    "cloudflare": "cloudflare",
    "opencode": "opencode",
}


async def _call_llm(prompt: str, model: str, user_keys: Dict) -> Dict:
    if model.startswith("gateway/"):
        return await call_gateway(prompt, model[len("gateway/"):])

    provider = MODEL_PROVIDER.get(model)
    if not provider:
        prefix = model.split("/", 1)[0] if "/" in model else ""
        provider = PROVIDER_PREFIXES.get(prefix)
    if not provider and model.startswith("ollama/"):
        provider = "ollama"
    if not provider:
        return {"success": False, "error": f"Unknown model: {model}"}
    
    config = PROVIDER_CONFIG.get(provider)
    if not config:
        return {"success": False, "error": f"Unknown provider: {provider}"}
    
    if provider == "ollama":
        return await call_ollama(prompt, model)
    if provider == "cloudflare":
        return await call_cloudflare(prompt, model)

    api_key = (
        user_keys.get(provider)
        or {
            "openrouter": OPENROUTER_API_KEY,
            "nvidia": NVIDIA_API_KEY,
            "opencode": OPENCODE_ZEN_API_KEY,
        }.get(provider, "")
    )
    if not api_key:
        return {"success": False, "error": f"No API key for {provider}. Add it in Settings."}
    
    if provider in {"openrouter", "nvidia", "opencode"}:
        return await call_openai_compatible(
            prompt,
            api_key,
            model.split("/", 1)[1] if model.startswith(provider + "/") else model,
            PROVIDER_CONFIG[provider]["url"],
            provider,
        )
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

async def call_llm(prompt: str, model: str, user_keys: Dict) -> Dict:
    """Trace every model request while preserving the existing provider/failover logic."""
    with start_span("vektorflow.llm", {"gen_ai.request.model": model} ) as span:
        result = await _call_llm(prompt, model, user_keys)
        if isinstance(result, dict):
            if result.get("provider") is not None:
                span.set_attribute("gen_ai.system", str(result.get("provider")))
            if result.get("success") is not None:
                span.set_attribute("vf.success", bool(result.get("success")))
            if result.get("model") is not None:
                span.set_attribute("gen_ai.response.model", str(result.get("model")))
        return result

async def call_gateway(prompt: str, model: str) -> Dict:
    """Call the shared Free LLM Gateway using its OpenAI-compatible endpoint."""
    if not LLM_GATEWAY_URL:
        return {"success": False, "error": "LLM_GATEWAY_URL is not configured."}
    if not LLM_GATEWAY_API_KEY:
        return {"success": False, "error": "LLM_GATEWAY_API_KEY is not configured."}

    requested_model = model or LLM_GATEWAY_MODEL
    payload = {
        "model": requested_model,
        "provider": LLM_GATEWAY_PROVIDER,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 500,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{LLM_GATEWAY_URL}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_GATEWAY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code >= 400:
                return {"success": False, "error": f"LLM Gateway HTTP {response.status_code}: {response.text[:1000]}"}
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"success": True, "response": content, "provider": LLM_GATEWAY_PROVIDER, "model": requested_model}
    except Exception as exc:
        return {"success": False, "error": f"LLM Gateway request failed: {exc}"}

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


async def call_openai_compatible(
    prompt: str,
    api_key: str,
    model: str,
    url: str,
    provider: str,
) -> Dict:
    """Shared OpenAI-compatible transport for cloud model providers."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if provider == "openrouter":
        if OPENROUTER_HTTP_REFERER:
            headers["HTTP-Referer"] = OPENROUTER_HTTP_REFERER
        if OPENROUTER_X_TITLE:
            headers["X-Title"] = OPENROUTER_X_TITLE

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 500,
                    "stream": False,
                },
            )
            if response.status_code >= 400:
                return {
                    "success": False,
                    "error": f"{provider} API error: {response.status_code}: {response.text[:500]}",
                    "provider": provider,
                    "model": model,
                }
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "success": True,
                "response": content,
                "provider": provider,
                "model": model,
            }
    except Exception as exc:
        return {
            "success": False,
            "error": f"{provider} request failed: {exc}",
            "provider": provider,
            "model": model,
        }

async def call_cloudflare(prompt: str, model: str) -> Dict:
    """Call Cloudflare Workers AI using an account-scoped AI Run endpoint."""
    if not CLOUDFLARE_ACCOUNT_ID or not CLOUDFLARE_API_TOKEN:
        return {
            "success": False,
            "error": "CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN are required for Cloudflare Workers AI.",
            "provider": "cloudflare",
        }

    model_name = model.split("/", 1)[1] if model.startswith("cloudflare/") else model
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/{model_name}"
    )
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={"messages": [{"role": "user", "content": prompt}]},
            )
            if response.status_code >= 400:
                return {
                    "success": False,
                    "error": f"Cloudflare Workers AI error: {response.status_code}: {response.text[:500]}",
                    "provider": "cloudflare",
                    "model": model_name,
                }
            data = response.json()
            result = data.get("result", {})
            content = result.get("response", "") if isinstance(result, dict) else str(result)
            return {
                "success": True,
                "response": content,
                "provider": "cloudflare",
                "model": model_name,
            }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Cloudflare request failed: {exc}",
            "provider": "cloudflare",
            "model": model_name,
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