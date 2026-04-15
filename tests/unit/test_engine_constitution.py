from __future__ import annotations

from axelo.engine.constitution import EngineConstitution
from axelo.engine.models import EvidenceRecord, MissionState, PrincipalAgentState


def _state(*records: EvidenceRecord, mechanism_required: bool = True) -> PrincipalAgentState:
    return PrincipalAgentState(
        mission=MissionState(
            session_id="AAA-000001",
            target_url="https://example.com",
            objective="Collect product listing data and reverse any request signing required",
            mechanism_required=mechanism_required,
        ),
        evidence=list(records),
    )


def test_recommend_next_action_prioritizes_surface_then_transport():
    state = _state()
    assert EngineConstitution.recommend_next_action(state).objective == "discover_surface"

    state = _state(
        EvidenceRecord(
            evidence_id="surface-1",
            kind="browser",
            source_task="surface",
            summary="surface recovered",
            confidence=0.9,
            details={"page_title": "Example", "js_bundles": ["https://example.com/app.js"]},
        )
    )
    assert EngineConstitution.recommend_next_action(state).objective == "recover_transport"


def test_recommend_next_action_advances_to_build_and_verify_when_grounded():
    state = _state(
        EvidenceRecord("surface-1", "browser", "surface", "surface", 0.9, {"page_title": "Example"}),
        EvidenceRecord("transport-1", "protocol", "transport", "transport", 0.9, {"target_request_url": "https://example.com/api/list", "request_fields": ["token"], "required_headers": ["x-token"]}),
        EvidenceRecord("reverse-1", "static", "reverse", "reverse", 0.9, {"algorithms": ["sha256"], "signature_candidates": [{"type": "sha256"}]}),
        EvidenceRecord("runtime-1", "runtime_hook", "runtime", "runtime", 0.9, {"runtime_sensitive_fields": ["token"], "hook_points": ["fetch"]}),
        EvidenceRecord("schema-1", "response_schema", "schema", "schema", 0.9, {"schema_fields": ["items.title"], "listing_item_fields": ["title", "price"]}),
    )
    assert EngineConstitution.recommend_next_action(state).objective == "build_artifacts"

    state.evidence.extend(
        [
            EvidenceRecord("extract-1", "extraction", "build", "extract", 1.0, {"coverage": 1.0}),
            EvidenceRecord("build-1", "codegen", "build", "build", 0.9, {"python_code": "print('crawler')"}),
        ]
    )
    assert EngineConstitution.recommend_next_action(state).objective == "verify_execution"


def test_classify_outcome_data_success_when_mechanism_unproven_but_data_returned():
    """
    With mechanism_required=True but no reverse/runtime evidence, the mechanism_assessment()
    auto-generates mechanism blockers. However, data was actually extracted and verify passed.
    Mechanism blockers are a research finding (unproven signing mechanism), NOT an execution
    failure. DATA_SUCCESS is the correct verdict: the system delivered data even if it couldn't
    prove the signing mechanism. Only captcha/blocked/no-data execution failures prevent DATA_SUCCESS.
    """
    state = _state(
        EvidenceRecord("surface-1", "browser", "surface", "surface", 0.9, {"page_title": "Example"}),
        EvidenceRecord("transport-1", "protocol", "transport", "transport", 0.9, {"target_request_url": "https://example.com/api/list", "request_fields": ["token"], "required_headers": ["x-token"]}),
        EvidenceRecord("schema-1", "response_schema", "schema", "schema", 0.9, {"schema_fields": ["items.title"], "listing_item_fields": ["title", "price"]}),
        EvidenceRecord("extract-1", "extraction", "build", "extract", 1.0, {"coverage": 1.0}),
        EvidenceRecord("build-1", "codegen", "build", "build", 0.9, {"python_code": "print('crawler')"}),
        EvidenceRecord("verify-1", "verify", "verify", "verify", 1.0, {"success": True, "execution_verdict": "pass", "mechanism_verdict": "replay_only"}),
    )
    outcome = EngineConstitution.classify_outcome(state, execution_success=True)
    # Data extracted + verify passed → DATA_SUCCESS even though mechanism is unproven
    assert outcome["verdict_tier"] == "data_success"
    assert outcome["status"] == "success"


def test_classify_outcome_marks_structural_success_when_all_evidence_grounded_but_no_hypothesis():
    """
    With mechanism_required=True and all evidence grounded (reverse + runtime covered),
    but no hypotheses validated, MECHANISM_SUCCESS cannot be awarded (mech_ok requires either
    a hypothesis with posterior >= 0.75 or mechanism_required=False).
    STRUCTURAL_SUCCESS is the correct ceiling: paths confirmed, but mechanism not hypothesis-validated.
    (Old test expected "mechanism_validated"; new model requires hypothesis validation for that tier.)
    """
    state = _state(
        EvidenceRecord("surface-1", "browser", "surface", "surface", 0.9, {"page_title": "Example"}),
        EvidenceRecord("transport-1", "protocol", "transport", "transport", 0.9, {"target_request_url": "https://example.com/api/list", "request_fields": ["token"], "required_headers": ["x-token"]}),
        EvidenceRecord("reverse-1", "static", "reverse", "reverse", 0.9, {"algorithms": ["sha256"], "signature_candidates": [{"type": "sha256"}]}),
        EvidenceRecord("runtime-1", "runtime_hook", "runtime", "runtime", 0.9, {"runtime_sensitive_fields": ["token"], "hook_points": ["fetch"]}),
        EvidenceRecord("schema-1", "response_schema", "schema", "schema", 0.9, {"schema_fields": ["items.title"], "listing_item_fields": ["title", "price"]}),
        EvidenceRecord("extract-1", "extraction", "build", "extract", 1.0, {"coverage": 1.0}),
        EvidenceRecord("build-1", "codegen", "build", "build", 0.9, {"python_code": "print('crawler')"}),
        EvidenceRecord("verify-1", "verify", "verify", "verify", 1.0, {"success": True, "execution_verdict": "pass", "mechanism_verdict": "validated"}),
    )
    outcome = EngineConstitution.classify_outcome(state, execution_success=True)
    # All evidence grounded, no blocking conditions → STRUCTURAL_SUCCESS
    # Not MECHANISM_SUCCESS because hypotheses=[] and mechanism_required=True
    assert outcome["verdict_tier"] == "structural_success"
    assert outcome["outcome"] == "replay_success"
    assert outcome["status"] == "success"
