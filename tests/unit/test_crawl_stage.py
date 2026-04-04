from __future__ import annotations

from axelo.models.target import RequestCapture
from axelo.pipeline.stages.s1_crawl import _select_session_status, _session_attempt_succeeded


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
