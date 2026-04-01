from __future__ import annotations

import json

import structlog

from axelo.browser import ActionRunner, BrowserDriver, BrowserStateStore, NetworkInterceptor, SessionPool
from axelo.config import settings
from axelo.models.pipeline import Decision, DecisionType, PipelineState, StageResult
from axelo.models.target import TargetSite
from axelo.modes.base import ModeController
from axelo.pipeline.base import PipelineStage
from axelo.policies import resolve_runtime_policy
from axelo.storage import SessionStateStore

log = structlog.get_logger()


class CrawlStage(PipelineStage):
    name = "s1_crawl"
    description = "Launch browser, replay the action flow, and capture network and JS resources."

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
        session_store = SessionStateStore(settings.sessions_dir)
        browser_state_store = BrowserStateStore(session_store)
        session_pool = SessionPool(settings.sessions_dir)
        active_session = session_pool.acquire(target.url, target.session_state)
        if not active_session.session_key:
            active_session.session_key = target.session_id
        target.session_state = active_session

        trace_path = crawl_dir / "playwright_trace.zip"
        driver = BrowserDriver(settings.browser, settings.headless)
        interceptor = NetworkInterceptor()
        action_runner = ActionRunner()
        action_result_summary = ""

        async with driver:
            page = await driver.launch(
                policy.apply_to_profile(target.browser_profile),
                session_state=target.session_state,
                trace_path=trace_path if policy.enable_trace_capture else None,
            )
            interceptor.attach(page)

            try:
                action_result = await action_runner.run(page, target, policy)
                action_result_summary = f"actions={action_result.executed}, failures={len(action_result.failures)}"
            except Exception as exc:
                action_result_summary = f"action_flow_failed={exc}"
                log.warning("action_flow_failed", error=str(exc))

            await interceptor.drain()
            target.session_state = await browser_state_store.persist_context(
                state.session_id,
                target.session_state.domain or page.url,
                driver.context,
                target.session_state,
            )

        all_captures = interceptor.captures
        api_calls = interceptor.get_api_calls()
        target.captured_requests = all_captures
        target.js_urls = interceptor.js_urls
        target.trace.trace_zip_path = str(trace_path) if trace_path.exists() else ""

        if target.known_endpoint:
            matches = [capture for capture in api_calls if target.known_endpoint in capture.url]
            if matches:
                api_calls = matches + [capture for capture in api_calls if capture not in matches]
                log.info("endpoint_matches_prioritized", endpoint=target.known_endpoint, matched=len(matches))

        captures_path = crawl_dir / "captures.json"
        captures_path.write_text(
            json.dumps([capture.model_dump(mode="json") for capture in all_captures], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        target.trace.network_log_path = str(captures_path)

        dominant_status = max((capture.response_status for capture in all_captures if capture.response_status), default=200)
        target.session_state = session_pool.release(
            target.url,
            target.session_state,
            success=bool(api_calls),
            status_code=dominant_status,
            error="" if api_calls else "no_api_calls_captured",
        )
        session_store.save(state.session_id, target.session_state)

        options = [f"[{i + 1}] {capture.method} {capture.url[:80]}" for i, capture in enumerate(api_calls[:15])]
        options.append("all")

        decision = Decision(
            stage=self.name,
            decision_type=DecisionType.CONFIRM_TARGET,
            prompt=f"Captured {len(api_calls)} API requests. Confirm the reverse-engineering target:",
            options=options,
            context_summary=(
                f"Captured {len(all_captures)} requests, {len(target.js_urls)} JS resources, "
                f"{action_result_summary}, session_health={target.session_state.health_score:.2f}"
            ),
            artifact_path=captures_path,
            default="all",
        )
        outcome = await mode.gate(decision, state)

        if outcome in {"all", "skip"}:
            target.target_requests = api_calls[:5]
        else:
            try:
                index = options.index(outcome)
                target.target_requests = [api_calls[index]] if index < len(api_calls) else api_calls[:5]
            except ValueError:
                target.target_requests = api_calls[:5]

        target_path = crawl_dir / "target.json"
        target_path.write_text(target.model_dump_json(indent=2), encoding="utf-8")

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"captures": captures_path, "target": target_path, "trace": trace_path},
            decisions=[decision],
            summary=(
                f"Captured {len(all_captures)} requests, confirmed {len(target.target_requests)} targets, "
                f"persisted session state to {target.session_state.storage_state_path or 'memory'}"
            ),
            next_input={"target": target},
        )
