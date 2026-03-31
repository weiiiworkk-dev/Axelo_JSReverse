from __future__ import annotations
import asyncio
import time
import re
from playwright.async_api import Page, Request, Response
from axelo.models.target import RequestCapture
import structlog

log = structlog.get_logger()

SKIP_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

JS_URL_PATTERNS = [
    re.compile(r'\.js(\?.*)?$', re.I),
    re.compile(r'/static/js/', re.I),
    re.compile(r'/assets/.*\.js', re.I),
    re.compile(r'chunk\.[a-f0-9]+\.js', re.I),
]


class NetworkInterceptor:
    """
    附加在 Playwright Page 上，拦截所有网络请求/响应。

    异步安全设计：
    - _on_request：同步回调，直接写入 captures 列表（无 await，无竞争）
    - _on_response：同步回调，将 Response 对象推入 asyncio.Queue
    - drain()：在导航完成后调用，从 Queue 中取出 Response 异步读取 body
      这样彻底避免了在 Playwright 事件回调中直接 await 的问题
    """

    def __init__(self) -> None:
        self.captures: list[RequestCapture] = []
        self.js_urls: list[str] = []
        # Response 对象队列，等待 drain() 处理
        self._response_queue: asyncio.Queue[Response] = asyncio.Queue()

    def attach(self, page: Page) -> None:
        page.on("request", self._on_request)
        page.on("response", self._on_response_sync)

    # ── 同步回调（Playwright 事件线程调用）──────────────────────

    def _on_request(self, request: Request) -> None:
        if request.resource_type in SKIP_RESOURCE_TYPES:
            return

        body_bytes: bytes | None = None
        try:
            raw = request.post_data_buffer
            body_bytes = raw if raw else None
        except Exception:
            pass

        cap = RequestCapture(
            url=request.url,
            method=request.method,
            request_headers=dict(request.headers),
            request_body=body_bytes,
            timestamp=time.time(),
            initiator=self._map_initiator(request.resource_type),
        )
        self.captures.append(cap)

        url = request.url
        if request.resource_type == "script" or any(p.search(url) for p in JS_URL_PATTERNS):
            if url not in self.js_urls:
                self.js_urls.append(url)

    def _on_response_sync(self, response: Response) -> None:
        """同步入队，不 await，彻底安全"""
        if response.request.resource_type in SKIP_RESOURCE_TYPES:
            return
        try:
            self._response_queue.put_nowait(response)
        except asyncio.QueueFull:
            log.warning("response_queue_full", url=response.url[:60])

    # ── 异步 drain（在导航/等待结束后主动调用）──────────────────

    async def drain(self, timeout: float = 5.0) -> None:
        """
        消费 Queue 中所有待处理的 Response，读取 body 并回填到 captures。
        在 page.goto() / page.wait_for_timeout() 之后调用一次即可。
        timeout：单个 response.body() 读取的最大等待时间（秒）。
        """
        drained = 0
        while not self._response_queue.empty():
            try:
                response: Response = self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            url = response.request.url
            body_bytes: bytes | None = None
            try:
                body_bytes = await asyncio.wait_for(response.body(), timeout=timeout)
            except Exception:
                pass

            # 回填到对应的 capture
            for cap in reversed(self.captures):
                if cap.url == url and cap.response_status == 0:
                    cap.response_status = response.status
                    cap.response_headers = dict(response.headers)
                    cap.response_body = body_bytes
                    break

            drained += 1

        if drained:
            log.debug("interceptor_drained", count=drained)

    # ── 辅助 ────────────────────────────────────────────────────

    def _map_initiator(self, resource_type: str) -> str:
        return {
            "fetch": "fetch",
            "xhr": "xhr",
            "script": "script",
            "document": "navigation",
        }.get(resource_type, "other")

    def get_api_calls(self) -> list[RequestCapture]:
        return [c for c in self.captures if c.initiator in ("fetch", "xhr")]
