from __future__ import annotations

from pathlib import Path

import pytest

from axelo.config import settings
from axelo.models.analysis import DynamicAnalysis, StaticAnalysis
from axelo.models.execution import ExecutionPlan, VerificationMode
from axelo.models.pipeline import Decision, PipelineState
from axelo.models.target import TargetSite
from axelo.pipeline.stages.s5_dynamic import DynamicAnalysisStage


class _RetryMode:
    async def gate(self, decision: Decision, state: PipelineState) -> str:
        return "retry"


@pytest.mark.asyncio
async def test_dynamic_stage_retries_with_hard_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)
    monkeypatch.setattr(settings, "max_dynamic_retries", 1)

    attempts: list[int] = []

    async def fake_collect_attempt(*, traces_dir: Path, attempt: int, target, static_results):
        attempts.append(attempt)
        trace_path = traces_dir / f"hook_trace_attempt_{attempt}.json"
        trace_path.write_text("{}", encoding="utf-8")
        return DynamicAnalysis(bundle_id="bundle", crypto_primitives=["sha256"]), {"summary": "ok"}, [], [], trace_path

    stage = DynamicAnalysisStage()
    monkeypatch.setattr(stage, "_collect_attempt", fake_collect_attempt)
    target = TargetSite(url="https://example.com", session_id="dyn01", interaction_goal="demo")
    target.execution_plan = ExecutionPlan(verification_mode=VerificationMode.STRICT)

    result = await stage.execute(
        PipelineState(session_id="dyn01"),
        _RetryMode(),
        target=target,
        static_results={"bundle": StaticAnalysis(bundle_id="bundle")},
    )

    assert result.success is False
    assert "retry exhausted" in (result.error or "")
    assert attempts == [1, 2]
    assert (tmp_path / "sessions" / "dyn01" / "traces" / "hook_trace_attempt_1.json").exists()


@pytest.mark.asyncio
async def test_dynamic_stage_reuses_existing_session_state(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)

    launch_calls: list[str | None] = []

    class FakePage:
        async def goto(self, url, wait_until="networkidle", timeout=30_000):
            return None

        async def wait_for_timeout(self, timeout_ms):
            return None

    class FakeBrowserDriver:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def launch(self, profile, session_state=None, trace_path=None):
            launch_calls.append(getattr(session_state, "storage_state_path", None))
            return FakePage()

    class FakeNetworkInterceptor:
        def attach(self, page):
            return None

        async def drain(self):
            return None

        def get_api_calls(self):
            return []

    class FakeHookInjector:
        async def inject(self, page):
            return None

        def get_intercepts(self):
            return []

        def get_taint_events(self):
            return []

    monkeypatch.setattr("axelo.pipeline.stages.s5_dynamic.BrowserDriver", FakeBrowserDriver)
    monkeypatch.setattr("axelo.pipeline.stages.s5_dynamic.NetworkInterceptor", FakeNetworkInterceptor)
    monkeypatch.setattr("axelo.pipeline.stages.s5_dynamic.JSHookInjector", FakeHookInjector)

    target = TargetSite(url="https://example.com", session_id="dyn02", interaction_goal="demo")
    target.session_state.storage_state_path = str(tmp_path / "storage.json")

    stage = DynamicAnalysisStage()
    result = await stage.execute(
        PipelineState(session_id="dyn02"),
        _RetryMode(),
        target=target,
        static_results={"bundle": StaticAnalysis(bundle_id="bundle")},
    )

    assert result is not None
    assert launch_calls == [str(tmp_path / "storage.json")]
