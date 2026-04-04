from __future__ import annotations

from types import SimpleNamespace

import pytest

from axelo.app.flows.analysis_flow import AnalysisFlow
from axelo.domain.services.analysis_routing_service import AnalysisRouteDecision
from axelo.models.analysis import AIHypothesis, StaticAnalysis, TokenCandidate
from axelo.models.execution import ExecutionPlan
from axelo.models.signature import SignatureSpec
from axelo.models.target import RequestCapture, TargetSite


@pytest.mark.asyncio
async def test_analysis_flow_materializes_template_codegen_branch(monkeypatch):
    class FakeStore:
        def save(self, _state):
            return None

    class FakeDB:
        def get_site_pattern(self, _domain):
            return None

    class FakeRetriever:
        def get_all_templates(self):
            return [SimpleNamespace(name="hmac-sha256-timestamp", algorithm_type="hmac")]

    class FakeAnalysisCache:
        def save(self, *args, **kwargs):
            return None

    class FakeRoutingService:
        def should_run_dynamic(self, _ctx) -> bool:
            return False

        def should_use_static_only(self, _ctx) -> bool:
            return False

        def choose_route(self, _ctx) -> AnalysisRouteDecision:
            return AnalysisRouteDecision(route="family_template", requires_ai=False, use_template_codegen=True)

        def should_use_template_codegen(self, _ctx) -> bool:
            return True

        def requires_low_confidence_confirmation(self, _ctx) -> bool:
            return False

        def top_static_confidence(self, _static_results) -> float:
            return 0.91

    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.classify",
        lambda target, static_results, known_pattern=None: SimpleNamespace(level="easy", reasons=[], recommended_path="static_only"),
    )
    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.detect_signature_family",
        lambda *args, **kwargs: SimpleNamespace(
            family_id="hmac-sha256-timestamp",
            algorithm_type="hmac",
            confidence=0.91,
            template_name="hmac-sha256-timestamp",
            template_ready=True,
        ),
    )
    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.build_hypothesis_from_family",
        lambda match, target: AIHypothesis(
            algorithm_description="Use HMAC template",
            generator_func_ids=["bundle:sign"],
            steps=["sign request"],
            inputs=["url", "method", "body"],
            outputs={"X-Sign": "hex digest"},
            codegen_strategy="python_reconstruct",
            confidence=match.confidence,
            template_name=match.template_name,
            secret_candidate="template_secret",
        ),
    )
    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.build_signature_spec",
        lambda target, hypothesis, static_results, dynamic: SignatureSpec(
            algorithm_id="hmac",
            codegen_strategy="python_reconstruct",
            confidence=0.91,
        ),
    )

    flow = AnalysisFlow(
        store=FakeStore(),
        db=FakeDB(),
        retriever=FakeRetriever(),
        analysis_cache=FakeAnalysisCache(),
        routing_service=FakeRoutingService(),
    )

    target = TargetSite(
        url="https://example.com/search?q=phone",
        session_id="flow01",
        interaction_goal="collect products",
    )
    target.execution_plan = ExecutionPlan(skip_codegen=False)

    ctx = SimpleNamespace(
        sid="flow01",
        memory_ctx={},
        static_results={
            "bundle": StaticAnalysis(
                bundle_id="bundle",
                token_candidates=[TokenCandidate(func_id="bundle:sign", token_type="hmac", confidence=0.91)],
            )
        },
        target=target,
        dynamic=None,
        difficulty=None,
        result=SimpleNamespace(difficulty=None, error=None),
        state=SimpleNamespace(workflow_status="", manual_review_reason="", current_stage_index=0),
        workflow=SimpleNamespace(checkpoint=lambda *args, **kwargs: {}, request_manual_review=lambda *args, **kwargs: {}),
        mode=SimpleNamespace(gate=None),
        mode_name="auto",
        governor=SimpleNamespace(allow_ai=lambda cost, plan: True),
        cost=SimpleNamespace(
            set_route=lambda route: None,
            set_stage_timing=lambda *args, **kwargs: None,
        ),
        bundle_hashes=["abc123"],
        analysis_cache_hit=True,
        family_match=None,
        analysis=None,
        hypothesis=None,
        scan_report=None,
    )

    artifacts = await flow.run(ctx)

    assert artifacts is not None
    assert artifacts.hypothesis is not None
    assert artifacts.analysis is not None
    assert artifacts.analysis.ready_for_codegen is True


@pytest.mark.asyncio
async def test_analysis_flow_materializes_family_codegen_branch(monkeypatch):
    class FakeStore:
        def save(self, _state):
            return None

    class FakeDB:
        def get_site_pattern(self, _domain):
            return None

    class FakeRetriever:
        def get_all_templates(self):
            return []

    class FakeAnalysisCache:
        def save(self, *args, **kwargs):
            return None

    class FakeRoutingService:
        def should_run_dynamic(self, _ctx) -> bool:
            return False

        def should_use_static_only(self, _ctx) -> bool:
            return False

        def choose_route(self, _ctx) -> AnalysisRouteDecision:
            return AnalysisRouteDecision(route="bridge_template", requires_ai=False, use_template_codegen=False)

        def should_use_template_codegen(self, _ctx) -> bool:
            return False

        def should_use_family_codegen(self, _ctx) -> bool:
            return True

        def requires_low_confidence_confirmation(self, _ctx) -> bool:
            return False

        def top_static_confidence(self, _static_results) -> float:
            return 0.0

    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.classify",
        lambda target, static_results, known_pattern=None: SimpleNamespace(level="easy", reasons=[], recommended_path="static_only"),
    )
    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.detect_signature_family",
        lambda *args, **kwargs: SimpleNamespace(
            family_id="mtop-h5-token",
            algorithm_type="mtop",
            confidence=0.94,
            template_name="",
            template_ready=False,
            codegen_strategy="js_bridge",
        ),
    )
    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.build_hypothesis_from_family",
        lambda match, target: AIHypothesis(
            algorithm_description="Use MTop bridge",
            generator_func_ids=[],
            steps=["bridge sign"],
            inputs=["url", "cookies"],
            outputs={"sign": "digest", "t": "timestamp"},
            codegen_strategy="js_bridge",
            confidence=match.confidence,
            template_name="",
            secret_candidate="",
        ),
    )
    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.build_signature_spec",
        lambda target, hypothesis, static_results, dynamic: SignatureSpec(
            algorithm_id="mtop",
            codegen_strategy="js_bridge",
            confidence=0.94,
        ),
    )

    flow = AnalysisFlow(
        store=FakeStore(),
        db=FakeDB(),
        retriever=FakeRetriever(),
        analysis_cache=FakeAnalysisCache(),
        routing_service=FakeRoutingService(),
    )

    target = TargetSite(
        url="https://www.lazada.com.my/#?",
        session_id="flow02",
        interaction_goal="collect products",
    )
    target.execution_plan = ExecutionPlan(skip_codegen=False)

    ctx = SimpleNamespace(
        sid="flow02",
        memory_ctx={},
        static_results={"bundle": StaticAnalysis(bundle_id="bundle")},
        target=target,
        dynamic=None,
        difficulty=None,
        result=SimpleNamespace(difficulty=None, error=None),
        state=SimpleNamespace(workflow_status="", manual_review_reason="", current_stage_index=0),
        workflow=SimpleNamespace(checkpoint=lambda *args, **kwargs: {}, request_manual_review=lambda *args, **kwargs: {}),
        mode=SimpleNamespace(gate=None),
        mode_name="auto",
        governor=SimpleNamespace(allow_ai=lambda cost, plan: True),
        cost=SimpleNamespace(
            set_route=lambda route: None,
            set_stage_timing=lambda *args, **kwargs: None,
        ),
        bundle_hashes=["abc123"],
        analysis_cache_hit=False,
        family_match=None,
        analysis=None,
        hypothesis=None,
        scan_report=None,
    )

    artifacts = await flow.run(ctx)

    assert artifacts is not None
    assert artifacts.hypothesis is not None
    assert artifacts.hypothesis.codegen_strategy == "js_bridge"
    assert artifacts.analysis is not None
    assert artifacts.analysis.ready_for_codegen is True


@pytest.mark.asyncio
async def test_analysis_flow_materializes_observed_replay_branch(monkeypatch):
    class FakeStore:
        def save(self, _state):
            return None

    class FakeDB:
        def get_site_pattern(self, _domain):
            return None

    class FakeRetriever:
        def get_all_templates(self):
            return []

    class FakeAnalysisCache:
        def save(self, *args, **kwargs):
            return None

    class FakeRoutingService:
        def should_run_dynamic(self, _ctx) -> bool:
            return False

        def should_use_static_only(self, _ctx) -> bool:
            return False

        def choose_route(self, _ctx) -> AnalysisRouteDecision:
            return AnalysisRouteDecision(route="contract_replay", requires_ai=False)

        def should_use_template_codegen(self, _ctx) -> bool:
            return False

        def should_use_family_codegen(self, _ctx) -> bool:
            return False

        def should_use_observed_replay(self, _ctx) -> bool:
            return True

        def requires_low_confidence_confirmation(self, _ctx) -> bool:
            return False

        def top_static_confidence(self, _static_results) -> float:
            return 0.0

    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.classify",
        lambda target, static_results, known_pattern=None: SimpleNamespace(level="easy", reasons=[], recommended_path="static_only"),
    )
    monkeypatch.setattr(
        "axelo.app.flows.analysis_flow.detect_signature_family",
        lambda *args, **kwargs: SimpleNamespace(
            family_id="unknown",
            algorithm_type="unknown",
            confidence=0.1,
            template_name="",
            template_ready=False,
            codegen_strategy="js_bridge",
        ),
    )

    flow = AnalysisFlow(
        store=FakeStore(),
        db=FakeDB(),
        retriever=FakeRetriever(),
        analysis_cache=FakeAnalysisCache(),
        routing_service=FakeRoutingService(),
    )

    target = TargetSite(
        url="https://example.com/search?q=phone",
        session_id="flow03",
        interaction_goal="collect products",
    )
    target.execution_plan = ExecutionPlan(skip_codegen=False)
    target.target_requests = [
        RequestCapture(
            url="https://example.com/api/search?q=phone",
            method="GET",
            request_headers={
                "x-csrftoken": "abc123",
                "authorization": "Bearer token",
            },
        )
    ]

    ctx = SimpleNamespace(
        sid="flow03",
        memory_ctx={},
        static_results={"bundle": StaticAnalysis(bundle_id="bundle")},
        target=target,
        dynamic=None,
        difficulty=None,
        result=SimpleNamespace(difficulty=None, error=None),
        state=SimpleNamespace(workflow_status="", manual_review_reason="", current_stage_index=0),
        workflow=SimpleNamespace(checkpoint=lambda *args, **kwargs: {}, request_manual_review=lambda *args, **kwargs: {}),
        mode=SimpleNamespace(gate=None),
        mode_name="auto",
        governor=SimpleNamespace(allow_ai=lambda cost, plan: True),
        cost=SimpleNamespace(
            set_route=lambda route: None,
            set_stage_timing=lambda *args, **kwargs: None,
        ),
        bundle_hashes=["abc123"],
        analysis_cache_hit=False,
        family_match=None,
        analysis=None,
        hypothesis=None,
        scan_report=None,
    )

    artifacts = await flow.run(ctx)

    assert artifacts is not None
    assert artifacts.hypothesis is not None
    assert artifacts.hypothesis.template_name == "contract_replay"
    assert artifacts.analysis is not None
    assert artifacts.analysis.ready_for_codegen is True
