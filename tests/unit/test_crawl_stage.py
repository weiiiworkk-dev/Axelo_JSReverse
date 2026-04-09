from __future__ import annotations

import asyncio

import pytest

from axelo.config import settings
from axelo.models.pipeline import Decision, PipelineState
from axelo.models.target import RequestCapture
from axelo.models.target import TargetSite
from axelo.pipeline.stages.s1_crawl import (
    CrawlStage,
    _RiskSignalObserver,
    _filter_api_calls,
    _prioritize_api_calls,
    _select_session_status,
    _session_attempt_succeeded,
)


def _capture(url: str, status: int) -> RequestCapture:
    return RequestCapture(url=url, method="GET", response_status=status)


class DummyMode:
    name = "auto"

    async def gate(self, decision: Decision, state: PipelineState) -> str:
        return decision.default or "all"

    def should_auto_proceed(self, stage_name: str, confidence: float) -> bool:
        return True


def test_select_session_status_prefers_blocked_api_responses():
    api_calls = [_capture("https://example.com/api", 403)]
    all_captures = [_capture("https://example.com/static.js", 500), *api_calls]

    status = _select_session_status(api_calls, all_captures)

    assert status == 403
    assert _session_attempt_succeeded(api_calls, status) is False


def test_select_session_status_prefers_most_common_api_status():
    api_calls = [
        _capture("https://example.com/api/1", 200),
        _capture("https://example.com/api/2", 200),
        _capture("https://example.com/api/3", 500),
    ]

    status = _select_session_status(api_calls, api_calls)

    assert status == 200
    assert _session_attempt_succeeded(api_calls, status) is True


def test_prioritize_api_calls_prefers_real_search_data_endpoint():
    target = TargetSite(
        url="https://shopee.com.my/search?keyword=iPhone%2015",
        session_id="crawl01",
        interaction_goal="collect search results",
        target_hint="iPhone 15",
    )
    target_requests = [
        RequestCapture(
            url="https://shopee.com.my/backend/growth/canonical_search/get_url/?keyword=iPhone%2015",
            method="GET",
            request_headers={"x-requested-with": "XMLHttpRequest"},
            response_headers={"content-type": "application/json"},
            response_status=200,
        ),
        RequestCapture(
            url="https://shopee.com.my/api/v4/search/search_items?keyword=iPhone%2015&limit=60",
            method="GET",
            request_headers={"x-requested-with": "XMLHttpRequest"},
            response_headers={"content-type": "application/json"},
            response_status=200,
        ),
    ]

    prioritized = _prioritize_api_calls(target_requests, target)

    assert prioritized[0].url.endswith("/api/v4/search/search_items?keyword=iPhone%2015&limit=60")


def test_filter_api_calls_drops_suppression_noise_for_search_intent():
    target = TargetSite(
        url="https://www.amazon.com/",
        session_id="crawl02",
        interaction_goal="collect search results",
        target_hint="iPhone 15",
    )
    target.intent.resource_kind = "search_results"
    target_requests = [
        RequestCapture(
            url="https://www.amazon.com/puff/content?data=%7B%22pageType%22%3A%22Gateway%22%7D",
            method="GET",
            request_headers={"x-requested-with": "XMLHttpRequest"},
            response_headers={"content-type": "application/json"},
            response_body=b'{"suppression":{"suppressionMessage":"Customer is unrecognized"},"responseType":"SUPPRESSION"}',
            response_status=200,
        ),
        RequestCapture(
            url="https://www.amazon.com/s?k=iPhone+15&page=1",
            method="GET",
            request_headers={"x-requested-with": "XMLHttpRequest"},
            response_headers={"content-type": "text/html"},
            response_status=200,
        ),
    ]

    prioritized = _prioritize_api_calls(target_requests, target)
    filtered = _filter_api_calls(prioritized, target)

    assert len(filtered) == 1
    assert filtered[0].url == "https://www.amazon.com/s?k=iPhone+15&page=1"


@pytest.mark.asyncio
async def test_crawl_stage_fails_fast_when_only_noise_candidates(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)
    noise_capture = RequestCapture(
        url="https://www.amazon.com/puff/content?data=%7B%22pageType%22%3A%22Gateway%22%7D",
        method="GET",
        request_headers={"x-requested-with": "XMLHttpRequest"},
        response_headers={"content-type": "application/json"},
        response_body=b'{"suppression":{"suppressionMessage":"Customer is unrecognized"},"responseType":"SUPPRESSION"}',
        response_status=200,
        initiator="xhr",
    )

    class FakeActionRunner:
        async def run(self, page, target, policy):
            raise TimeoutError("Page.goto timed out")

    class FakeBrowserDriver:
        def __init__(self, *args, **kwargs) -> None:
            self.context = object()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def launch(self, profile, session_state=None, trace_path=None):
            class FakePage:
                url = "https://www.amazon.com/"

            return FakePage()

    class FakeNetworkInterceptor:
        def __init__(self) -> None:
            self.captures = [noise_capture]
            self.js_urls = []

        def attach(self, page) -> None:
            return None

        async def drain(self) -> None:
            return None

        def get_api_calls(self):
            return [noise_capture]

    class FakeBrowserStateStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def persist_context(self, session_id, domain, context, session_state):
            session_state.storage_state_path = str(tmp_path / "storage.json")
            return session_state

    class FakeSessionPool:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def acquire(self, url, session_state, exclude_keys=None):
            return session_state

        def release(self, url, session_state, **kwargs):
            return session_state

    class FakeSessionStateStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def save(self, session_id, session_state) -> None:
            return None

    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.ActionRunner", FakeActionRunner)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.BrowserDriver", FakeBrowserDriver)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.NetworkInterceptor", FakeNetworkInterceptor)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.BrowserStateStore", FakeBrowserStateStore)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.SessionPool", FakeSessionPool)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.SessionStateStore", FakeSessionStateStore)

    target = TargetSite(
        url="https://www.amazon.com/",
        session_id="crawl03",
        interaction_goal="collect search results",
        target_hint="iPhone 15",
    )
    target.intent.resource_kind = "search_results"

    stage = CrawlStage()
    result = await stage.execute(PipelineState(session_id="crawl03"), DummyMode(), target=target)

    assert result.success is False
    assert result.summary == "No high-confidence target requests matched the requested intent"
    assert result.error is not None
    assert "captured_api_calls=1" in result.error
    assert "action_flow_failed" in result.error


@pytest.mark.asyncio
async def test_crawl_stage_stops_immediately_on_risk_control_signal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "workspace", tmp_path)

    class FakeResponse:
        url = "https://example.com/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1"
        status = 403
        headers = {"content-type": "text/html", "set-cookie": "cf_clearance=token; Path=/; Secure"}

        class request:
            resource_type = "document"

        async def text(self):
            return "<html><title>Just a moment...</title></html>"

    class FakePage:
        def __init__(self) -> None:
            self.url = "https://example.com/"
            self._listeners: dict[str, object] = {}

        def on(self, event_name, callback):
            self._listeners[event_name] = callback

        async def emit_response(self):
            callback = self._listeners.get("response")
            if callback:
                callback(FakeResponse())
            await asyncio.sleep(0)

    class FakeActionRunner:
        async def run(self, page, target, policy):
            await page.emit_response()
            await asyncio.sleep(0.05)
            return type("Result", (), {"executed": 1, "failures": []})()

    class FakeBrowserDriver:
        def __init__(self, *args, **kwargs) -> None:
            self.context = object()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def launch(self, profile, session_state=None, trace_path=None):
            return FakePage()

    class FakeNetworkInterceptor:
        def __init__(self) -> None:
            self.captures = []
            self.js_urls = []

        def attach(self, page) -> None:
            return None

        async def drain(self) -> None:
            return None

        def get_api_calls(self):
            return []

    class FakeBrowserStateStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def persist_context(self, session_id, domain, context, session_state):
            session_state.storage_state_path = str(tmp_path / "storage.json")
            return session_state

    class FakeSessionPool:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def acquire(self, url, session_state, exclude_keys=None):
            return session_state

        def release(self, url, session_state, **kwargs):
            return session_state

    class FakeSessionStateStore:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def save(self, session_id, session_state) -> None:
            return None

    class FakeRealBrowserResolver:
        def __init__(self, **kwargs):
            pass

        async def resolve(self, **kwargs):
            return None  # Simulate resolution failure

    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.ActionRunner", FakeActionRunner)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.BrowserDriver", FakeBrowserDriver)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.NetworkInterceptor", FakeNetworkInterceptor)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.BrowserStateStore", FakeBrowserStateStore)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.SessionPool", FakeSessionPool)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.SessionStateStore", FakeSessionStateStore)
    monkeypatch.setattr("axelo.pipeline.stages.s1_crawl.RealBrowserResolver", FakeRealBrowserResolver)

    target = TargetSite(
        url="https://example.com/",
        session_id="crawl04",
        interaction_goal="collect product details",
    )

    stage = CrawlStage()
    result = await stage.execute(PipelineState(session_id="crawl04"), DummyMode(), target=target)

    assert result.success is False
    assert result.summary == "Risk-control challenge detected during crawl"
    assert result.error is not None
    assert "status=403" in result.error
    assert "cdn-cgi/challenge-platform" in result.error


@pytest.mark.asyncio
async def test_static_asset_cdn_cookies_do_not_trigger_risk_signal():
    """CDN anti-bot cookies (bm_sz, _abck) on static assets must NOT fire the risk signal.

    Shopee's CDN (Akamai) sets bm_sz / _abck on every response, including CSS
    bundle files.  Before this fix, _RiskSignalObserver fired a false-positive
    'risk-control challenge page detected' for those stylesheet responses.
    """
    from axelo.domain.services.risk_control_service import RiskControlService

    # Test 1: static asset (stylesheet) with CDN anti-bot cookie — must not fire
    observer = _RiskSignalObserver(RiskControlService(), target_url="https://example.com/")

    class FakeRequest:
        resource_type = "stylesheet"
        url = "https://cdn.example.com/assets/bundle.abc123.css"

    class FakeResponse:
        url = "https://cdn.example.com/assets/bundle.abc123.css"
        status = 200
        request = FakeRequest()
        headers = {
            "content-type": "text/css",
            "set-cookie": "bm_sz=AABBCC; Path=/; Domain=.example.com",
        }

        async def text(self):
            return ""

    await observer._inspect_response(FakeResponse())
    assert not observer._event.is_set(), "Static asset Akamai cookie incorrectly triggered risk-control signal"
    assert observer._signal is None

    # Test 2: cross-origin CDN fetch (localization JSON) with Akamai cookies — must not fire
    observer2 = _RiskSignalObserver(RiskControlService(), target_url="https://shopee.com/search")

    class FakeXhrRequest:
        resource_type = "fetch"
        url = "https://deo.shopeemobile.com/shopee/stm-sg-live/shopee-pcmall-live-sg/en.col722.json"

    class FakeXhrResponse:
        url = "https://deo.shopeemobile.com/shopee/stm-sg-live/shopee-pcmall-live-sg/en.col722.json"
        status = 200
        request = FakeXhrRequest()
        headers = {
            "content-type": "application/json",
            "set-cookie": "_abck=XYZXYZ; Path=/; Domain=.shopeemobile.com, bm_sz=AABBCC; Path=/",
        }

        async def text(self):
            return "{}"

    await observer2._inspect_response(FakeXhrResponse())
    assert not observer2._event.is_set(), "Cross-origin CDN JSON fetch incorrectly triggered risk-control signal"
    assert observer2._signal is None
