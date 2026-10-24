"""Tests for the Meta Model API prep wiring (src/meta_model.py).

Prepared 2026-10-21 for the Meta Global AI Developer Hackathon
(VektorMind 2.0). These tests prove the integration is honestly gated:
no credentials -> explicit refusal, no network attempt, no fabricated
output. With credentials set, they pin the exact request shape the
Meta Model API will receive on key day (via httpx MockTransport —
no real network is touched).
"""
import asyncio
import json
import os
import sys

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src import meta_model
from src.meta_model import (
    MetaImageClient,
    MetaNotConfigured,
    bridge_gateway_env,
    meta_chat,
    meta_status,
)

META_VARS = ["META_MODEL_API_KEY", "META_MODEL_API_BASE",
             "META_MUSE_MODEL", "META_IMAGE_MODEL"]
GATEWAY_VARS = ["LLM_GATEWAY_URL", "LLM_GATEWAY_API_KEY", "LLM_GATEWAY_MODEL"]
DUMMY_KEY = "test-meta-key-not-a-real-secret"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in META_VARS + GATEWAY_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(meta_model, "_bridge_state", {})
    yield


@pytest.fixture
def configured_env(monkeypatch):
    monkeypatch.setenv("META_MODEL_API_KEY", DUMMY_KEY)
    monkeypatch.setenv("META_MODEL_API_BASE", "https://meta.test")
    monkeypatch.setenv("META_MUSE_MODEL", "muse-spark-test")
    monkeypatch.setenv("META_IMAGE_MODEL", "muse-image-test")
    monkeypatch.setattr(meta_model, "_bridge_state", {})


# --- status ---------------------------------------------------------------

def test_status_unconfigured_is_honest():
    status = meta_status()
    assert status["configured"] is False
    assert status["api_key_set"] is False
    assert status["api_base_set"] is False
    assert status["chat"]["ready"] is False
    assert status["image"]["ready"] is False
    assert status["gateway_bridge"] == "inactive"


def test_status_configured_and_secret_free(configured_env):
    status = meta_status()
    assert status["configured"] is True
    assert status["chat"] == {
        "model": "muse-spark-test",
        "ready": True,
        "via": "llm_gateway.agent_llm (policy-authorized)",
    }
    assert status["image"]["ready"] is True
    assert status["image"]["model"] == "muse-image-test"
    assert DUMMY_KEY not in json.dumps(status)


# --- gateway bridge ---------------------------------------------------------

def test_bridge_points_gateway_at_meta(configured_env, monkeypatch):
    applied = bridge_gateway_env()
    assert set(applied) == {"LLM_GATEWAY_URL", "LLM_GATEWAY_API_KEY", "LLM_GATEWAY_MODEL"}
    assert os.environ["LLM_GATEWAY_URL"] == "https://meta.test"
    assert os.environ["LLM_GATEWAY_API_KEY"] == DUMMY_KEY
    assert os.environ["LLM_GATEWAY_MODEL"] == "muse-spark-test"
    assert meta_status()["gateway_bridge"] == "bridged-to-meta"


def test_bridge_never_overrides_existing_gateway(configured_env, monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_URL", "https://other-gateway.example")
    bridge_gateway_env()
    assert os.environ["LLM_GATEWAY_URL"] == "https://other-gateway.example"
    assert meta_status()["gateway_bridge"] == "gateway-already-configured"


def test_bridge_noop_without_meta_env():
    assert bridge_gateway_env() == {}
    assert "LLM_GATEWAY_URL" not in os.environ


# --- chat -------------------------------------------------------------------

def test_meta_chat_refuses_when_unconfigured(monkeypatch):
    import llm_gateway

    async def forbidden(*args, **kwargs):
        raise AssertionError("agent_llm must not be called when unconfigured")

    monkeypatch.setattr(llm_gateway, "agent_llm", forbidden)
    result = asyncio.run(meta_chat("DaVinci", "write an ad headline"))
    assert result["success"] is False
    assert "not configured" in result["error"]


def test_meta_chat_routes_through_policy_gateway(configured_env, monkeypatch):
    import llm_gateway

    seen = {}

    async def fake_agent_llm(agent, prompt, model, user_keys, mission_id=None):
        seen.update(agent=agent, prompt=prompt, model=model, mission_id=mission_id)
        return {"success": True, "response": "ok", "model": "muse-spark-test",
                "provider": "openrouter", "gateway": "vektorflow-agent-gateway"}

    monkeypatch.setattr(llm_gateway, "agent_llm", fake_agent_llm)
    result = asyncio.run(meta_chat("DaVinci", "headline please", mission_id="msn_1"))
    assert seen["model"] == "gateway/muse-spark-test"
    assert seen["agent"] == "DaVinci"
    assert seen["mission_id"] == "msn_1"
    assert result["meta_requested_model"] == "muse-spark-test"
    assert result["meta_served"] is True


def test_meta_chat_flags_silent_failover(configured_env, monkeypatch):
    import llm_gateway

    async def failover_agent_llm(agent, prompt, model, user_keys, mission_id=None):
        # llm_handler.call_llm fails over to openrouter/free on gateway errors;
        # the annotation must expose that Muse did NOT serve this request.
        return {"success": True, "response": "ok", "model": "openrouter/free",
                "provider": "openrouter"}

    monkeypatch.setattr(llm_gateway, "agent_llm", failover_agent_llm)
    result = asyncio.run(meta_chat("Scout", "research this"))
    assert result["meta_served"] is False


# --- image client -----------------------------------------------------------

def test_image_client_refuses_when_unconfigured():
    client = MetaImageClient(api_key="", api_base="", image_model="")
    with pytest.raises(MetaNotConfigured, match="not configured"):
        asyncio.run(client.generate_image("a red car"))


def test_image_client_request_shape_and_url_passthrough():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": [{"url": "https://img.example/ad.png"}]})

    client = MetaImageClient(api_key=DUMMY_KEY, api_base="https://meta.test",
                             image_model="muse-image-test",
                             transport=httpx.MockTransport(handler))
    result = asyncio.run(client.generate_image("shiny red car ad", model="muse-image",
                                               size="1080x1350"))
    assert captured["url"] == "https://meta.test/v1/images/generations"
    assert captured["auth"] == f"Bearer {DUMMY_KEY}"
    assert captured["body"]["model"] == "muse-image-test"  # sentinel resolved
    assert captured["body"]["prompt"] == "shiny red car ad"
    assert captured["body"]["size"] == "1080x1350"
    assert result["provider"] == "meta"
    assert result["data"][0]["url"] == "https://img.example/ad.png"


def test_image_client_normalizes_b64_reply():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"b64_json": "QUJD"}]})

    client = MetaImageClient(api_key=DUMMY_KEY, api_base="https://meta.test",
                             image_model="muse-image-test",
                             transport=httpx.MockTransport(handler))
    result = asyncio.run(client.generate_image("anything"))
    assert result["data"][0]["url"] == "data:image/png;base64,QUJD"


def test_image_client_upstream_error_is_honest():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = MetaImageClient(api_key=DUMMY_KEY, api_base="https://meta.test",
                             image_model="muse-image-test",
                             transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="upstream HTTP 500"):
        asyncio.run(client.generate_image("anything"))
