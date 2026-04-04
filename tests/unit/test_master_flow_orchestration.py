from __future__ import annotations

from types import SimpleNamespace

import pytest

from axelo.orchestrator.master import MasterOrchestrator, MasterResult


@pytest.mark.asyncio
async def test_master_orchestrator_runs_thin_flow_sequence(monkeypatch):
    calls: list[str] = []

    class FakeRunner:
        instances: list["FakeRunner"] = []

        def __init__(self, *_args, **_kwargs) -> None:
            self.started = False
            self.stopped = False
            self.__class__.instances.append(self)

        async def start(self) -> None:
            self.started = True

        async def stop(self) -> None:
            self.stopped = True

    class FakeAnalyzer:
        def __init__(self, runner) -> None:
            self.runner = runner

    class FakeReuseFlow:
        async def run(self, ctx):
            calls.append("reuse")
            return None

    class FakeDiscoveryFlow:
        async def run(self, ctx, *, runner, ast_analyzer):
            assert isinstance(runner, FakeRunner)
            assert isinstance(ast_analyzer, FakeAnalyzer)
            calls.append("discovery")
            return object()

    class FakeAnalysisFlow:
        async def run(self, ctx):
            calls.append("analysis")
            return object()

    class FakeDeliveryFlow:
        async def run(self, ctx):
            calls.append("delivery")
            return object()

    result = MasterResult(session_id="thin01", url="https://example.com")
    ctx = SimpleNamespace(
        sid="thin01",
        cost=SimpleNamespace(
            add_node_call=lambda stage: calls.append(f"node:{stage}"),
            route_label="",
            reuse_hits=[],
        ),
        target=SimpleNamespace(trace={}),
        workflow=SimpleNamespace(checkpoint=lambda *args, **kwargs: {"stage": args[2], "status": args[3]}),
        state=SimpleNamespace(workflow_status="", error=None),
        result=result,
    )

    async def fake_initialize(self, **_kwargs):
        return ctx

    finalized: list[bool] = []

    async def fake_finalize(self, local_ctx, completed: bool):
        finalized.append(completed)
        return local_ctx.result

    monkeypatch.setattr("axelo.orchestrator.master.NodeRunner", FakeRunner)
    monkeypatch.setattr("axelo.orchestrator.master.ASTAnalyzer", FakeAnalyzer)
    monkeypatch.setattr(MasterOrchestrator, "_initialize_run_context", fake_initialize)
    monkeypatch.setattr(MasterOrchestrator, "_finalize_run", fake_finalize)

    orchestrator = MasterOrchestrator()
    orchestrator._store = SimpleNamespace(save=lambda _state: None)
    orchestrator._reuse_flow = FakeReuseFlow()
    orchestrator._discovery_flow = FakeDiscoveryFlow()
    orchestrator._analysis_flow = FakeAnalysisFlow()
    orchestrator._delivery_flow = FakeDeliveryFlow()

    await orchestrator.run(url="https://example.com", goal="demo")

    assert calls == ["reuse", "node:node_runtime", "discovery", "analysis", "delivery"]
    assert finalized == [True]
    assert FakeRunner.instances[0].started is True
    assert FakeRunner.instances[0].stopped is True
