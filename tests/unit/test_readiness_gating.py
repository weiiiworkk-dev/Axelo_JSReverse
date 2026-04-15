"""
Tests for the deterministic start gating logic in IntakeAIProcessor._compute_readiness().

Each test targets one gate in isolation. The final test verifies that all gates
passing produces is_ready=True regardless of AI-reported confidence.
"""
from __future__ import annotations

import pytest
from axelo.engine.principal import IntakeAIProcessor
from axelo.models.contracts import MissionContract, FieldSpec


# ── Helpers ─────────────────────────────────────────────────────────────────

def _processor() -> IntakeAIProcessor:
    return IntakeAIProcessor()


def _ai(confidence: float = 0.9, blocking: list[str] | None = None) -> dict:
    """Minimal AI assessment dict."""
    return {
        "confidence": confidence,
        "blocking_gaps": blocking or [],
        "missing_info": [],
        "suggestions": [],
    }


def _contract(**kwargs) -> MissionContract:
    """Build a MissionContract with sane defaults; override with kwargs."""
    defaults = dict(
        target_url="https://example.com",
        objective="Extract product listings including title, price, and rating",
        objective_type="extract_data",
        requested_fields=[FieldSpec(field_name="title", field_alias="title")],
        contract_version=1,
    )
    defaults.update(kwargs)
    return MissionContract(**defaults)


# ── Gate 1: Valid URL ────────────────────────────────────────────────────────

def test_gate1_missing_url_blocks_start():
    proc = _processor()
    contract = _contract(target_url="")
    result = proc._compute_readiness(contract, _ai())
    assert not result.is_ready
    assert any("URL" in g for g in result.blocking_gaps)


def test_gate1_relative_url_blocks_start():
    proc = _processor()
    contract = _contract(target_url="example.com/products")
    result = proc._compute_readiness(contract, _ai())
    assert not result.is_ready
    assert any("URL" in g for g in result.blocking_gaps)


def test_gate1_valid_http_url_passes():
    proc = _processor()
    contract = _contract(target_url="http://example.com")
    result = proc._compute_readiness(contract, _ai())
    assert not any("URL" in g for g in result.blocking_gaps)


def test_gate1_valid_https_url_passes():
    proc = _processor()
    contract = _contract(target_url="https://shop.example.com/products")
    result = proc._compute_readiness(contract, _ai())
    assert not any("URL" in g for g in result.blocking_gaps)


# ── Gate 2: Executable objective ────────────────────────────────────────────

def test_gate2_too_short_objective_blocks_start():
    proc = _processor()
    contract = _contract(objective="crawl")  # 5 chars, also in trivial set
    result = proc._compute_readiness(contract, _ai())
    assert not result.is_ready
    assert any("Objective" in g or "vague" in g for g in result.blocking_gaps)


def test_gate2_bare_keyword_blocks_start():
    proc = _processor()
    # "scrape" is in _TRIVIAL_OBJECTIVES
    contract = _contract(objective="scrape it please yeah sure ok done go")
    # This is long enough (>15) but trivial check is on objective.lower() equality
    # The 15-char check would pass for this. Let's use a real trivial one:
    contract2 = _contract(objective="抓取")
    result2 = proc._compute_readiness(contract2, _ai())
    assert not result2.is_ready


def test_gate2_specific_objective_passes():
    proc = _processor()
    contract = _contract(objective="Extract iPhone 15 product listings with title, price")
    result = proc._compute_readiness(contract, _ai())
    assert not any("Objective" in g or "vague" in g for g in result.blocking_gaps)


# ── Gate 3: At least one data signal ────────────────────────────────────────

def test_gate3_no_fields_and_no_type_blocks_start():
    proc = _processor()
    contract = _contract(requested_fields=[], objective_type="")
    result = proc._compute_readiness(contract, _ai())
    assert not result.is_ready
    assert any("fields" in g.lower() or "intent" in g.lower() for g in result.blocking_gaps)


def test_gate3_objective_type_alone_satisfies():
    proc = _processor()
    contract = _contract(requested_fields=[], objective_type="extract_data")
    result = proc._compute_readiness(contract, _ai())
    assert not any("fields" in g.lower() or "intent" in g.lower() for g in result.blocking_gaps)


def test_gate3_fields_alone_satisfies():
    proc = _processor()
    contract = _contract(
        requested_fields=[FieldSpec(field_name="price", field_alias="price")],
        objective_type="",
    )
    result = proc._compute_readiness(contract, _ai())
    assert not any("fields" in g.lower() or "intent" in g.lower() for g in result.blocking_gaps)


# ── Internal sanity: contract_version < 1 → silent not-ready ────────────────

def test_gate4_unprocessed_contract_blocks_start_silently():
    """
    contract_version=0 → is_ready=False but blocking_gaps is EMPTY.
    The welcome state is its own feedback; no user-visible version message.
    """
    proc = _processor()
    contract = _contract(contract_version=0)
    result = proc._compute_readiness(contract, _ai())
    assert not result.is_ready
    assert result.blocking_gaps == []   # silent — no user-visible message


def test_gate4_version_1_passes():
    proc = _processor()
    contract = _contract(contract_version=1)
    result = proc._compute_readiness(contract, _ai())
    assert not any("processed" in g.lower() for g in result.blocking_gaps)


# ── Gate 5: AI-reported blocking gaps ───────────────────────────────────────

def test_gate5_ai_blocking_gap_blocks_start():
    proc = _processor()
    contract = _contract()
    ai = _ai(blocking=["Login credentials required but not provided"])
    result = proc._compute_readiness(contract, ai)
    assert not result.is_ready
    assert "Login credentials required but not provided" in result.blocking_gaps


def test_gate5_empty_ai_blocking_passes():
    proc = _processor()
    contract = _contract()
    ai = _ai(blocking=[])
    result = proc._compute_readiness(contract, ai)
    assert not any("credential" in g.lower() for g in result.blocking_gaps)


# ── All gates passing → is_ready=True ───────────────────────────────────────

def test_all_gates_pass_produces_is_ready():
    proc = _processor()
    contract = _contract(
        target_url="https://www.amazon.com/s?k=iphone+15",
        objective="Extract iPhone 15 product listings: title, price, review count",
        objective_type="extract_data",
        requested_fields=[
            FieldSpec(field_name="title", field_alias="title"),
            FieldSpec(field_name="price", field_alias="price"),
        ],
        contract_version=2,
    )
    ai = _ai(confidence=0.85, blocking=[])
    result = proc._compute_readiness(contract, ai)
    assert result.is_ready
    assert result.blocking_gaps == []
    assert result.confidence == 0.85


def test_is_ready_does_not_require_confidence_threshold():
    """
    is_ready must be True when all gates pass, even if AI confidence < 0.75.
    Confidence is decorative — not the gate.
    """
    proc = _processor()
    contract = _contract()  # All sane defaults
    ai = _ai(confidence=0.50, blocking=[])  # AI is unsure but no blocking gaps
    result = proc._compute_readiness(contract, ai)
    assert result.is_ready  # Gates all pass → ready
    assert result.confidence == 0.50  # Confidence preserved as-is (no gates failed)


def test_confidence_not_capped_when_gate_fails():
    """
    Confidence must NOT be clamped even when a gate fails.
    Confidence is display-only — the backend passes it through unchanged.
    """
    proc = _processor()
    contract = _contract(target_url="")  # Gate 1 fails
    ai = _ai(confidence=0.95, blocking=[])
    result = proc._compute_readiness(contract, ai)
    assert not result.is_ready
    assert result.confidence == 0.95   # Passed through unchanged — no cap


def test_confidence_not_required_for_ready():
    """
    is_ready can be True even when AI confidence is low (< 0.75).
    Only the gate list determines readiness.
    """
    proc = _processor()
    contract = _contract()   # All sane defaults, all gates pass
    ai = _ai(confidence=0.30, blocking=[])
    result = proc._compute_readiness(contract, ai)
    assert result.is_ready          # Gates pass → ready
    assert result.confidence == 0.30   # Low confidence preserved, does not block
