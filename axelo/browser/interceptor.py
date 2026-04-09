from __future__ import annotations

import asyncio
import re
import time

import structlog
from playwright.async_api import Page, Request, Response

from axelo.models.target import RequestCapture

log = structlog.get_logger()

SKIP_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

JS_URL_PATTERNS = [
    re.compile(r"\.js(\?.*)?$", re.I),
    re.compile(r"/static/js/", re.I),
    re.compile(r"/assets/.*\.js", re.I),
    re.compile(r"chunk\.[a-f0-9]+\.js", re.I),
]


class NetworkInterceptor:
    """
    Attach to a Playwright page and capture request/response pairs.

    Request events are handled synchronously and responses are drained later so
    body reads never block the Playwright event callback.
    """

    def __init__(self) -> None:
        self.captures: list[RequestCapture] = []
        self.js_urls: list[str] = []
        self._api_call_times: dict[str, float] = {}   # url → API 调用发起时间戳
        self._js_load_times: dict[str, float] = {}    # url → JS Bundle 加载时间戳
        self._response_queue: asyncio.Queue[tuple[Response, int]] = asyncio.Queue()
        self._capture_index_by_request_id: dict[int, int] = {}

    def attach(self, page: Page) -> None:
        self._page = page
        page.on("request", self._on_request)
        page.on("response", self._on_response_sync)

    def detach(self) -> None:
        if self._page:
            self._page.remove_listener("request", self._on_request)
            self._page.remove_listener("response", self._on_response_sync)
            self._page = None

    def _on_request(self, request: Request) -> None:
        if request.resource_type in SKIP_RESOURCE_TYPES:
            return

        body_bytes: bytes | None = None
        try:
            raw = request.post_data_buffer
            body_bytes = raw if raw else None
        except Exception:
            pass

        capture = RequestCapture(
            url=request.url,
            method=request.method,
            request_headers=dict(request.headers),
            request_body=body_bytes,
            timestamp=time.time(),
            initiator=self._map_initiator(request.resource_type),
        )
        self.captures.append(capture)
        self._capture_index_by_request_id[id(request)] = len(self.captures) - 1

        # 记录 API 调用时间戳（用于 Bundle-API 时序关联）
        if capture.initiator in ("fetch", "xhr"):
            if capture.url not in self._api_call_times:
                self._api_call_times[capture.url] = capture.timestamp

        url = request.url
        if request.resource_type == "script" or any(pattern.search(url) for pattern in JS_URL_PATTERNS):
            if url not in self.js_urls:
                self.js_urls.append(url)
            if url not in self._js_load_times:
                self._js_load_times[url] = capture.timestamp

    def _on_response_sync(self, response: Response) -> None:
        if response.request.resource_type in SKIP_RESOURCE_TYPES:
            return
        try:
            self._response_queue.put_nowait((response, id(response.request)))
        except asyncio.QueueFull:
            log.warning("response_queue_full", url=response.url[:60])

    async def drain(self, timeout: float = 5.0) -> None:
        drained = 0
        while not self._response_queue.empty():
            try:
                response, request_id = self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            body_bytes: bytes | None = None
            try:
                body_bytes = await asyncio.wait_for(response.body(), timeout=timeout)
            except Exception:
                pass

            self._apply_response(response, request_id=request_id, body_bytes=body_bytes)
            drained += 1

        if drained:
            log.debug("interceptor_drained", count=drained)

    def _map_initiator(self, resource_type: str) -> str:
        return {
            "fetch": "fetch",
            "xhr": "xhr",
            "script": "script",
            "document": "navigation",
        }.get(resource_type, "other")

    def _apply_response(
        self,
        response: Response,
        *,
        request_id: int,
        body_bytes: bytes | None,
    ) -> None:
        capture_index = self._capture_index_by_request_id.pop(request_id, None)
        if capture_index is not None and 0 <= capture_index < len(self.captures):
            capture = self.captures[capture_index]
            if capture.response_status == 0:
                capture.response_status = response.status
                capture.response_headers = dict(response.headers)
                capture.response_body = body_bytes[:4096] if body_bytes else None
                return

        url = response.request.url
        method = response.request.method
        for capture in reversed(self.captures):
            if capture.url == url and capture.method == method and capture.response_status == 0:
                capture.response_status = response.status
                capture.response_headers = dict(response.headers)
                capture.response_body = body_bytes[:4096] if body_bytes else None
                return

    def get_api_calls(self) -> list[RequestCapture]:
        return [capture for capture in self.captures if capture.initiator in ("fetch", "xhr")]

    def get_api_correlated_js_urls(self, window_sec: float = 30.0) -> list[str]:
        """返回在任意 API 调用前 window_sec 秒内被加载的 JS URL。

        加载时机早于 API 调用、且时间差在 window_sec 以内的 Bundle，
        极有可能包含该 API 的签名逻辑。无时序数据时回退到全部 js_urls。
        """
        if not self._api_call_times or not self._js_load_times:
            return list(self.js_urls)
        correlated: list[str] = []
        api_times = list(self._api_call_times.values())
        for js_url, load_time in self._js_load_times.items():
            for api_time in api_times:
                if 0 <= (api_time - load_time) <= window_sec:
                    correlated.append(js_url)
                    break
        return correlated
