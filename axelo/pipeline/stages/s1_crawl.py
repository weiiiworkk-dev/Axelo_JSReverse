from __future__ import annotations
import json
from pathlib import Path
from axelo.models.pipeline import PipelineState, StageResult, Decision, DecisionType
from axelo.models.target import TargetSite, RequestCapture
from axelo.modes.base import ModeController
from axelo.browser.driver import BrowserDriver
from axelo.browser.interceptor import NetworkInterceptor
from axelo.pipeline.base import PipelineStage
from axelo.config import settings
import structlog

log = structlog.get_logger()


class CrawlStage(PipelineStage):
    name = "s1_crawl"
    description = "启动浏览器，导航到目标URL，捕获所有网络流量和JS资源"

    async def run(self, state: PipelineState, mode: ModeController, target: TargetSite, **_) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        crawl_dir = session_dir / "crawl"
        crawl_dir.mkdir(parents=True, exist_ok=True)

        driver = BrowserDriver(settings.browser, settings.headless)
        interceptor = NetworkInterceptor()

        async with driver:
            page = await driver.launch(target.browser_profile)
            interceptor.attach(page)

            log.info("navigating", url=target.url)
            try:
                await page.goto(target.url, wait_until="networkidle", timeout=30_000)
            except Exception as e:
                # 超时不中断，已捕获的请求仍然有用
                log.warning("navigation_timeout", error=str(e))

            # 等待额外请求
            await page.wait_for_timeout(2000)
            # 异步安全：drain Queue，读取所有 response body
            await interceptor.drain()

        # 保存捕获数据
        all_captures = interceptor.captures
        api_calls = interceptor.get_api_calls()
        target.captured_requests = all_captures
        target.js_urls = interceptor.js_urls

        captures_path = crawl_dir / "captures.json"
        captures_path.write_text(
            json.dumps([c.model_dump(mode="json") for c in all_captures], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        log.info("crawl_done", total=len(all_captures), api_calls=len(api_calls), js_urls=len(interceptor.js_urls))

        # 构建决策：让人工确认哪些 API 请求是逆向目标
        options = [f"[{i+1}] {c.method} {c.url[:80]}" for i, c in enumerate(api_calls[:15])]
        options.append("全选")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.CONFIRM_TARGET,
            prompt=f"捕获到 {len(api_calls)} 个 API 请求，请确认需要逆向的目标请求：",
            options=options,
            context_summary=f"共捕获 {len(all_captures)} 条请求，{len(interceptor.js_urls)} 个JS资源",
            artifact_path=captures_path,
            default="全选",
        )

        outcome = await mode.gate(decision, state)

        # 根据决策设置 target_requests
        if outcome == "全选" or outcome == "skip":
            target.target_requests = api_calls[:5]
        else:
            # 解析选项编号
            try:
                idx = options.index(outcome)
                if idx < len(api_calls):
                    target.target_requests = [api_calls[idx]]
                else:
                    target.target_requests = api_calls[:5]
            except ValueError:
                target.target_requests = api_calls[:5]

        # 保存 target 元数据
        target_path = crawl_dir / "target.json"
        target_path.write_text(target.model_dump_json(indent=2), encoding="utf-8")

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"captures": captures_path, "target": target_path},
            decisions=[decision],
            summary=f"捕获 {len(all_captures)} 请求，确认 {len(target.target_requests)} 个目标，{len(target.js_urls)} 个JS文件",
            next_input={"target": target},
        )
