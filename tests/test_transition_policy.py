from mission_control import can_transition, can_task_transition


def test_terminal_mission_states_are_final():
    assert not can_transition("completed", "planning")
    assert not can_transition("cancelled", "executing")
    assert not can_transition("completed", "cancelled")
    assert not can_transition("cancelled", "completed")
    assert not can_transition("completed", "completed")


def test_failed_mission_can_retry_only_to_planning_or_ready():
    assert can_transition("failed", "planning")
    assert can_transition("failed", "ready")
    assert not can_transition("failed", "executing")
    assert can_transition("failed", "cancelled")


def test_unknown_mission_states_are_rejected():
    assert not can_transition("pending", "planning")
    assert not can_transition("draft", "bogus")
    assert not can_transition("", "draft")


def test_non_terminal_mission_states_move_freely():
    assert can_transition("draft", "executing")
    assert can_transition("paused", "ready")
    assert can_transition("draft", "completed")
    assert can_transition("blocked", "cancelled")


def test_task_policy_has_no_hand_maintained_edges():
    assert can_task_transition("pending", "failed")
    assert can_task_transition("running", "pending")
    assert not can_task_transition("completed", "pending")


def test_terminal_task_states_are_final():
    assert not can_task_transition("completed", "cancelled")
    assert not can_task_transition("cancelled", "running")
    assert not can_task_transition("cancelled", "completed")
    assert not can_task_transition("completed", "completed")


def test_failed_task_can_retry_freely():
    assert can_task_transition("failed", "pending")
    assert can_task_transition("failed", "running")


def test_unknown_task_states_are_rejected():
    assert not can_task_transition("waiting", "pending")
    assert not can_task_transition("pending", "bogus")
    assert not can_task_transition("", "pending")


def test_non_terminal_task_states_move_including_cancel():
    assert can_task_transition("pending", "cancelled")
    assert can_task_transition("running", "cancelled")
