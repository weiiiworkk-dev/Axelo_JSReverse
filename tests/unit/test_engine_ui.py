from __future__ import annotations

from unittest.mock import Mock

from axelo.engine.models import (
    AgentExecutionResult,
    ArtifactBundle,
    EnginePlan,
    EngineRunResult,
    MissionState,
    PrincipalAgentState,
    TaskIntent,
)
from axelo.engine.ui import EngineTerminalUI


def test_begin_intake_resets_previous_run_state(monkeypatch):
    ui = EngineTerminalUI()
    monkeypatch.setattr(ui, "_render", lambda: None)

    ui.state.session_id = "AAA-000999"
    ui.state.target_url = "https://example.com"
    ui.state.goal = "old goal"
    ui.state.plan_items = ["prior -> task"]
    ui.state.requirement_items = ["old requirement"]
    ui.state.artifacts = ["crawler: old.py"]
    ui.state.events = ["old event"]

    ui.begin_intake()

    assert ui.state.phase == "intake"
    assert ui.state.session_id == ""
    assert ui.state.target_url == ""
    assert ui.state.goal == ""
    assert ui.state.plan_items == []
    assert ui.state.requirement_items == []
    assert ui.state.artifacts == []
    assert ui.state.footer_hint == "Answer > "
    assert ui.state.events == ["Requirement intake started."]
    assert ui.state.action_items == ["Requirement intake started."]


def test_print_error_keeps_feedback_inside_dashboard_state(monkeypatch):
    ui = EngineTerminalUI()
    monkeypatch.setattr(ui, "_render", lambda: None)

    ui.begin_intake()
    ui.print_error("Target URL is required.")

    assert ui.state.current_prompt == "Target URL is required."
    assert ui.state.events[-1] == "error: Target URL is required."
    assert ui.state.action_items[-1] == "error: Target URL is required."


def test_begin_intake_does_not_render_twice_before_first_question(monkeypatch):
    ui = EngineTerminalUI()
    render = Mock()
    monkeypatch.setattr(ui, "_render", render)

    ui.begin_intake()

    render.assert_not_called()


def test_ui_tracks_actions_and_thoughts_separately(monkeypatch):
    ui = EngineTerminalUI()
    monkeypatch.setattr(ui, "_render", lambda: None)

    ui.begin_intake()
    ui.push_action("Dispatching reverse-agent")
    ui.push_thought("Need stronger runtime evidence before code generation.")

    assert ui.state.action_items[-1] == "Dispatching reverse-agent"
    assert ui.state.thought_items[-1] == "Need stronger runtime evidence before code generation."


def test_ui_updates_principal_snapshot_fields(monkeypatch):
    ui = EngineTerminalUI()
    monkeypatch.setattr(ui, "_render", lambda: None)

    ui.update_principal_snapshot(
        mission_status="active",
        current_focus="trace -> runtime token observation",
        current_uncertainty="Need better nonce provenance.",
        evidence_count=3,
        hypothesis_count=2,
        branch_items=["main [active] score=0.70"],
        coverage={"reverse": 0.6, "verify": 0.2},
        trust_score=0.65,
        trust_level="medium",
        trust_summary="Trust is medium.",
        next_action_hint="runtime_evidence",
        evidence_delta="reverse improved",
    )

    assert ui.state.mission_status == "active"
    assert ui.state.current_focus == "trace -> runtime token observation"
    assert ui.state.current_uncertainty == "Need better nonce provenance."
    assert ui.state.evidence_count == 3
    assert ui.state.hypothesis_count == 2
    assert ui.state.branch_items == ["main [active] score=0.70"]
    assert ui.state.coverage_items == ["reverse: 0.60", "verify: 0.20"]
    assert ui.state.trust_score == 0.65
    assert ui.state.trust_level == "medium"
    assert ui.state.next_action_hint == "runtime_evidence"
    assert ui.state.evidence_delta == "reverse improved"


def test_render_result_surfaces_principal_cognition(monkeypatch):
    ui = EngineTerminalUI()
    monkeypatch.setattr(ui, "_render", lambda: None)

    result = EngineRunResult(
        session_id="AAA-000001",
        success=True,
        summary="Run complete.",
        plan=EnginePlan(
            session_id="AAA-000001",
            summary="plan",
            intent=TaskIntent(intent_type="reverse", confidence=1.0),
            lines_of_inquiry=["Find the surface", "Ground the transport", "Verify delivery"],
        ),
        agent_results=[
            AgentExecutionResult(
                task_id="task-01",
                tool_name="verify",
                agent_role="verifier-agent",
                success=True,
                status="success",
                duration_seconds=1.0,
            )
        ],
        artifact_bundle=ArtifactBundle(session_id="AAA-000001", root_dir=".", index_path="."),
        principal_state=PrincipalAgentState(
            mission=MissionState(session_id="AAA-000001", target_url="https://example.com", objective="crawl"),
            cognition_summary="Mission reached verified completion.",
        ),
    )

    ui.render_result(result)

    assert ui.state.action_items[-1] == "Run complete."
    assert ui.state.thought_items[-1] == "Mission reached verified completion."
