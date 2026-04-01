from __future__ import annotations

import json

import structlog

from axelo.browser.driver import BrowserDriver
from axelo.browser.interceptor import NetworkInterceptor
from axelo.config import settings
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage
from axelo.policies import resolve_runtime_policy

log = structlog.get_logger()


class CrawlStage(PipelineStage):
    name = "s1_crawl"
    description = "启动浏览器，导航到目标 URL，捕获网络请求与 JS 资源。"

    async def run(
        self,
        state: PipelineState,
        mode: ModeController,
        target: TargetSite,
        **_,
    ) -> StageResult:
        session_dir = settings.session_dir(state.session_id)
        crawl_dir = session_dir / "crawl"
        crawl_dir.mkdir(parents=True, exist_ok=True)

        policy = resolve_runtime_policy(target)
        driver = BrowserDriver(settings.browser, settings.headless)
        interceptor = NetworkInterceptor()

        async with driver:
            page = await driver.launch(policy.apply_to_profile(target.browser_profile))
            interceptor.attach(page)

            log.info(
                "navigating",
                url=target.url,
                wait_until=policy.goto_wait_until,
                post_wait_ms=policy.post_navigation_wait_ms,
            )
            try:
                await page.goto(target.url, wait_until=policy.goto_wait_until, timeout=30_000)
            except Exception as exc:
                # Navigation timeout does not invalidate already captured requests.
                log.warning("navigation_timeout", error=str(exc))

            await page.wait_for_timeout(policy.post_navigation_wait_ms)
            await interceptor.drain()

        all_captures = interceptor.captures
        api_calls = interceptor.get_api_calls()
        target.captured_requests = all_captures
        target.js_urls = interceptor.js_urls

        if target.known_endpoint:
            matches = [cap for cap in api_calls if target.known_endpoint in cap.url]
            if matches:
                api_calls = matches + [cap for cap in api_calls if cap not in matches]
                log.info(
                    "endpoint_matches_prioritized",
                    endpoint=target.known_endpoint,
                    matched=len(matches),
                )

        captures_path = crawl_dir / "captures.json"
        captures_path.write_text(
            json.dumps([c.model_dump(mode="json") for c in all_captures], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        log.info(
            "crawl_done",
            total=len(all_captures),
            api_calls=len(api_calls),
            js_urls=len(interceptor.js_urls),
        )

        options = [f"[{i + 1}] {c.method} {c.url[:80]}" for i, c in enumerate(api_calls[:15])]
        options.append("全选")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.CONFIRM_TARGET,
            prompt=f"捕获到 {len(api_calls)} 个 API 请求，请确认需要逆向的目标请求：",
            options=options,
            context_summary=f"共捕获 {len(all_captures)} 条请求，{len(interceptor.js_urls)} 个 JS 资源",
            artifact_path=captures_path,
            default="全选",
        )
        outcome = await mode.gate(decision, state)

        if outcome in {"全选", "skip"}:
            target.target_requests = api_calls[:5]
        else:
            try:
                idx = options.index(outcome)
                target.target_requests = [api_calls[idx]] if idx < len(api_calls) else api_calls[:5]
            except ValueError:
                target.target_requests = api_calls[:5]

        target_path = crawl_dir / "target.json"
        target_path.write_text(target.model_dump_json(indent=2), encoding="utf-8")

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"captures": captures_path, "target": target_path},
            decisions=[decision],
            summary=f"捕获 {len(all_captures)} 请求，确认 {len(target.target_requests)} 个目标，{len(target.js_urls)} 个 JS 文件",
            next_input={"target": target},
        )

