from __future__ import annotations
import json
from axelo.models.pipeline import PipelineState, StageResult, Decision, DecisionType
from axelo.models.target import TargetSite
from axelo.models.analysis import StaticAnalysis, DynamicAnalysis
from axelo.modes.base import ModeController
from axelo.browser.driver import BrowserDriver
from axelo.browser.interceptor import NetworkInterceptor
from axelo.browser.hooks import JSHookInjector
from axelo.analysis.dynamic.hook_analyzer import HookAnalyzer
from axelo.analysis.dynamic.trace_builder import TraceBuilder
from axelo.analysis.dynamic.crypto_detector import detect_algorithm
from axelo.pipeline.base import PipelineStage
from axelo.config import settings
import structlog

log = structlog.get_logger()


class DynamicAnalysisStage(PipelineStage):
    name = "s5_dynamic"
    description = "动态执行分析：注入Hook，重跑目标请求，记录加密API调用轨迹"

    async def run(
        self, state: PipelineState, mode: ModeController,
        target: TargetSite,
        static_results: dict[str, StaticAnalysis],
        **_,
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        traces_dir = session_dir / "traces"
        traces_dir.mkdir(parents=True, exist_ok=True)

        driver = BrowserDriver(settings.browser, settings.headless)
        interceptor = NetworkInterceptor()
        hook_injector = JSHookInjector()

        async with driver:
            page = await driver.launch(target.browser_profile)
            interceptor.attach(page)
            await hook_injector.inject(page)

            log.info("dynamic_navigate", url=target.url)
            try:
                await page.goto(target.url, wait_until="networkidle", timeout=30_000)
            except Exception as e:
                log.warning("dynamic_nav_timeout", error=str(e))

            await page.wait_for_timeout(3000)
            # 异步安全：drain response queue
            await interceptor.drain()

        intercepts = hook_injector.get_intercepts()
        api_calls = interceptor.get_api_calls()

        # Hook 分析
        hook_analyzer = HookAnalyzer()
        # 取第一个 bundle 的静态结果做关联
        first_static = next(iter(static_results.values()), None)
        hook_analysis = hook_analyzer.analyze(intercepts, first_static)

        # 轨迹构建
        trace_builder = TraceBuilder()
        bundle_id = next(iter(static_results), "unknown")
        dynamic = trace_builder.build(bundle_id, intercepts, target.target_requests, hook_analysis)

        # 加密算法检测
        algo_info = detect_algorithm(intercepts)

        # 保存轨迹
        trace_path = traces_dir / "hook_trace.json"
        trace_path.write_text(
            json.dumps({
                "intercepts": [ic.model_dump(mode="json") for ic in intercepts],
                "hook_analysis": hook_analysis,
                "algo_info": algo_info,
                "dynamic": dynamic.model_dump(mode="json"),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 构建决策摘要
        summary = hook_analysis.get("summary", "无Hook触发")
        if algo_info:
            algo_str = ", ".join(f"{a['algorithm']}({a['api']})" for a in algo_info[:3])
            summary += f"\n检测到加密算法: {algo_str}"

        options = ["确认轨迹，继续AI分析", "重新执行Hook（再来一次）", "跳过动态分析"]

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.APPROVE_STAGE,
            prompt="动态Hook分析完成，请确认执行轨迹：",
            options=options,
            artifact_path=trace_path,
            context_summary=summary,
            default="确认轨迹，继续AI分析",
        )

        outcome = await mode.gate(decision, state)

        if outcome == options[1]:
            # 简单重试：重新运行此阶段逻辑（递归调用）
            log.info("dynamic_retry")
            return await self.run(state, mode, target=target, static_results=static_results)

        dynamic_used = None if outcome == options[2] else dynamic

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"hook_trace": trace_path},
            decisions=[decision],
            summary=f"Hook拦截 {len(intercepts)} 次，{len(dynamic.crypto_primitives)} 种加密原语",
            next_input={"dynamic": dynamic_used, "static_results": static_results, "target": target},
        )
