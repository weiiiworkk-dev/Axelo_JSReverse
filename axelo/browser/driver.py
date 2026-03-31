from __future__ import annotations
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
from axelo.models.target import BrowserProfile
from axelo.browser.profiles import STEALTH_SCRIPT
import structlog

log = structlog.get_logger()


class BrowserDriver:
    """
    Playwright 浏览器驱动封装。
    管理 Browser / Context / Page 生命周期。
    """

    def __init__(self, browser_type: str = "chromium", headless: bool = True) -> None:
        self._browser_type = browser_type
        self._headless = headless
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def launch(self, profile: BrowserProfile) -> Page:
        self._pw = await async_playwright().start()

        launcher = getattr(self._pw, self._browser_type)
        self._browser = await launcher.launch(
            headless=self._headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )

        self._context = await self._browser.new_context(
            user_agent=profile.user_agent or None,
            viewport={"width": profile.viewport_width, "height": profile.viewport_height},
            locale=profile.locale,
            timezone_id=profile.timezone,
            extra_http_headers=profile.extra_headers,
            ignore_https_errors=True,
        )

        if profile.stealth:
            await self._context.add_init_script(STEALTH_SCRIPT)

        self._page = await self._context.new_page()
        log.info("browser_launched", type=self._browser_type, headless=self._headless)
        return self._page

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        log.info("browser_closed")

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("BrowserDriver 未启动，请先调用 launch()")
        return self._page

    async def __aenter__(self) -> "BrowserDriver":
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
