from __future__ import annotations

from types import SimpleNamespace

from axelo.domain.services import AnalysisRoutingService
from axelo.models.execution import ExecutionPlan


def _ctx(**overrides):
    plan = overrides.pop("plan", ExecutionPlan())
    defaults = {
        "target": SimpleNamespace(execution_plan=plan),
        "analysis_cache_hit": False,
        "memory_ctx": {},
        "static_results": {},
        "family_match": SimpleNamespace(template_ready=False, confidence=0.0),
        "difficulty": SimpleNamespace(recommended_path="static"),
        "analysis": SimpleNamespace(ready_for_codegen=True),
        "hypothesis": SimpleNamespace(confidence=0.9),
        "mode_name": "interactive",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_static_only_route_when_skip_codegen_and_cache_hit():
    service = AnalysisRoutingService()
    plan = ExecutionPlan(skip_codegen=True)

    assert service.should_use_static_only(_ctx(plan=plan, analysis_cache_hit=True)) is True


def test_template_codegen_requires_template_ready_and_confident_family():
    service = AnalysisRoutingService()
    plan = ExecutionPlan(skip_codegen=False)
    ctx = _ctx(
        plan=plan,
        family_match=SimpleNamespace(template_ready=True, confidence=0.85),
    )

    assert service.should_use_template_codegen(ctx) is True


def test_confirmation_required_when_analysis_is_not_ready_for_codegen():
    service = AnalysisRoutingService()
    interactive_ctx = _ctx(
        analysis=SimpleNamespace(ready_for_codegen=False),
        hypothesis=SimpleNamespace(confidence=0.49),
    )
    auto_ctx = _ctx(
        analysis=SimpleNamespace(ready_for_codegen=False),
        hypothesis=SimpleNamespace(confidence=0.8),
        mode_name="auto",
    )

    assert service.requires_low_confidence_confirmation(interactive_ctx) is True
    assert service.requires_low_confidence_confirmation(auto_ctx) is False


def test_observed_replay_route_for_high_entropy_observed_request():
    service = AnalysisRoutingService()
    plan = ExecutionPlan(skip_codegen=False)
    ctx = _ctx(
        plan=plan,
        family_match=SimpleNamespace(template_ready=False, confidence=0.2, codegen_strategy="js_bridge"),
        target=SimpleNamespace(
            execution_plan=plan,
            target_requests=[
                SimpleNamespace(
                    url="https://shopee.com.my/api/v4/search/search_items?keyword=iphone",
                    method="GET",
                    request_headers={
                        "x-csrftoken": "abc",
                        "af-ac-enc-dat": "deadbeefcafebabe",
                        "sz-token": "token-value",
                    },
                )
            ],
        ),
    )

    assert service.should_use_observed_replay(ctx) is True
    assert service.choose_route(ctx).route == "contract_replay"


def test_observed_replay_not_blocked_by_non_actionable_family_match():
    service = AnalysisRoutingService()
    plan = ExecutionPlan(skip_codegen=False)
    ctx = _ctx(
        plan=plan,
        family_match=SimpleNamespace(
            template_ready=False,
            confidence=0.95,
            codegen_strategy="python_reconstruct",
        ),
        target=SimpleNamespace(
            execution_plan=plan,
            target_requests=[
                SimpleNamespace(
                    url="https://example.com/api/search?q=phone",
                    method="GET",
                    request_headers={"authorization": "Bearer token"},
                )
            ],
        ),
    )

    assert service.should_use_family_codegen(ctx) is False
    assert service.should_use_template_codegen(ctx) is False
    assert service.should_use_observed_replay(ctx) is True
