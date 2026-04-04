from __future__ import annotations

import json
from urllib.parse import unquote

import structlog

from axelo.analysis.request_contracts import build_dataset_contract, build_request_contract, derive_capability_profile
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
        action_runner = ActionRunner()

        trace_path = crawl_dir / "playwright_trace.zip"
        all_captures = []
        api_calls = []
        js_urls: list[str] = []
        decisions: list[Decision] = []
        action_result_summary = ""
        used_session_keys: set[str] = set()
        max_attempts = max(1, target.execution_plan.max_crawl_retries if target.execution_plan else policy.max_runtime_retries)

        for attempt in range(1, max_attempts + 1):
            active_session = session_pool.acquire(target.url, target.session_state, exclude_keys=used_session_keys)
            if not active_session.session_key:
                active_session.session_key = target.session_id
            used_session_keys.add(active_session.session_key)
            target.session_state = active_session

            driver = BrowserDriver(settings.browser, settings.headless)
            interceptor = NetworkInterceptor()

            try:
                async with driver:
                    page = await driver.launch(
                        policy.apply_to_profile(target.browser_profile),
                        session_state=target.session_state,
                        trace_path=trace_path if policy.enable_trace_capture and attempt == 1 else None,
                    )
                    interceptor.attach(page)

                    try:
                        action_result = await action_runner.run(page, target, policy)
                        action_result_summary = (
                            f"attempt={attempt} actions={action_result.executed}, failures={len(action_result.failures)}"
                        )
                    except Exception as exc:
                        action_result_summary = f"attempt={attempt} action_flow_failed={exc}"
                        log.warning("action_flow_failed", error=str(exc), attempt=attempt)

                    await interceptor.drain()
                    target.session_state = await browser_state_store.persist_context(
                        state.session_id,
                        target.session_state.domain or page.url,
                        driver.context,
                        target.session_state,
                    )
            except Exception as exc:
                target.session_state = session_pool.release(
                    target.url,
                    target.session_state,
                    success=False,
                    error=str(exc),
                )
                session_store.save(state.session_id, target.session_state)
                if attempt == max_attempts:
                    return StageResult(
                        stage_name=self.name,
                        success=False,
                        error=str(exc),
                        summary=f"crawl failed after {attempt} attempts",
                    )
                continue

            all_captures = interceptor.captures
            api_calls = interceptor.get_api_calls()
            js_urls = interceptor.js_urls
            session_status = _select_session_status(api_calls, all_captures)
            session_success = _session_attempt_succeeded(api_calls, session_status)
            target.session_state = session_pool.release(
                target.url,
                target.session_state,
                success=session_success,
                status_code=session_status,
                error="" if api_calls else "no_api_calls_captured",
            )
            session_store.save(state.session_id, target.session_state)
            if api_calls:
                break

        target.captured_requests = all_captures
        target.js_urls = js_urls
        target.trace.trace_zip_path = str(trace_path) if trace_path.exists() else ""

        if target.known_endpoint:
            matches = [capture for capture in api_calls if target.known_endpoint in capture.url]
            if matches:
                api_calls = matches + [capture for capture in api_calls if capture not in matches]
                log.info("endpoint_matches_prioritized", endpoint=target.known_endpoint, matched=len(matches))
        api_calls = _prioritize_api_calls(api_calls, target)

        captures_path = crawl_dir / "captures.json"
        captures_path.write_text(
            json.dumps([capture.model_dump(mode="json") for capture in all_captures], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        target.trace.network_log_path = str(captures_path)

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
        decisions.append(decision)

        outcome = "all"
        if target.execution_plan is None or target.execution_plan.enable_target_confirmation:
            outcome = await mode.gate(decision, state)

        if outcome in {"all", "skip"}:
            target.target_requests = api_calls[:5]
        else:
            try:
                index = options.index(outcome)
                target.target_requests = [api_calls[index]] if index < len(api_calls) else api_calls[:5]
            except ValueError:
                target.target_requests = api_calls[:5]

        target.request_contracts = [build_request_contract(capture, target) for capture in target.target_requests]
        target.selected_contract = target.request_contracts[0] if target.request_contracts else None
        target.dataset_contract = build_dataset_contract(target, target.selected_contract)
        target.capability_profile = derive_capability_profile(target, contract=target.selected_contract)

        target_path = crawl_dir / "target.json"
        target_path.write_text(target.model_dump_json(indent=2), encoding="utf-8")

        return StageResult(
            stage_name=self.name,
            success=True,
            artifacts={"captures": captures_path, "target": target_path, "trace": trace_path},
            decisions=decisions,
            summary=(
                f"Captured {len(all_captures)} requests, confirmed {len(target.target_requests)} targets, "
                f"persisted session state to {target.session_state.storage_state_path or 'memory'}"
            ),
            next_input={"target": target},
        )


def _select_session_status(api_calls, all_captures) -> int | None:
    preferred = [capture.response_status for capture in api_calls if capture.response_status]
    fallback = [capture.response_status for capture in all_captures if capture.response_status]
    statuses = preferred or fallback
    if not statuses:
        return None

    for blocked_status in (429, 403, 401):
        if blocked_status in statuses:
            return blocked_status

    counts: dict[int, int] = {}
    for status in statuses:
        counts[status] = counts.get(status, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _session_attempt_succeeded(api_calls, session_status: int | None) -> bool:
    if not api_calls:
        return False
    if session_status is None:
        return True
    return 200 <= session_status < 400


def _prioritize_api_calls(api_calls, target: TargetSite):
    if not api_calls:
        return api_calls

    scored = sorted(
        api_calls,
        key=lambda capture: _capture_priority_score(capture, target),
        reverse=True,
    )
    return scored


def _capture_priority_score(capture, target: TargetSite) -> int:
    score = 0
    haystack = _capture_haystack(capture)
    url_lower = (capture.url or "").lower()
    response_headers = {str(key).lower(): str(value).lower() for key, value in (capture.response_headers or {}).items()}
    request_headers = {str(key).lower(): str(value).lower() for key, value in (capture.request_headers or {}).items()}

    if target.known_endpoint and target.known_endpoint.lower() in haystack:
        score += 100
    if target.target_hint:
        for token in _hint_tokens(target.target_hint):
            if token and token in haystack:
                score += 30
    if "/api/" in url_lower:
        score += 25
    if "application/json" in response_headers.get("content-type", ""):
        score += 20
    if request_headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        score += 10
    if capture.method.upper() == "GET":
        score += 3
    if any(keyword in url_lower for keyword in ("search_items", "item/get", "product", "detail")):
        score += 50
    elif any(keyword in url_lower for keyword in ("search_user", "curated_search", "facet", "search_page_common")):
        score += 25
    if any(keyword in url_lower for keyword in ("canonical_search/get_url", "/activity;", "doubleclick", "tracking", "analytics")):
        score -= 60
    if any(keyword in haystack for keyword in ("item", "product", "detail", "search", "catalog", "sku")):
        score += 5
    return score


def _capture_haystack(capture) -> str:
    parts = [capture.url.lower()]
    for payload in (capture.request_body, capture.response_body):
        if not payload:
            continue
        preview = payload[:1024]
        try:
            parts.append(preview.decode("utf-8", errors="ignore").lower())
        except Exception:
            continue
    return unquote(" ".join(parts))


def _hint_tokens(target_hint: str) -> list[str]:
    normalized = unquote(target_hint.strip().lower())
    tokens = [token for token in normalized.replace("/", " ").replace("-", " ").split() if len(token) >= 3]
    if normalized and normalized not in tokens:
        tokens.insert(0, normalized)
    return tokens[:6]
