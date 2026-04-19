from __future__ import annotations
import pytest
from axelo.core.router.state_machine import SessionStatus, StateMachine, InvalidTransitionError


def test_initial_status():
    sm = StateMachine()
    assert sm.status == SessionStatus.SESSION_INIT


def test_valid_transition():
    sm = StateMachine()
    sm.transition(SessionStatus.SESSION_PLANNING)
    assert sm.status == SessionStatus.SESSION_PLANNING


def test_invalid_transition_raises():
    sm = StateMachine()
    with pytest.raises(InvalidTransitionError):
        sm.transition(SessionStatus.SESSION_COMPLETE)  # can't go INIT -> COMPLETE


def test_transition_records_history():
    sm = StateMachine()
    sm.transition(SessionStatus.SESSION_PLANNING, reason="started")
    sm.transition(SessionStatus.SESSION_RUNNING)
    assert len(sm.history) == 2
    assert sm.history[0]["to"] == "session_planning"


def test_failed_transition_always_allowed():
    sm = StateMachine()
    sm.transition(SessionStatus.SESSION_PLANNING)
    sm.transition(SessionStatus.SESSION_RUNNING)
    sm.transition(SessionStatus.SESSION_FAILED, reason="error")
    assert sm.status == SessionStatus.SESSION_FAILED


def test_all_states_exist():
    expected = [
        "SESSION_INIT", "SESSION_PLANNING", "SESSION_RUNNING", "SESSION_COMPLETE", "SESSION_FAILED",
        "RECON_QUEUED", "RECON_RUNNING", "RECON_COMPLETE", "RECON_FAILED", "RECON_RETRYING",
        "BROWSER_QUEUED", "BROWSER_RUNNING", "BROWSER_CAPTURING", "BROWSER_COMPLETE", "BROWSER_FAILED",
        "ANALYSIS_QUEUED", "ANALYSIS_STATIC", "ANALYSIS_DYNAMIC", "ANALYSIS_DEOBFUSCATING", "ANALYSIS_COMPLETE",
        "CODEGEN_QUEUED", "CODEGEN_GENERATING", "CODEGEN_ITERATING", "CODEGEN_COMPLETE", "CODEGEN_FAILED",
        "VERIFICATION_QUEUED", "VERIFICATION_RUNNING", "VERIFICATION_COMPLETE",
        "REPLAY_QUEUED", "REPLAY_RUNNING", "REPLAY_EVALUATING", "REPLAY_COMPLETE",
        "MEMORY_QUEUED", "MEMORY_WRITING", "MEMORY_WRITTEN",
    ]
    for name in expected:
        assert hasattr(SessionStatus, name), f"Missing state: {name}"
