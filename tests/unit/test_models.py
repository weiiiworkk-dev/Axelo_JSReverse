"""核心数据模型单元测试"""
import pytest
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult, StageStatus
from axelo.models.target import TargetSite, RequestCapture, BrowserProfile
from axelo.models.bundle import JSBundle
from axelo.models.analysis import (
    TokenCandidate, StaticAnalysis, HookIntercept,
    DynamicAnalysis, AIHypothesis,
)
from pathlib import Path


class TestPipelineState:
    def test_create_state(self):
        state = PipelineState(session_id="test01", mode="interactive")
        assert state.session_id == "test01"
        assert state.mode == "interactive"
        assert state.current_stage_index == 0
        assert not state.completed

    def test_set_and_get_artifact(self, tmp_path):
        state = PipelineState(session_id="test01")
        p = tmp_path / "output.py"
        p.write_text("# code")
        state.set_artifact("script", p)
        assert state.get_artifact("script") == p

    def test_get_missing_artifact_returns_none(self):
        state = PipelineState(session_id="test01")
        assert state.get_artifact("nonexistent") is None


class TestDecision:
    def test_decision_has_id(self):
        d = Decision(
            stage="s1_crawl",
            decision_type=DecisionType.CONFIRM_TARGET,
            prompt="test",
        )
        assert len(d.decision_id) == 8

    def test_decision_with_options(self):
        d = Decision(
            stage="s2_fetch",
            decision_type=DecisionType.SELECT_OPTION,
            prompt="Select bundle",
            options=["bundle_a", "bundle_b"],
            default="bundle_a",
        )
        assert d.options == ["bundle_a", "bundle_b"]
        assert d.default == "bundle_a"


class TestRequestCapture:
    def test_basic_capture(self):
        cap = RequestCapture(
            url="https://api.example.com/search",
            method="POST",
            request_headers={"X-Sign": "abc123", "Content-Type": "application/json"},
            response_status=200,
        )
        assert cap.url == "https://api.example.com/search"
        assert cap.method == "POST"
        assert cap.response_status == 200

    def test_token_fields_default_empty(self):
        cap = RequestCapture(url="https://x.com", method="GET")
        assert cap.token_fields == []

    def test_binary_body_serializes_without_utf8_failure(self):
        cap = RequestCapture(
            url="https://api.example.com/data",
            method="POST",
            request_body=b"\x80\x81\x82payload",
            response_body=b"\x00\x01\x02binary",
        )
        target = TargetSite(
            url="https://example.com",
            session_id="test01",
            interaction_goal="demo",
            captured_requests=[cap],
            target_requests=[cap],
        )
        payload = target.model_dump(mode="json")
        assert isinstance(payload["captured_requests"][0]["request_body"], str)
        assert isinstance(payload["captured_requests"][0]["response_body"], str)
        assert target.model_dump_json()


class TestTokenCandidate:
    def test_candidate_creation(self):
        c = TokenCandidate(
            func_id="bundle01:signRequest",
            token_type="hmac",
            confidence=0.85,
            evidence=["包含关键词 'hmac'", "函数名含 sign"],
            request_field="X-Sign",
        )
        assert c.confidence == 0.85
        assert c.token_type == "hmac"

    def test_confidence_bounds(self):
        c = TokenCandidate(func_id="x:y", token_type="md5", confidence=0.0)
        assert 0.0 <= c.confidence <= 1.0


class TestAIHypothesis:
    def test_hypothesis_defaults(self):
        h = AIHypothesis(
            algorithm_description="HMAC-SHA256 with timestamp",
            codegen_strategy="python_reconstruct",
            python_feasibility=0.9,
            confidence=0.85,
        )
        assert h.steps == []
        assert h.inputs == []
        assert h.outputs == {}

    def test_codegen_strategy_values(self):
        for strategy in ("python_reconstruct", "js_bridge"):
            h = AIHypothesis(
                algorithm_description="test",
                codegen_strategy=strategy,
            )
            assert h.codegen_strategy == strategy
