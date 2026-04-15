"""
Tests for IntakeAIProcessor._apply_patch() typed deep merge.

Key invariants:
- Nested model fields (auth_spec, execution_spec, target_scope, output_spec) are deep-merged,
  not replaced: patching one subfield must not wipe sibling subfields.
- Locked contracts must be returned unchanged.
- SYSTEM_ONLY fields in patch must be silently ignored.
- requested_fields (list) is fully replaced when AI provides it.
- Unknown fields are silently ignored.
"""
from __future__ import annotations

import pytest
from axelo.engine.principal import IntakeAIProcessor
from axelo.models.contracts import (
    AuthSpec,
    ExecutionSpec,
    FieldSpec,
    MissionContract,
    OutputSpec,
    ScopeDefinition,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _processor() -> IntakeAIProcessor:
    return IntakeAIProcessor()


def _base_contract(**kwargs) -> MissionContract:
    """A baseline contract with non-default nested values to catch clobber bugs."""
    return MissionContract(
        target_url="https://example.com",
        objective="Extract product listings with title and price",
        objective_type="extract_data",
        contract_version=1,
        auth_spec=AuthSpec(
            mechanism="cookie",
            login_required=True,
            signing_required=False,
            signing_description="session cookie required",
        ),
        execution_spec=ExecutionSpec(
            stealth_level="high",
            js_rendering="always",
            concurrency=2,
            requests_per_sec=0.5,
            max_pages=10,
            timeout_sec=60,
            budget_usd=0.25,
            time_limit_min=30,
        ),
        output_spec=OutputSpec(
            format="csv",
            dedup=False,
            dataset_name="products",
            session_label="run-01",
        ),
        target_scope=ScopeDefinition(
            mode="single",
            seed_urls=["https://example.com/products"],
            login_required=True,
            credentials_provided=False,
        ),
        **kwargs,
    )


# ── Nested field deep merge ─────────────────────────────────────────────────

def test_patch_auth_spec_subfield_preserves_siblings():
    """Patching auth_spec.mechanism must not wipe login_required."""
    proc = _processor()
    contract = _base_contract()
    patch = {"auth_spec": {"mechanism": "bearer"}}

    result = proc._apply_patch(contract, patch)

    assert result.auth_spec.mechanism == "bearer"           # updated
    assert result.auth_spec.login_required is True          # preserved
    assert result.auth_spec.signing_required is False       # preserved
    assert result.auth_spec.signing_description == "session cookie required"  # preserved


def test_patch_execution_spec_subfield_preserves_siblings():
    """Patching execution_spec.stealth_level must not wipe concurrency."""
    proc = _processor()
    contract = _base_contract()
    patch = {"execution_spec": {"stealth_level": "low"}}

    result = proc._apply_patch(contract, patch)

    assert result.execution_spec.stealth_level == "low"     # updated
    assert result.execution_spec.concurrency == 2           # preserved
    assert result.execution_spec.requests_per_sec == 0.5    # preserved
    assert result.execution_spec.max_pages == 10            # preserved
    assert result.execution_spec.budget_usd == 0.25         # preserved


def test_patch_output_spec_subfield_preserves_siblings():
    proc = _processor()
    contract = _base_contract()
    patch = {"output_spec": {"format": "json"}}

    result = proc._apply_patch(contract, patch)

    assert result.output_spec.format == "json"              # updated
    assert result.output_spec.dedup is False                # preserved
    assert result.output_spec.dataset_name == "products"    # preserved
    assert result.output_spec.session_label == "run-01"     # preserved


def test_patch_target_scope_subfield_preserves_siblings():
    proc = _processor()
    contract = _base_contract()
    patch = {"target_scope": {"mode": "multi"}}

    result = proc._apply_patch(contract, patch)

    assert result.target_scope.mode == "multi"              # updated
    assert result.target_scope.seed_urls == ["https://example.com/products"]  # preserved
    assert result.target_scope.login_required is True       # preserved


# ── Locked contract: reject all AI patches ──────────────────────────────────

def test_locked_contract_is_returned_unchanged():
    proc = _processor()
    contract = _base_contract()
    # Simulate locking by setting locked_at
    locked = contract.model_copy(update={"locked_at": "2026-04-14T10:00:00"})
    patch = {"target_url": "https://evil.com", "objective": "changed"}

    result = proc._apply_patch(locked, patch)

    assert result.target_url == "https://example.com"  # unchanged
    assert result.objective == "Extract product listings with title and price"  # unchanged
    assert result.locked_at == "2026-04-14T10:00:00"   # still locked


# ── SYSTEM_ONLY fields: silently ignored ────────────────────────────────────

def test_system_only_contract_id_not_patchable():
    proc = _processor()
    original_id = "test-contract-id-123"
    contract = MissionContract(
        contract_id=original_id,
        target_url="https://example.com",
        objective="Extract product listings: title, price",
        contract_version=1,
    )
    patch = {"contract_id": "attacker-controlled-id"}

    result = proc._apply_patch(contract, patch)

    assert result.contract_id == original_id  # unchanged


def test_system_only_session_id_not_patchable():
    proc = _processor()
    contract = MissionContract(
        session_id="real-session-abc",
        target_url="https://example.com",
        objective="Extract product listings: title, price",
        contract_version=1,
    )
    patch = {"session_id": "hijacked-session"}

    result = proc._apply_patch(contract, patch)

    assert result.session_id == "real-session-abc"


def test_system_only_field_evidence_not_patchable():
    proc = _processor()
    contract = _base_contract()
    # field_evidence is written post-execution, should never be AI-patchable
    patch = {"field_evidence": [{"field_name": "fake", "found": True}]}

    result = proc._apply_patch(contract, patch)

    assert result.field_evidence == []  # unchanged (empty default)


# ── requested_fields (list): full replacement ───────────────────────────────

def test_requested_fields_list_is_fully_replaced():
    proc = _processor()
    contract = _base_contract(
        requested_fields=[
            FieldSpec(field_name="title"),
            FieldSpec(field_name="price"),
        ]
    )
    new_fields = [
        {"field_name": "title", "field_alias": "Product Title", "required": True, "priority": 1,
         "data_type": "string", "description": "", "example_hint": "", "validation_hint": ""},
        {"field_name": "price", "field_alias": "Price", "required": True, "priority": 1,
         "data_type": "number", "description": "", "example_hint": "", "validation_hint": ""},
        {"field_name": "rating", "field_alias": "Rating", "required": False, "priority": 2,
         "data_type": "number", "description": "", "example_hint": "", "validation_hint": ""},
    ]
    patch = {"requested_fields": new_fields}

    result = proc._apply_patch(contract, patch)

    assert len(result.requested_fields) == 3
    assert result.requested_fields[2].field_name == "rating"


# ── Unknown fields silently ignored ─────────────────────────────────────────

def test_unknown_fields_in_patch_are_silently_ignored():
    proc = _processor()
    contract = _base_contract()
    patch = {
        "totally_made_up_field": "should not appear",
        "target_url": "https://updated.com",
    }

    result = proc._apply_patch(contract, patch)

    assert result.target_url == "https://updated.com"  # valid field updated
    assert not hasattr(result, "totally_made_up_field")  # spurious field ignored


# ── Empty patch is a no-op ───────────────────────────────────────────────────

def test_empty_patch_is_no_op():
    proc = _processor()
    contract = _base_contract()

    result = proc._apply_patch(contract, {})

    assert result.target_url == contract.target_url
    assert result.objective == contract.objective
