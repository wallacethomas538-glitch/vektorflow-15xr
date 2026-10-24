"""Meta Model API integration — prepared 2026-10-21 for the Meta Global AI
Developer Hackathon (project: VektorMind 2.0).

Wiring state: READY, awaiting credentials. Nothing in this module fabricates
a response. When the Meta Model API environment variables are absent, chat
and image calls refuse with an explicit "not configured" result and no
network request is attempted — the same honesty contract the rest of this
codebase follows (see AdImageAgent in vektorflow_agents.py).

Environment (set in the backend's Render environment on key day):
    META_MODEL_API_KEY   Meta Model API key (hackathon credits).
    META_MODEL_API_BASE  API root URL, e.g. https://api.example-meta.dev
                         (no trailing "/v1" — paths are appended here).
    META_MUSE_MODEL      Muse Spark chat model id.
    META_IMAGE_MODEL     Muse Image model id.

Chat path: Muse Spark requests route through the existing policy gateway
(llm_gateway.agent_llm -> llm_handler.call_gateway). policy_engine
authorizes first, so the kill switch and usage recording apply exactly as
they do to every other agent LLM call. bridge_gateway_env() points the
pre-existing LLM_GATEWAY_* settings at the Meta API when — and only when —
they are not already configured, so key day is an env change, not a code
change. NOTE: llm_handler reads LLM_GATEWAY_* into module constants at
import time, so this module bridges at import and must be imported before
llm_handler (main.py does this explicitly).

Image path: MetaImageClient mirrors AdImageAgent's OpenAI-style images
contract ({base}/v1/images/generations, Bearer auth, response_format=url)
and normalizes a b64_json upstream reply to a data: URL, so callers always
receive data[0].url — the exact shape the Ads Studio already renders.

Known caveat (documented, not hidden): llm_handler.call_llm fails over to
openrouter/free when a gateway/ call fails. meta_chat therefore annotates
its result with meta_served so a caller (or a demo) can prove whether the
Muse Spark model actually served the request.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

ENV_API_KEY = "META_MODEL_API_KEY"
ENV_API_BASE = "META_MODEL_API_BASE"
ENV_MUSE_MODEL = "META_MUSE_MODEL"
ENV_IMAGE_MODEL = "META_IMAGE_MODEL"

#: Model strings the Ads Studio sends when the commander picks the Meta
#: engine. They are routing sentinels, never upstream model ids.
META_MODEL_SENTINELS = {"muse-image", "meta", "muse_image"}

_NOT_CONFIGURED = (
    "Meta Model API is not configured on the backend "
    "(META_MODEL_API_KEY / META_MODEL_API_BASE / model id missing from the environment)"
)


class MetaNotConfigured(RuntimeError):
    """Raised when a Meta Model API call is attempted without credentials."""


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _api_key() -> str:
    return _env(ENV_API_KEY)


def _api_base() -> str:
    return _env(ENV_API_BASE).rstrip("/")


def _muse_model() -> str:
    return _env(ENV_MUSE_MODEL)


def _image_model() -> str:
    return _env(ENV_IMAGE_MODEL)


_bridge_state: Dict[str, str] = {}


def bridge_gateway_env() -> Dict[str, str]:
    """Point the existing LLM gateway env at the Meta Model API.

    Sets LLM_GATEWAY_URL / LLM_GATEWAY_API_KEY / LLM_GATEWAY_MODEL from the
    META_* variables, each ONLY when the gateway variable is currently
    unset — an operator-configured gateway is never overridden. Returns a
    map of what was set (variable name -> source), never key values.
    """
    global _bridge_state
    if _bridge_state:
        return dict(_bridge_state)
    applied: Dict[str, str] = {}
    if _api_key() and _api_base():
        if not _env("LLM_GATEWAY_URL"):
            os.environ["LLM_GATEWAY_URL"] = _api_base()
            applied["LLM_GATEWAY_URL"] = ENV_API_BASE
        if not _env("LLM_GATEWAY_API_KEY"):
            os.environ["LLM_GATEWAY_API_KEY"] = _api_key()
            applied["LLM_GATEWAY_API_KEY"] = ENV_API_KEY
        if _muse_model() and not _env("LLM_GATEWAY_MODEL"):
            os.environ["LLM_GATEWAY_MODEL"] = _muse_model()
            applied["LLM_GATEWAY_MODEL"] = ENV_MUSE_MODEL
    _bridge_state = applied
    if applied:
        logger.info("Meta Model API gateway bridge applied: %s", sorted(applied))
    return dict(_bridge_state)


def _gateway_bridge_desc() -> str:
    if _env("LLM_GATEWAY_URL") and _api_base() and _env("LLM_GATEWAY_URL") == _api_base():
        return "bridged-to-meta"
    if _env("LLM_GATEWAY_URL"):
        return "gateway-already-configured"
    return "inactive"


def meta_status() -> Dict[str, Any]:
    """Public, secret-free status of the Meta Model API integration.

    Safe to expose on an unauthenticated route: contains no key material,
    only set/unset flags, the (non-secret) base URL, and model ids.
    """
    key_set = bool(_api_key())
    base_set = bool(_api_base())
    configured = key_set and base_set
    return {
        "provider": "meta-model-api",
        "configured": configured,
        "api_key_set": key_set,
        "api_base_set": base_set,
        "api_base": _api_base() or None,
        "chat": {
            "model": _muse_model() or None,
            "ready": bool(configured and _muse_model()),
            "via": "llm_gateway.agent_llm (policy-authorized)",
        },
        "image": {
            "model": _image_model() or None,
            "ready": bool(configured and _image_model()),
        },
        "gateway_bridge": _gateway_bridge_desc(),
    }


async def meta_chat(agent: str, prompt: str, user_keys: Optional[Dict[str, str]] = None,
                    mission_id: Optional[str] = None) -> Dict[str, Any]:
    """Run one Muse Spark chat request through the policy gateway.

    Refuses (without any provider call) when the Meta integration is not
    configured. Otherwise delegates to llm_gateway.agent_llm with the
    "gateway/<muse model>" route, so policy_engine authorization, the kill
    switch, and usage recording all apply. The result is annotated with
    meta_requested_model / meta_served so a silent failover inside
    call_llm (gateway failure -> openrouter/free) is detectable.
    """
    status = meta_status()
    if not status["chat"]["ready"]:
        return {"success": False, "error": _NOT_CONFIGURED, "meta": status}
    bridge_gateway_env()
    from llm_gateway import agent_llm  # lazy: keeps this module import-safe pre-bridge

    muse = _muse_model()
    result = await agent_llm(agent, prompt, f"gateway/{muse}", user_keys or {},
                             mission_id=mission_id)
    if isinstance(result, dict):
        result["meta_requested_model"] = muse
        result["meta_served"] = bool(result.get("success")) and result.get("model") == muse
    return result


class MetaImageClient:
    """Muse Image client with the same contract as AdImageAgent.

    Returns {"status", "provider": "meta", "agent", "model",
    "data": [{"url": ...}]} — the shape POST /api/ads/generate-image
    already returns for Pollinations and the Ads Studio already renders.
    """

    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None,
                 image_model: Optional[str] = None,
                 transport: Optional[httpx.AsyncBaseTransport] = None):
        self.api_key = api_key if api_key is not None else _api_key()
        self.api_base = (api_base if api_base is not None else _api_base()).rstrip("/")
        self.image_model = image_model if image_model is not None else _image_model()
        self._transport = transport

    def _resolve_model(self, model: Optional[str]) -> str:
        candidate = (model or "").strip()
        if candidate and candidate.lower() not in META_MODEL_SENTINELS:
            return candidate
        return self.image_model

    async def generate_image(self, prompt: str, model: Optional[str] = None,
                             size: str = "1024x1024") -> Dict[str, Any]:
        if not self.api_key or not self.api_base:
            raise MetaNotConfigured(_NOT_CONFIGURED)
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("Prompt required")
        resolved = self._resolve_model(model)
        if not resolved:
            raise MetaNotConfigured(_NOT_CONFIGURED)
        size = (size or "1024x1024").strip() or "1024x1024"
        width, height = (size.split("x", 1) if "x" in size else ("1024", "1024"))

        async with httpx.AsyncClient(timeout=120.0, transport=self._transport) as client:
            response = await client.post(
                f"{self.api_base}/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": resolved,
                    "prompt": prompt,
                    "size": f"{width}x{height}",
                    "n": 1,
                    "response_format": "url",
                },
            )
        if response.status_code >= 400:
            logger.error("Meta image API error: HTTP %s", response.status_code)
            raise RuntimeError(
                f"Meta image generation failed (upstream HTTP {response.status_code})"
            )
        payload = response.json()
        data = payload.get("data") or []
        first = data[0] if data else {}
        url = first.get("url")
        if not url and first.get("b64_json"):
            url = f"data:image/png;base64,{first['b64_json']}"
        if not url:
            raise RuntimeError("Meta image response contained no image data")
        return {
            "status": "success",
            "provider": "meta",
            "agent": "MetaImage",
            "model": resolved,
            "data": [{"url": url}],
        }


_meta_image_client: Optional[MetaImageClient] = None


def get_meta_image_client() -> MetaImageClient:
    global _meta_image_client
    if _meta_image_client is None:
        _meta_image_client = MetaImageClient()
    return _meta_image_client


# Bridge at import time: any process that imports this module before
# llm_handler gets the gateway pointed at Meta when META_* env is present.
bridge_gateway_env()
