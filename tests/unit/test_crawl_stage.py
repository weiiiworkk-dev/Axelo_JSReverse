from __future__ import annotations

from axelo.models.target import RequestCapture
from axelo.models.target import TargetSite
from axelo.pipeline.stages.s1_crawl import (
    _prioritize_api_calls,
    _select_session_status,
    _session_attempt_succeeded,
)


def _capture(url: str, status: int) -> RequestCapture:
    return RequestCapture(url=url, method="GET", response_status=status)


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
