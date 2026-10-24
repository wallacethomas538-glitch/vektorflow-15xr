"""The vektormind.task-result.v1 completion contract."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mission_control_api import _task_result_completion_gate


def result(**overrides):
    value = {
        "status": "completed",
        "summary": "Found a supported opportunity.",
        "evidence": [{"source": "catalog", "value": "SKU-1"}],
        "tool_calls": [{"tool": "search", "status": "completed"}],
        "approvals": [],
    }
    value.update(overrides)
    return value


def test_01_valid_result_completes():
    assert _task_result_completion_gate(result()) == (True, "")


def test_02_status_must_be_completed():
    ok, reason = _task_result_completion_gate(result(status="running"))
    assert not ok and "status" in reason


def test_03_missing_status_rejected():
    value = result(); del value["status"]
    assert not _task_result_completion_gate(value)[0]


def test_04_empty_summary_rejected():
    ok, reason = _task_result_completion_gate(result(summary="  "))
    assert not ok and "summary" in reason


def test_05_missing_summary_rejected():
    value = result(); del value["summary"]
    assert not _task_result_completion_gate(value)[0]


def test_06_empty_evidence_rejected():
    ok, reason = _task_result_completion_gate(result(evidence=[]))
    assert not ok and "evidence" in reason


def test_07_blank_evidence_rejected():
    assert not _task_result_completion_gate(result(evidence=[{}, ""]))[0]


def test_08_evidence_mapping_is_supported():
    assert _task_result_completion_gate(result(evidence={"source": {"id": "42"}}))[0]


def test_10_required_failed_tool_rejected():
    ok, reason = _task_result_completion_gate(result(tool_calls=[{"tool": "search", "status": "failed"}]))
    assert not ok and "tool" in reason


def test_11_optional_failed_tool_does_not_reject():
    assert _task_result_completion_gate(result(tool_calls=[{"tool": "telemetry", "status": "failed", "required": False}]))[0]


def test_12_pending_approval_rejected():
    ok, reason = _task_result_completion_gate(result(approvals=[{"status": "pending"}]))
    assert not ok and "approval" in reason


def test_13_awaiting_approval_rejected():
    assert not _task_result_completion_gate(result(approvals=[{"state": "awaiting_approval"}]))[0]


def test_14_approved_result_completes():
    assert _task_result_completion_gate(result(approvals=[{"status": "approved"}]))[0]


def test_15_failed_result_never_completes():
    assert not _task_result_completion_gate(result(status="failed"))[0]
