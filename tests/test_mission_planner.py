"""Envelope validation tests for mission_planner — no LLM, no network.

Covers `_validate` directly: agent roster check (case-exact), risk values,
dependency indices (int/digit-string, no self-deps, in-range), non-empty
instructions, and the empty-tasks safe-plan fallback.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from mission_planner import TASK_FIELDS, _safe_plan, _validate


def _task(**overrides):
    task = {"agent": "Scout", "instruction": "find trends", "dependencies": [], "risk": "low"}
    task.update(overrides)
    return task


def test_valid_plan_passes_and_normalizes():
    plan = _validate({"tasks": [
        _task(),
        _task(agent="Rook", dependencies=[0, "0"], risk="HIGH"),
    ]}, "objective")
    assert plan["tasks"][0]["agent"] == "Scout"
    assert plan["tasks"][1]["dependencies"] == [0, 0]
    assert plan["tasks"][1]["risk"] == "high"


def test_unknown_agent_rejected():
    with pytest.raises(ValueError):
        _validate({"tasks": [_task(agent="Ghost")]}, "objective")


def test_case_mismatch_agent_rejected():
    with pytest.raises(ValueError):
        _validate({"tasks": [_task(agent="scout")]}, "objective")


def test_bad_risk_rejected():
    with pytest.raises(ValueError):
        _validate({"tasks": [_task(risk="extreme")]}, "objective")


def test_empty_instruction_rejected():
    with pytest.raises(ValueError):
        _validate({"tasks": [_task(instruction="   ")]}, "objective")


def test_missing_field_rejected():
    task = _task()
    del task["instruction"]
    with pytest.raises(ValueError):
        _validate({"tasks": [task]}, "objective")


def test_out_of_range_dependency_rejected():
    with pytest.raises(ValueError):
        _validate({"tasks": [_task(dependencies=[1])]}, "objective")
    with pytest.raises(ValueError):
        _validate({"tasks": [_task(dependencies=[-1])]}, "objective")


def test_self_dependency_rejected():
    with pytest.raises(ValueError):
        _validate({"tasks": [_task(dependencies=[0])]}, "objective")
    with pytest.raises(ValueError):
        _validate({"tasks": [
            _task(),
            _task(dependencies=[1]),
        ]}, "objective")


def test_non_index_dependency_rejected():
    for bad in [["abc"], [None], [1.5], [True], [[]]]:
        with pytest.raises(ValueError):
            _validate({"tasks": [_task(dependencies=bad)]}, "objective")


def test_non_tasks_payload_rejected():
    for bad in [[], "plan", {"tasks": "none"}, {"objective": "x"}]:
        with pytest.raises(ValueError):
            _validate(bad, "objective")


def test_empty_tasks_returns_safe_plan():
    plan = _validate({"tasks": []}, "objective")
    assert plan == _safe_plan("objective")
    assert plan["tasks"][0]["agent"] == "Scout"
    assert plan["tasks"][0]["instruction"] == "objective"


def test_task_fields_constant_matches_envelope():
    assert set(TASK_FIELDS) == {"agent", "instruction", "dependencies", "risk"}
