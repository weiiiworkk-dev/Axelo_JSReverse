from __future__ import annotations

from pathlib import Path

import pytest

from axelo.config import settings
from axelo.models.analysis import DynamicAnalysis, StaticAnalysis
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

    result = await stage.execute(
        PipelineState(session_id="dyn01"),
        _RetryMode(),
        target=TargetSite(url="https://example.com", session_id="dyn01", interaction_goal="demo"),
        static_results={"bundle": StaticAnalysis(bundle_id="bundle")},
    )

    assert result.success is False
    assert "retry exhausted" in (result.error or "")
    assert attempts == [1, 2]
    assert (tmp_path / "sessions" / "dyn01" / "traces" / "hook_trace_attempt_1.json").exists()
