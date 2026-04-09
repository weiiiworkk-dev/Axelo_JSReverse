from __future__ import annotations

import pytest

from axelo.browser.interceptor import NetworkInterceptor


class FakeRequest:
    def __init__(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        resource_type: str = "xhr",
        post_data_buffer: bytes | None = None,
    ) -> None:
        self.url = url
        self.method = method
        self.headers = headers or {}
        self.resource_type = resource_type
        self.post_data_buffer = post_data_buffer


class FakeResponse:
    def __init__(
        self,
        request: FakeRequest,
        *,
        status: int,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self.request = request
        self.status = status
        self.headers = headers or {}
        self.url = request.url
        self._body = body

    async def body(self) -> bytes:
        return self._body


@pytest.mark.asyncio
async def test_network_interceptor_matches_duplicate_urls_by_request_identity():
    interceptor = NetworkInterceptor()
    request_one = FakeRequest("https://api.example.com/data", method="POST")
    request_two = FakeRequest("https://api.example.com/data", method="POST")

    interceptor._on_request(request_one)
    interceptor._on_request(request_two)

    interceptor._on_response_sync(
        FakeResponse(
            request_one,
            status=201,
            headers={"X-Order": "one"},
            body=b"first-response",
        )
    )
    interceptor._on_response_sync(
        FakeResponse(
            request_two,
            status=202,
            headers={"X-Order": "two"},
            body=b"second-response",
        )
    )

    await interceptor.drain()

    assert interceptor.captures[0].response_status == 201
    assert interceptor.captures[0].response_headers["X-Order"] == "one"
    assert interceptor.captures[0].response_body == b"first-response"
    assert interceptor.captures[1].response_status == 202
    assert interceptor.captures[1].response_headers["X-Order"] == "two"
    assert interceptor.captures[1].response_body == b"second-response"
