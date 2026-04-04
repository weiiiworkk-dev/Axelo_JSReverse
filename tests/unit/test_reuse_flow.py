from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from axelo.app.flows.reuse_flow import ReuseFlow
from axelo.models.analysis import AnalysisResult
from axelo.models.codegen import GeneratedCode
from axelo.models.execution import ExecutionPlan, ExecutionTier


class _Cost:
    def __init__(self) -> None:
        self.route_label = ""
        self.reuse_hits: list[str] = []

    def set_route(self, label: str) -> None:
        self.route_label = label

    def add_reuse_hit(self, hit: str) -> None:
        self.reuse_hits.append(hit)


class _Store:
    def __init__(self) -> None:
        self.saved = 0

    def save(self, _state) -> None:
        self.saved += 1


class _Workflow:
    def request_manual_review(self, *_args, **_kwargs):
        return {"status": "manual_review"}

    def checkpoint(self, *_args, **_kwargs):
        return {"status": "checkpoint"}


def _ctx(plan: ExecutionPlan, *, adapter_candidate=None):
    return SimpleNamespace(
        sid="reuse01",
        target=SimpleNamespace(execution_plan=plan, trace={}, compliance=SimpleNamespace(allow_live_verification=False)),
        cost=_Cost(),
        analysis=None,
        state=SimpleNamespace(workflow_status="", manual_review_reason="", execution_plan={}),
        workflow=_Workflow(),
        result=SimpleNamespace(error=None, output_dir=None, adapter_reused=False),
        adapter_candidate=adapter_candidate,
        output_dir=Path("C:/tmp"),
        generated=None,
        verified=False,
    )


@pytest.mark.asyncio
async def test_reuse_flow_requests_manual_review():
    store = _Store()
    flow = ReuseFlow(store=store, workflow_store=None, adapter_registry=SimpleNamespace())
    ctx = _ctx(ExecutionPlan(tier=ExecutionTier.MANUAL_REVIEW, reasons=["high risk"]))

    outcome = await flow.run(ctx)

    assert outcome is False
    assert isinstance(ctx.analysis, AnalysisResult)
    assert ctx.analysis.manual_review_required is True
    assert ctx.result.error == "manual review required by execution plan"
    assert ctx.state.workflow_status == "waiting_manual_review"


@pytest.mark.asyncio
async def test_reuse_flow_marks_verified_adapter_success(monkeypatch):
    store = _Store()
    flow = ReuseFlow(store=store, workflow_store=None, adapter_registry=SimpleNamespace())
    adapter = SimpleNamespace(registry_key="demo", output_mode="standalone")
    ctx = _ctx(ExecutionPlan(tier=ExecutionTier.ADAPTER_REUSE), adapter_candidate=adapter)

    async def fake_reuse_adapter(**_kwargs):
        return (
            GeneratedCode(session_id="reuse01", output_mode="standalone", crawler_script_path=Path("crawler.py")),
            True,
        )

    monkeypatch.setattr(flow, "_reuse_adapter", fake_reuse_adapter)

    outcome = await flow.run(ctx)

    assert outcome is True
    assert ctx.verified is True
    assert ctx.result.adapter_reused is True
    assert ctx.cost.route_label == "adapter_reuse"
    assert "adapter" in ctx.cost.reuse_hits
