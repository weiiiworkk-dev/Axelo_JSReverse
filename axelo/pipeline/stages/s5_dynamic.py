from __future__ import annotations

import json
from pathlib import Path

import structlog

from axelo.analysis.dynamic.crypto_detector import detect_algorithm
from axelo.analysis.dynamic.hook_analyzer import HookAnalyzer
from axelo.analysis.dynamic.trace_builder import TraceBuilder
from axelo.browser.driver import BrowserDriver
from axelo.browser.hooks import JSHookInjector
from axelo.browser.interceptor import NetworkInterceptor
from axelo.config import settings
from axelo.models.execution import VerificationMode
from axelo.models.analysis import DynamicAnalysis, StaticAnalysis
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage

log = structlog.get_logger()


class DynamicAnalysisStage(PipelineStage):
    name = "s5_dynamic"
    description = "Run browser hooks and capture dynamic crypto behavior."

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        target: TargetSite,
        static_results: dict[str, StaticAnalysis],
        **_,
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        traces_dir = session_dir / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)

        verification_mode = target.execution_plan.verification_mode if target.execution_plan else VerificationMode.STANDARD
        max_attempts = 1 if verification_mode != VerificationMode.STRICT else max(1, settings.max_dynamic_retries + 1)
        decisions: list[Decision] = []
        latest_trace_path: Path | None = None

        for attempt in range(1, max_attempts + 1):
            dynamic, hook_analysis, algo_info, intercepts, trace_path = await self._collect_attempt(
                traces_dir=traces_dir,
                attempt=attempt,
                target=target,
                static_results=static_results,
            )
            latest_trace_path = trace_path

            summary = hook_analysis.get("summary", "No hook activity")
            if algo_info:
                algo_str = ", ".join(f"{item['algorithm']}({item['api']})" for item in algo_info[:3])
                summary += f"\nDetected crypto algorithms: {algo_str}"
            summary += f"\nAttempt {attempt}/{max_attempts}"

            options = ["accept", "retry", "skip"]
            decision = Decision(
                stage=self.name,
                decision_type=DecisionType.APPROVE_STAGE,
                prompt="Dynamic hook analysis completed. Confirm how to proceed:",
                options=options,
                artifact_path=trace_path,
                context_summary=summary,
                default="accept",
            )
            decisions.append(decision)

            outcome = await mode.gate(decision, state)
            if outcome == "skip":
                return StageResult(
                    stage_name=self.name,
                    success=True,
                    artifacts={"hook_trace": trace_path},
                    decisions=decisions,
                    summary=f"Dynamic analysis skipped after {attempt} attempt(s)",
                    next_input={"dynamic": None, "static_results": static_results, "target": target},
                )

            if outcome != "retry":
                return StageResult(
                    stage_name=self.name,
                    success=True,
                    artifacts={"hook_trace": trace_path},
                    decisions=decisions,
                    summary=(
                        f"Hook intercepts={len(intercepts)}, crypto_primitives={len(dynamic.crypto_primitives)}, "
                        f"attempts={attempt}"
                    ),
                    next_input={"dynamic": dynamic, "static_results": static_results, "target": target},
                )

            if attempt == max_attempts:
                return StageResult(
                    stage_name=self.name,
                    success=False,
                    artifacts={"hook_trace": trace_path},
                    decisions=decisions,
                    error=f"dynamic retry exhausted after {max_attempts} attempts",
                    summary=f"Dynamic retry exhausted after {max_attempts} attempts",
                )

            log.info("dynamic_retry_requested", attempt=attempt)

        return StageResult(
            stage_name=self.name,
            success=False,
            artifacts={"hook_trace": latest_trace_path} if latest_trace_path else {},
            decisions=decisions,
            error="dynamic analysis ended unexpectedly",
        )

    async def _collect_attempt(
        self,
        *,
        traces_dir: Path,
        attempt: int,
        target: TargetSite,
        static_results: dict[str, StaticAnalysis],
    ) -> tuple[DynamicAnalysis, dict, list[dict], list, Path]:
        driver = BrowserDriver(settings.browser, settings.headless)
        interceptor = NetworkInterceptor()
        hook_injector = JSHookInjector()

        async with driver:
            page = await driver.launch(target.browser_profile)
            interceptor.attach(page)
            await hook_injector.inject(page)

            log.info("dynamic_navigate", url=target.url, attempt=attempt)
            try:
                await page.goto(target.url, wait_until="networkidle", timeout=30_000)
            except Exception as exc:
                log.warning("dynamic_nav_timeout", error=str(exc), attempt=attempt)

            await page.wait_for_timeout(3000)
            await interceptor.drain()

        intercepts = hook_injector.get_intercepts()
        hook_analyzer = HookAnalyzer()
        first_static = next(iter(static_results.values()), None)
        hook_analysis = hook_analyzer.analyze(intercepts, first_static)

        trace_builder = TraceBuilder()
        bundle_id = next(iter(static_results), "unknown")
        dynamic = trace_builder.build(bundle_id, intercepts, target.target_requests, hook_analysis)
        algo_info = detect_algorithm(intercepts)

        trace_path = traces_dir / f"hook_trace_attempt_{attempt}.json"
        trace_path.write_text(
            json.dumps(
                {
                    "attempt": attempt,
                    "intercepts": [intercept.model_dump(mode="json") for intercept in intercepts],
                    "hook_analysis": hook_analysis,
                    "algo_info": algo_info,
                    "dynamic": dynamic.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return dynamic, hook_analysis, algo_info, intercepts, trace_path
