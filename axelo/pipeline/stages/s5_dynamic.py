from __future__ import annotations

from pathlib import Path

from axelo.config import settings
from axelo.models.analysis import DynamicAnalysis
from axelo.models.pipeline import Decision, DecisionType, StageResult


class BrowserDriver:
    pass


class NetworkInterceptor:
    pass


class JSHookInjector:
    pass


class DynamicAnalysisStage:
    async def _collect_attempt(self, *, traces_dir: Path, attempt: int, target, static_results):
        trace_path = traces_dir / f"hook_trace_attempt_{attempt}.json"
        trace_path.write_text("{}", encoding="utf-8")
        return DynamicAnalysis(bundle_id="dynamic"), {"summary": "ok"}, [], [], trace_path

    async def execute(self, state, mode, *, target, static_results):
        traces_dir = settings.workspace / "sessions" / state.session_id / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)
        max_retries = int(getattr(settings, "max_dynamic_retries", 1))
        for attempt in range(1, max_retries + 2):
            dynamic, summary, _intercepts, _events, _trace_path = await self._collect_attempt(
                traces_dir=traces_dir,
                attempt=attempt,
                target=target,
                static_results=static_results,
            )
            decision = Decision(
                stage="s5_dynamic",
                decision_type=DecisionType.SELECT_OPTION,
                prompt="retry dynamic?",
                options=["retry", "accept"],
                default="accept",
            )
            if attempt <= max_retries and await mode.gate(decision, state) == "retry":
                continue
            return StageResult(stage_name="s5_dynamic", success=True, summary=summary.get("summary", "ok"), next_input={"dynamic": dynamic})
        return StageResult(stage_name="s5_dynamic", success=False, error="retry exhausted", summary="retry exhausted")
