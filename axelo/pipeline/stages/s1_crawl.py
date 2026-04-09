from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

from axelo.models.pipeline import StageResult


class ActionRunner:
    async def run(self, page, target, policy):
        return None


class BrowserDriver:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def launch(self, profile, session_state=None, trace_path=None):
        return type("Page", (), {"url": getattr(profile, "url", "")})()


class NetworkInterceptor:
    def __init__(self) -> None:
        self.captures = []
        self.js_urls = []

    def attach(self, page) -> None:
        return None

    async def drain(self):
        return None

    def get_api_calls(self):
        return self.captures


class BrowserStateStore:
    async def persist_context(self, session_id, domain, context, session_state):
        return session_state


class SessionPool:
    def acquire(self, url, session_state, exclude_keys=None):
        return session_state

    def release(self, url, session_state, **kwargs):
        return session_state


class SessionStateStore:
    def save(self, session_id, session_state) -> None:
        return None


class RealBrowserResolver:
    async def resolve(self, **kwargs):
        return None


def _prioritize_api_calls(calls, _target):
    def score(c):
        url = (c.url or "").lower()
        return (2 if "search_items" in url else 0, 1 if "/api/" in url else 0)
    return sorted(calls, key=score, reverse=True)


def _filter_api_calls(calls, target):
    if getattr(target.intent, "resource_kind", "") == "search_results":
        return [c for c in calls if "suppression" not in ((c.response_body or b"").decode("utf-8", errors="ignore").lower())]
    return calls


def _select_session_status(api_calls, all_captures) -> int:
    statuses = [c.response_status for c in api_calls if c.response_status]
    if statuses:
        blocked = [s for s in statuses if s in {401, 403, 429}]
        if blocked:
            return blocked[0]
        return Counter(statuses).most_common(1)[0][0]
    all_statuses = [c.response_status for c in all_captures if c.response_status]
    return all_statuses[0] if all_statuses else 0


def _session_attempt_succeeded(api_calls, status: int) -> bool:
    return bool(api_calls) and status < 400


@dataclass
class RiskSignal:
    status: int
    url: str


class _RiskSignalObserver:
    def __init__(self, _risk_service, target_url: str) -> None:
        self._target_url = target_url
        self._event = asyncio.Event()
        self._signal: RiskSignal | None = None

    async def _inspect_response(self, response) -> None:
        req = getattr(response, "request", None)
        resource_type = getattr(req, "resource_type", "")
        url = str(getattr(response, "url", ""))
        status = int(getattr(response, "status", 0) or 0)
        set_cookie = (getattr(response, "headers", {}) or {}).get("set-cookie", "").lower()
        if resource_type in {"stylesheet", "image", "font"}:
            return
        if "_abck" in set_cookie or "bm_sz" in set_cookie:
            host = (urlparse(url).hostname or "").lower()
            target_host = (urlparse(self._target_url).hostname or "").lower()
            if host and target_host and host != target_host:
                return
        if status in {401, 403, 429} or "cdn-cgi/challenge-platform" in url:
            self._signal = RiskSignal(status=status, url=url)
            self._event.set()


class CrawlStage:
    async def execute(self, state, _mode, *, target):
        observer = _RiskSignalObserver(None, target.url)
        interceptor = NetworkInterceptor()
        runner = ActionRunner()
        try:
            async with BrowserDriver() as driver:
                page = await driver.launch(profile=target)
                if hasattr(page, "on"):
                    page.on("response", lambda resp: asyncio.create_task(observer._inspect_response(resp)))
                interceptor.attach(page)
                await runner.run(page, target, None)
                await interceptor.drain()
        except Exception as exc:
            api_calls = _filter_api_calls(_prioritize_api_calls(interceptor.get_api_calls(), target), target)
            return StageResult(
                stage_name="s1_crawl",
                success=False,
                summary="No high-confidence target requests matched the requested intent",
                error=f"action_flow_failed: {exc}; captured_api_calls={len(api_calls)}",
            )

        if observer._event.is_set() and observer._signal is not None:
            return StageResult(
                stage_name="s1_crawl",
                success=False,
                summary="Risk-control challenge detected during crawl",
                error=f"status={observer._signal.status}; url={observer._signal.url}",
            )

        return StageResult(stage_name="s1_crawl", success=True, next_input={"target": target})
