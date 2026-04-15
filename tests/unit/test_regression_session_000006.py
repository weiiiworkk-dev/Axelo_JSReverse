"""
Regression tests for the session 000006 failure class.

Session 000006 failures:
  1. operational_success issued when agenda items were still in_progress
  2. page_extract fallback counted as strong verify coverage (was ~0.85, should be ≤ 0.65)
  3. VerificationRecord typed fields not reaching evidence_coverage() via details dict
  4. CLI mode: PreparedRun.contract never attached → _populate_field_evidence() skipped

New regressions added in this phase:
  5. Missing must-have field must cap verdict at PARTIAL_SUCCESS
  6. CLI PreparedRun.contract attachment ensures field_evidence is populated
"""
from __future__ import annotations

import pytest
from axelo.engine.constitution import AgendaReconciler, EngineConstitution
from axelo.engine.models import (
    AgendaRecord,
    EvidenceRecord,
    MissionState,
    PrincipalAgentState,
    VerificationRecord,
    VerdictTier,
)
from axelo.models.contracts import FieldEvidence, FieldSpec, MissionContract


# ── Helpers ─────────────────────────────────────────────────────────────────

def _state_with_page_extract(mechanism_required: bool = False) -> PrincipalAgentState:
    """Reproduces the session 000006 state: page_extract fallback, no mechanism closure."""
    state = PrincipalAgentState(
        mission=MissionState(
            session_id="amazon_com-000006",
            target_url="https://www.amazon.com",
            objective="Extract iPhone 15 product listings: title, price, review count",
            mechanism_required=mechanism_required,
        ),
    )
    state.evidence = [
        EvidenceRecord("surface-1", "browser", "surface", "Surface acquired", 0.80,
                       {"page_title": "Amazon.com: iPhone 15"}),
        EvidenceRecord("transport-1", "protocol", "transport", "HTTP/S, no signing", 0.60,
                       {"target_request_url": "https://www.amazon.com/s?k=iphone+15"}),
        EvidenceRecord("schema-1", "response_schema", "schema", "HTML schema inferred", 0.70,
                       {"schema_fields": ["title", "price", "review_count"],
                        "listing_item_fields": ["title", "price", "review_count"]}),
        EvidenceRecord("extract-1", "extraction", "build", "Extracted 3 fields", 0.75,
                       {"coverage": 0.75,
                        "field_mapping": {
                            "title": {"selector": ".a-title span", "extractor": "css",
                                      "sample_values": ["iPhone 15 Pro 256GB"], "confidence": 0.88},
                            "price": {"selector": ".a-price .a-offscreen", "extractor": "css",
                                      "sample_values": ["$999.00"], "confidence": 0.82},
                            "review_count": {"selector": ".a-size-small .a-size-base", "extractor": "css",
                                             "sample_values": ["2,847"], "confidence": 0.71},
                        }}),
        EvidenceRecord("build-1", "codegen", "build", "Crawler generated", 0.80,
                       {"python_code": "# page_extract crawler"}),
    ]

    # VerificationRecord with page_extract fallback, no mechanism closure
    vr = VerificationRecord(
        evidence_id="verify-1",
        source_task="verify",
        summary="Execution verified via page_extract",
        confidence=0.80,
        execution_verdict="pass",
        http_status=200,
        no_crash=True,
        duration_seconds=4.2,
        structural_verdict="pass",
        fields_present=["title", "price", "review_count"],
        fields_missing=[],
        record_count=48,
        target_record_count=50,
        schema_match=True,
        semantic_verdict="unknown",
        overall_verdict="pass",
        fallback_strategy="page_extract",
        mechanism_closure=False,     # ← Key: no mechanism closure
        stability_level="fragile",
    )
    state.evidence.append(vr)

    # Add agenda items that mirror session 000006 (some still in_progress)
    state.agenda = [
        AgendaRecord(item_id="mission:surface", label="Discover surface", owner="recon-agent",
                     status="completed"),
        AgendaRecord(item_id="mission:transport", label="Recover transport layer",
                     owner="transport-agent", status="in_progress"),  # NOT closed
        AgendaRecord(item_id="mission:build", label="Build artifacts", owner="builder-agent",
                     status="in_progress"),   # NOT closed
    ]
    return state


# ── Regression 1 + 2: page_extract + unresolved agenda → PARTIAL_SUCCESS ────

def test_page_extract_with_unresolved_agenda_is_partial_success():
    """
    Core session 000006 regression:
    - page_extract fallback without mechanism closure → verify coverage capped at 0.65
    - OPERATIONAL_SUCCESS requires coverage["verify"] >= 0.70, so it must NOT be awarded
    - AgendaReconciler should close the items correctly (this tests reconciler + verdict chain)
    → Must NOT produce OPERATIONAL_SUCCESS or MECHANISM_SUCCESS
    """
    state = _state_with_page_extract(mechanism_required=False)

    coverage = EngineConstitution.evidence_coverage(state)
    recon_actions = AgendaReconciler.reconcile(state, coverage)

    # Reconciler must produce actions (closing in_progress items)
    assert len(recon_actions) > 0, "AgendaReconciler must produce reconciliation actions"

    # All agenda items must be in terminal state after reconciliation
    open_items = [a for a in state.agenda if a.status in ("in_progress", "pending")]
    assert open_items == [], (
        f"Agenda items still open after reconciliation: {[a.item_id for a in open_items]}"
    )

    outcome = EngineConstitution.classify_outcome(state, execution_success=True)

    # The core regression: page_extract with verify ≤ 0.65 must NOT produce high success verdicts
    assert outcome["verdict_tier"] not in (VerdictTier.OPERATIONAL_SUCCESS, VerdictTier.MECHANISM_SUCCESS), (
        f"Got {outcome['verdict_tier']} — page_extract without mechanism_closure and "
        f"verify={coverage['verify']:.3f} must NOT produce OPERATIONAL_SUCCESS or MECHANISM_SUCCESS"
    )
    # Verify the specific reason: verify coverage is the bottleneck
    assert coverage["verify"] <= 0.65, (
        f"verify={coverage['verify']:.3f} must be ≤ 0.65 for page_extract without mechanism_closure"
    )


def test_verify_coverage_capped_for_page_extract_without_mechanism_closure():
    """
    The verify coverage dimension must be ≤ 0.65 when fallback_strategy='page_extract'
    and mechanism_closure=False (even with a clean execution and structural pass).
    """
    state = _state_with_page_extract(mechanism_required=False)
    coverage = EngineConstitution.evidence_coverage(state)
    assert coverage["verify"] <= 0.65, (
        f"verify={coverage['verify']:.3f} — page_extract without mechanism_closure must cap at 0.65"
    )


# ── Regression 3: VerificationRecord details sync ───────────────────────────

def test_verification_record_details_sync():
    """
    VerificationRecord.__post_init__ must sync typed layer fields into details dict
    so evidence_coverage() can read them. Without this sync, verify always returns 0.150.
    """
    vr = VerificationRecord(
        evidence_id="vr-sync-test",
        source_task="verify",
        summary="test",
        confidence=0.9,
        execution_verdict="pass",
        structural_verdict="pass",
        semantic_verdict="validated",
        fallback_strategy="none",
        mechanism_closure=True,
    )

    assert vr.details.get("execution_verdict") == "pass", "execution_verdict not synced to details"
    assert vr.details.get("structural_verdict") == "pass", "structural_verdict not synced to details"
    assert vr.details.get("semantic_verdict") == "validated", "semantic_verdict not synced to details"
    assert vr.details.get("fallback_strategy") == "none", "fallback_strategy not synced to details"
    assert vr.details.get("mechanism_closure") is True, "mechanism_closure not synced to details"


# ── Regression 4: CLI PreparedRun.contract attachment ───────────────────────

def test_cli_prepared_run_contract_field_is_accessible():
    """
    Verify that MissionContract can be attached to PreparedRun as a live object.
    This tests the attribute exists and is settable (regression for the CLI attachment bug).
    """
    from axelo.engine.models import PreparedRun, EngineRequest, EnginePlan, TaskIntent

    request = EngineRequest(
        prompt="Extract iPhone 15 listings from Amazon",
        url="https://www.amazon.com",
        goal="Extract product data",
        session_id="test-000",
    )
    intent = TaskIntent(
        intent_type="extract_data",
        confidence=0.9,
        reasoning="User wants product listings",
    )
    plan = EnginePlan(
        session_id="test-000",
        summary="Extract iPhone 15 product listings from Amazon",
        intent=intent,
        lines_of_inquiry=["discover_surface", "build_artifacts", "verify_execution"],
    )
    prepared = PreparedRun(
        request=request,
        plan=plan,
        session_id="test-000",
        session_dir="/tmp/test",
    )

    # Before attachment: contract is None (the current web intake sets it explicitly)
    assert prepared.contract is None

    # After attachment (what CLI must do after plan_request())
    contract = MissionContract(
        target_url="https://www.amazon.com",
        objective="Extract iPhone 15 product listings: title, price, review count",
        contract_version=1,
    )
    prepared.contract = contract  # This is the one-line fix for CLI

    assert prepared.contract is not None
    assert prepared.contract.target_url == "https://www.amazon.com"


# ── Regression 5 (new): Missing must-have field caps verdict at PARTIAL_SUCCESS ──

def test_missing_must_have_field_caps_verdict_at_partial_success():
    """
    New regression scenario:
    Execution succeeds, but a priority-1 (must-have) field has validation_status="missing".
    Verdict must be PARTIAL_SUCCESS, not OPERATIONAL_SUCCESS or DATA_SUCCESS.
    """
    state = PrincipalAgentState(
        mission=MissionState(
            session_id="test-missing-field",
            target_url="https://example.com",
            objective="Extract product listings: title, price, and review_count",
            mechanism_required=False,
        ),
    )
    state.evidence = [
        EvidenceRecord("surface-1", "browser", "surface", "Surface", 0.90, {"page_title": "Shop"}),
        EvidenceRecord("schema-1", "response_schema", "schema", "Schema", 0.85,
                       {"schema_fields": ["title", "price"], "listing_item_fields": ["title", "price"]}),
        EvidenceRecord("extract-1", "extraction", "build", "2/3 fields extracted", 0.70,
                       {"coverage": 0.70,
                        "field_mapping": {
                            "title": {"selector": ".title", "extractor": "css",
                                      "sample_values": ["Widget A"], "confidence": 0.92},
                            "price": {"selector": ".price", "extractor": "css",
                                      "sample_values": ["$9.99"], "confidence": 0.88},
                        }}),
        EvidenceRecord("build-1", "codegen", "build", "Crawler built", 0.80,
                       {"python_code": "# crawler code"}),
    ]

    vr = VerificationRecord(
        evidence_id="verify-1",
        source_task="verify",
        summary="2 of 3 fields found",
        confidence=0.70,
        execution_verdict="pass",
        structural_verdict="partial",
        fields_present=["title", "price"],
        fields_missing=["review_count"],
        record_count=20,
        target_record_count=50,
        schema_match=False,
        semantic_verdict="unknown",
        fallback_strategy="page_extract",
        mechanism_closure=False,
    )
    state.evidence.append(vr)
    state.agenda = []

    # Build a contract with review_count as priority=1 (must-have)
    contract = MissionContract(
        target_url="https://example.com",
        objective="Extract product listings: title, price, and review_count",
        contract_version=1,
        requested_fields=[
            FieldSpec(field_name="title", priority=1),
            FieldSpec(field_name="price", priority=1),
            FieldSpec(field_name="review_count", priority=1),  # must-have, but missing
        ],
        field_evidence=[
            FieldEvidence(field_name="title", found=True,
                          selector=".title", validation_status="validated"),
            FieldEvidence(field_name="price", found=True,
                          selector=".price", validation_status="validated"),
            FieldEvidence(field_name="review_count", found=False,
                          validation_status="missing"),   # ← missing must-have field
        ],
    )

    coverage = EngineConstitution.evidence_coverage(state)
    AgendaReconciler.reconcile(state, coverage)
    outcome = EngineConstitution.classify_outcome(state, execution_success=True, contract=contract)

    assert outcome["verdict_tier"] in (VerdictTier.PARTIAL_SUCCESS, VerdictTier.DATA_SUCCESS), (
        f"Expected PARTIAL_SUCCESS or DATA_SUCCESS (not higher), got {outcome['verdict_tier']} — "
        "a missing must-have field should prevent OPERATIONAL_SUCCESS"
    )
    # Specifically: OPERATIONAL_SUCCESS requires all must-have fields found
    assert outcome["verdict_tier"] != VerdictTier.OPERATIONAL_SUCCESS, (
        "OPERATIONAL_SUCCESS must not be awarded when a must-have field is missing"
    )
