"""Kill switch enforcement across the policy engine.

Proves that with the kill switch ON for an agent, all three authorizers
reject — and with it OFF, normal allow decisions still work.

The fix under test is in policy_engine.py:
  * authorize_tool() — kill switch is an early reject.
  * authorize_model() — kill switch is the FIRST check.
  * authorize_llm_request() — covered transitively because it calls
    authorize_model() before any budget math.

Run:
    pytest tests/test_kill_switch_llm.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the repo root is importable when running pytest from the tests/ dir.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import policy_engine
from policy_engine import authorize_llm_request, authorize_model, authorize_tool

AGENT = "test-agent"
KNOWN_TOOL = "search_products"
KNOWN_MODEL = "local-model-v1"


class _StubKillSwitch:
    """Stand-in for whatever get_kill_switch() returns."""

    def __init__(self, killed_agents):
        self._killed = set(killed_agents)

    def is_killed(self, agent):
        return agent in self._killed


# tiny helper to keep the test bodies clean
def _patch_tool_names(names):
    import contextlib

    @contextlib.contextmanager
    def _cm():
        original = policy_engine._tool_names
        policy_engine._tool_names = lambda agent: set(names)
        try:
            yield
        finally:
            policy_engine._tool_names = original
    return _cm()


def _patch_kill_switch(agents):
    import contextlib

    @contextlib.contextmanager
    def _cm():
        original = policy_engine.get_kill_switch
        policy_engine.get_kill_switch = lambda: _StubKillSwitch(agents)
        try:
            yield
        finally:
            policy_engine.get_kill_switch = original
    return _cm()


def _patch_env(mapping):
    import contextlib

    @contextlib.contextmanager
    def _cm():
        saved = {k: os.environ.get(k) for k in mapping}
        for k, v in mapping.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        try:
            yield
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return _cm()


# --- authorize_tool ----------------------------------------------------

def test_authorize_tool_allows_when_kill_switch_off():
    with _patch_kill_switch(set()), _patch_tool_names([KNOWN_TOOL]):
        result = authorize_tool(AGENT, KNOWN_TOOL)
    assert result["allowed"] is True
    assert result["decision"] == "allow"


def test_authorize_tool_rejects_when_kill_switch_on():
    with _patch_kill_switch({AGENT}), _patch_tool_names([KNOWN_TOOL]):
        result = authorize_tool(AGENT, KNOWN_TOOL)
    assert result["allowed"] is False
    assert result["decision"] == "reject"
    assert "Kill switch is on" in result["reason"]


# --- authorize_model ---------------------------------------------------

def test_authorize_model_allows_when_kill_switch_off():
    with _patch_kill_switch(set()), _patch_env({"VF_ALLOWED_MODELS": KNOWN_MODEL}):
        result = authorize_model(AGENT, KNOWN_MODEL)
    assert result["allowed"] is True
    assert result["decision"] == "allow"


def test_authorize_model_rejects_when_kill_switch_on():
    with _patch_kill_switch({AGENT}), _patch_env({"VF_ALLOWED_MODELS": KNOWN_MODEL}):
        result = authorize_model(AGENT, KNOWN_MODEL)
    assert result["allowed"] is False
    assert result["decision"] == "reject"


# --- authorize_llm_request --------------------------------------------

def test_llm_request_allows_when_kill_switch_off():
    # Blanket allowlist so the model check is trivially true; budgets are
    # at their defaults (60 rpm / 120k tpm) which this request will not
    # exceed on a fresh process.
    with _patch_kill_switch(set()), _patch_env({"VF_ALLOWED_MODELS": ""}):
        result = authorize_llm_request(AGENT, KNOWN_MODEL, estimated_tokens=100)
    assert result["allowed"] is True
    assert result["decision"] == "allow"


def test_llm_request_rejects_when_kill_switch_on():
    with _patch_kill_switch({AGENT}), _patch_env({"VF_ALLOWED_MODELS": ""}):
        result = authorize_llm_request(AGENT, KNOWN_MODEL, estimated_tokens=100)
    assert result["allowed"] is False
    assert result["decision"] == "reject"
